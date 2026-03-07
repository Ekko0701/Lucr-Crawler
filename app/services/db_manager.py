"""
DB Manager - PostgreSQL 직접 저장

역할:
  - 크롤링된 뉴스를 PostgreSQL에 직접 저장
  - 뉴스 + 분석 결과(감정 점수, 키워드, 종목 언급)를 같은 트랜잭션에서 저장
  - CrawlJob 상태 업데이트 (RUNNING → COMPLETED / FAILED)

@author Ekko0701
@since 2026-02-06
"""
from datetime import datetime
from decimal import Decimal
import json
import uuid

from app.config.database import SessionLocal
from app.models.db_models import CrawlJobModel, Keyword, News, NewsKeyword, NewsStock
from app.utils.logger import log


class DBManager:
    """PostgreSQL 직접 저장 매니저"""

    def save_news(self, news_data) -> bool:
        """
        뉴스 1건 저장 (중복 URL 체크 포함)

        참고:
            분석 결과까지 함께 저장해야 할 때는 save_news_with_analysis()를 사용합니다.

        Args:
            news_data: CrawledNews 객체 (app.models.news.CrawledNews)

        Returns:
            True: 저장 성공, False: 중복 또는 실패
        """
        session = SessionLocal()
        try:
            # URL 중복 확인
            exists = session.query(News).filter(News.url == news_data.url).first()
            if exists:
                log.debug(f"중복 URL 스킵: {news_data.url}")
                return False

            # News 객체 생성 및 저장
            news = News(
                id=uuid.uuid4(),
                title=news_data.title,
                content=news_data.content,
                url=news_data.url,
                source=news_data.source,
                published_at=news_data.published_at,
                crawled_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(news)
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            log.error(f"뉴스 저장 실패: {e}")
            return False
        finally:
            session.close()

    def save_news_with_analysis(self, news_data) -> bool:
        """
        뉴스 + 분석 결과를 하나의 트랜잭션에서 저장합니다.

        저장 순서:
            1. URL 중복 확인
            2. news INSERT (sentiment_score 포함)
            3. keywords UPSERT + news_keywords INSERT
            4. news_stocks INSERT
            5. COMMIT

        중간 단계에서 예외가 나면 전체 ROLLBACK하여
        부분 저장(뉴스만 저장, 키워드 누락 등)을 방지합니다.

        Args:
            news_data: CrawledNews 객체 (analysis 필드 포함)

        Returns:
            True: 저장 성공, False: 중복 URL 또는 예외
        """
        session = SessionLocal()
        try:
            # 1) URL 중복 확인
            exists = session.query(News).filter(News.url == news_data.url).first()
            if exists:
                log.debug(f"중복 URL 스킵: {news_data.url}")
                return False

            # 2) 뉴스 저장 (감정 점수 포함)
            sentiment = None
            if news_data.sentiment_score is not None:
                clamped = max(-1.0, min(1.0, news_data.sentiment_score))
                sentiment = Decimal(str(round(clamped, 2)))

            news = News(
                id=uuid.uuid4(),
                title=news_data.title,
                content=news_data.content,
                url=news_data.url,
                source=news_data.source,
                published_at=news_data.published_at,
                crawled_at=datetime.now(),
                sentiment_score=sentiment,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(news)
            session.flush()  # news.id 확보

            # 3) 키워드 저장
            keywords = getattr(news_data, "keywords", []) or []
            if keywords:
                self._save_keywords(session, news, keywords)

            # 4) 종목 언급 저장
            stock_codes = getattr(news_data, "stock_codes", {}) or {}
            if stock_codes:
                self._save_stock_mentions(session, news, stock_codes)

            # 5) 전체 커밋
            session.commit()
            log.debug(
                f"뉴스+분석 저장 완료: '{news_data.title[:30]}...' "
                f"| sentiment={news_data.sentiment_score} "
                f"| keywords={keywords[:3]} "
                f"| stocks={list(stock_codes.keys())[:3]}"
            )
            return True

        except Exception as e:
            session.rollback()
            log.error(f"뉴스+분석 저장 실패: {e}")
            return False
        finally:
            session.close()

    def _save_keywords(self, session, news: News, keywords: list[str]):
        """
        키워드를 keywords / news_keywords 테이블에 저장합니다.

        - keywords: 동일 단어는 frequency를 1 증가 (UPSERT 성격)
        - news_keywords: 뉴스-키워드 매핑 + rank 기반 tfidf_score 저장

        COMMIT은 호출자(save_news_with_analysis)에서 수행합니다.
        """
        seen_words: set[str] = set()

        for rank, raw_word in enumerate(keywords):
            word = (raw_word or "").strip()
            if not word or word in seen_words:
                continue
            seen_words.add(word)

            keyword_obj = session.query(Keyword).filter(Keyword.word == word).first()
            if keyword_obj:
                keyword_obj.frequency += 1
                keyword_obj.updated_at = datetime.now()
            else:
                keyword_obj = Keyword(
                    id=uuid.uuid4(),
                    word=word,
                    frequency=1,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                session.add(keyword_obj)
                session.flush()  # keyword_id 확보

            # rank(0-based) 기반 점수: 1.00, 0.90, ... 최소 0.10
            tfidf_score = max(
                Decimal("0.10"),
                Decimal("1.00") - Decimal(str(rank)) * Decimal("0.10"),
            )

            session.add(
                NewsKeyword(
                    news_id=news.id,
                    keyword_id=keyword_obj.id,
                    tfidf_score=tfidf_score,
                    created_at=datetime.now(),
                )
            )

    def _save_stock_mentions(self, session, news: News, stock_codes: dict[str, int]):
        """
        종목 언급 정보를 news_stocks 테이블에 저장합니다.

        외래키 제약을 위해 stocks 테이블에 존재하는 종목코드만 저장합니다.
        """
        from sqlalchemy import text as sql_text

        for stock_code, mention_count in stock_codes.items():
            code = (stock_code or "").strip()
            if not code:
                continue

            exists = session.execute(
                sql_text("SELECT 1 FROM stocks WHERE code = :code"),
                {"code": code},
            ).fetchone()
            if not exists:
                log.debug(f"종목코드 미등록, 스킵: {code}")
                continue

            safe_count = int(mention_count) if mention_count and mention_count > 0 else 1

            session.add(
                NewsStock(
                    news_id=news.id,
                    stock_code=code,
                    mention_count=safe_count,
                    created_at=datetime.now(),
                )
            )

    def update_job_status(self, job_id: str, status: str,
                          total_articles: int = 0,
                          media_results: dict = None,
                          error_message: str = None):
        """
        CrawlJob 상태 업데이트

        Args:
            job_id: 작업 UUID (문자열)
            status: 변경할 상태 ("RUNNING" / "COMPLETED" / "FAILED")
            total_articles: 수집된 총 기사 수
            media_results: 언론사별 수집 결과 dict
            error_message: 실패 시 에러 메시지
        """
        session = SessionLocal()
        try:
            job = session.query(CrawlJobModel).filter(
                CrawlJobModel.id == uuid.UUID(job_id)
            ).first()

            if not job:
                log.error(f"CrawlJob을 찾을 수 없음: {job_id}")
                return

            job.status = status
            job.updated_at = datetime.now()

            if status == "COMPLETED":
                job.total_articles = total_articles
                job.media_results = json.dumps(media_results) if media_results else None
                job.completed_at = datetime.now()
            elif status == "FAILED":
                job.error_message = error_message
                job.completed_at = datetime.now()

            session.commit()
            log.info(f"CrawlJob 상태 업데이트: {job_id} → {status}")

        except Exception as e:
            session.rollback()
            log.error(f"CrawlJob 업데이트 실패: {e}")
        finally:
            session.close()
