"""
DBManager 단위 테스트.

목표:
- 실제 PostgreSQL 연결 없이 save_news_with_analysis()의 제어 흐름을 검증한다.
- SessionLocal을 테스트 더블로 치환해 commit/rollback/close 호출 여부를 확인한다.
"""

from datetime import datetime

from app.models.news import CrawledNews
from app.services.db_manager import DBManager


class _QueryStub:
    """session.query(...).filter(...).first() 체인을 최소 형태로 흉내내는 더블."""

    def __init__(self, first_value):
        self._first_value = first_value

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._first_value


class _SessionStub:
    """
    SQLAlchemy Session 최소 동작 더블.

    save_news_with_analysis()가 사용하는 메서드만 구현한다:
    - query/filter/first
    - add/flush/commit/rollback/close
    """

    def __init__(self, duplicate_news=None):
        self.duplicate_news = duplicate_news
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def query(self, _model):
        return _QueryStub(self.duplicate_news)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _sample_news(sentiment=1.7, keywords=None, stock_codes=None):
    """테스트용 CrawledNews 생성 헬퍼."""
    return CrawledNews(
        title="삼성전자 실적",
        content="실적이 개선되었습니다.",
        url="https://example.com/news-1",
        source="hankyung",
        published_at=datetime(2026, 3, 8, 10, 0, 0),
        sentiment_score=sentiment,
        keywords=keywords or ["삼성전자", "실적"],
        stock_codes=stock_codes or {"005930": 2},
    )


def test_save_news_with_analysis_returns_false_when_duplicate_url(monkeypatch):
    """
    중복 URL이면 즉시 False를 반환해야 한다.

    기대 동작:
    - DB INSERT/분석 저장 로직으로 진입하지 않음
    - commit/rollback 없이 close만 호출
    """
    from app.services import db_manager as db_manager_module

    session = _SessionStub(duplicate_news=object())
    monkeypatch.setattr(db_manager_module, "SessionLocal", lambda: session)

    manager = DBManager()
    result = manager.save_news_with_analysis(_sample_news())

    assert result is False
    assert session.commit_count == 0
    assert session.rollback_count == 0
    assert session.close_count == 1


def test_save_news_with_analysis_success_commits_and_clamps_sentiment(monkeypatch):
    """
    정상 저장 시 commit이 호출되고 감정 점수는 -1.0~1.0 범위로 보정되어야 한다.

    추가 검증:
    - keywords/stock_codes가 존재하면 내부 저장 메서드가 호출되는지 확인
    """
    from app.services import db_manager as db_manager_module

    session = _SessionStub(duplicate_news=None)
    monkeypatch.setattr(db_manager_module, "SessionLocal", lambda: session)

    manager = DBManager()
    recorded = {"keywords_called": 0, "stocks_called": 0}

    def _fake_save_keywords(_session, _news, _keywords):
        recorded["keywords_called"] += 1

    def _fake_save_stocks(_session, _news, _stocks):
        recorded["stocks_called"] += 1

    monkeypatch.setattr(manager, "_save_keywords", _fake_save_keywords)
    monkeypatch.setattr(manager, "_save_stock_mentions", _fake_save_stocks)

    # 입력 sentiment_score=1.7 -> 내부에서 1.00으로 clamp 되어 저장되어야 함
    result = manager.save_news_with_analysis(_sample_news(sentiment=1.7))

    assert result is True
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.close_count == 1
    assert recorded["keywords_called"] == 1
    assert recorded["stocks_called"] == 1

    saved_news = session.added[0]
    assert str(saved_news.sentiment_score) == "1.0"


def test_save_news_with_analysis_rolls_back_when_keyword_save_fails(monkeypatch):
    """
    키워드 저장 중 예외가 발생하면 전체 트랜잭션을 rollback 해야 한다.

    기대 동작:
    - False 반환
    - commit 미호출
    - rollback 1회 호출
    """
    from app.services import db_manager as db_manager_module

    session = _SessionStub(duplicate_news=None)
    monkeypatch.setattr(db_manager_module, "SessionLocal", lambda: session)

    manager = DBManager()

    def _raise_error(*_args, **_kwargs):
        raise RuntimeError("keyword insert failed")

    monkeypatch.setattr(manager, "_save_keywords", _raise_error)

    result = manager.save_news_with_analysis(
        _sample_news(keywords=["삼성전자"], stock_codes={})
    )

    assert result is False
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1
