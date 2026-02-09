"""
DB Manager - PostgreSQL 직접 저장

역할:
  - 크롤링된 뉴스를 PostgreSQL에 직접 저장 (기존 HTTP POST 대체)
  - CrawlJob 상태 업데이트 (RUNNING → COMPLETED / FAILED)

@author Ekko0701
@since 2026-02-06
"""
from datetime import datetime
import json
import uuid

from app.config.database import SessionLocal
from app.models.db_models import News, CrawlJobModel
from app.utils.logger import log


class DBManager:
    """PostgreSQL 직접 저장 매니저"""

    def save_news(self, news_data) -> bool:
        """
        뉴스 1건 저장 (중복 URL 체크 포함)

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
