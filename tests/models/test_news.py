"""
CrawledNews / NewsCreate Pydantic 모델 단위 테스트.

핵심 검증:
- CrawledNews 기본값(분석 필드)이 올바르게 설정되는지
- to_create_dto() 변환 시 감정 점수 clamp(-1.0 ~ 1.0)과 Decimal 변환
- NewsCreate 필드 검증(min_length, max_length)
"""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.news import CrawledNews, NewsCreate


def _base_news(**overrides):
    """CrawledNews 최소 필수 필드 + 오버라이드 헬퍼."""
    defaults = dict(
        title="삼성전자 실적 발표",
        content="삼성전자가 역대 최고 실적을 기록했다.",
        url="https://example.com/news/1",
        source="hankyung",
        published_at=datetime(2026, 3, 8, 10, 0, 0),
    )
    defaults.update(overrides)
    return CrawledNews(**defaults)


# ── CrawledNews 기본값 ──


def test_crawled_news_defaults_analysis_fields():
    """분석 필드(sentiment_score, keywords, stock_codes)는 기본값이 None/[]/{}이어야 한다."""
    news = _base_news()

    assert news.sentiment_score is None
    assert news.keywords == []
    assert news.stock_codes == {}


def test_crawled_news_accepts_analysis_fields():
    """분석 결과가 명시적으로 전달되면 해당 값이 저장되어야 한다."""
    news = _base_news(
        sentiment_score=0.85,
        keywords=["삼성전자", "실적"],
        stock_codes={"005930": 3},
    )

    assert news.sentiment_score == 0.85
    assert news.keywords == ["삼성전자", "실적"]
    assert news.stock_codes == {"005930": 3}


def test_crawled_news_image_url_defaults_to_none():
    """image_url은 선택 필드이며 기본값은 None이다."""
    news = _base_news()
    assert news.image_url is None


def test_crawled_news_preserves_image_url():
    """image_url이 전달되면 그대로 저장되어야 한다."""
    news = _base_news(image_url="https://img.example.com/photo.jpg")
    assert news.image_url == "https://img.example.com/photo.jpg"


# ── to_create_dto() 변환 ──


def test_to_create_dto_clamps_positive_overflow():
    """sentiment_score가 1.0을 초과하면 1.0으로 clamp되어야 한다."""
    news = _base_news(sentiment_score=2.5)
    dto = news.to_create_dto()

    assert dto.sentiment_score == Decimal("1.0")


def test_to_create_dto_clamps_negative_overflow():
    """sentiment_score가 -1.0 미만이면 -1.0으로 clamp되어야 한다."""
    news = _base_news(sentiment_score=-3.0)
    dto = news.to_create_dto()

    assert dto.sentiment_score == Decimal("-1.0")


def test_to_create_dto_preserves_normal_score():
    """정상 범위 점수는 그대로 변환되어야 한다."""
    news = _base_news(sentiment_score=0.75)
    dto = news.to_create_dto()

    assert dto.sentiment_score == Decimal("0.75")


def test_to_create_dto_none_sentiment_stays_none():
    """분석 전(sentiment_score=None) 상태는 DTO에서도 None이어야 한다."""
    news = _base_news(sentiment_score=None)
    dto = news.to_create_dto()

    assert dto.sentiment_score is None


def test_to_create_dto_copies_core_fields():
    """title, content, url, source, published_at은 그대로 복사되어야 한다."""
    news = _base_news()
    dto = news.to_create_dto()

    assert dto.title == news.title
    assert dto.content == news.content
    assert dto.url == news.url
    assert dto.source == news.source
    assert dto.published_at == news.published_at


# ── NewsCreate 검증 ──


def test_news_create_rejects_short_title():
    """title이 5자 미만이면 ValidationError가 발생해야 한다."""
    with pytest.raises(ValidationError):
        NewsCreate(
            title="짧은",
            content="본문입니다",
            url="https://example.com/1",
            source="test",
            published_at=datetime.now(),
        )


def test_news_create_rejects_empty_content():
    """content가 빈 문자열이면 ValidationError가 발생해야 한다."""
    with pytest.raises(ValidationError):
        NewsCreate(
            title="충분히 긴 제목입니다",
            content="",
            url="https://example.com/1",
            source="test",
            published_at=datetime.now(),
        )
