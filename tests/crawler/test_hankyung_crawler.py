"""
HankyungCrawler 파싱 로직 단위 테스트.

핵심 전략:
- httpx를 mock해서 실제 네트워크 요청 없이 HTML 파싱 로직만 검증한다.
- 목록 페이지에서 링크 추출, 상세 페이지에서 본문/이미지 추출을 분리 테스트한다.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.crawler.hankyung_crawler import HankyungCrawler


SAMPLE_LIST_HTML = """
<html>
<body>
  <a href="/article/2026030800001">삼성전자 역대 최대 실적 달성으로 주가 상승 기대</a>
  <a href="/article/2026030800002">SK하이닉스 반도체 호조 속에 투자자 관심 집중</a>
  <a href="/article/2026030800001">삼성전자 역대 최대 실적 달성으로 주가 상승 기대</a>
  <a href="/other/page">짧은</a>
  <a href="/article/2026030800003">제목없</a>
</body>
</html>
"""

SAMPLE_DETAIL_HTML = """
<html>
<body>
  <div class="article-body">
    삼성전자가 2025년 4분기 영업이익 15조원을 기록했다.
  </div>
  <article>
    <img src="/images/photo.jpg" />
  </article>
</body>
</html>
"""


def _mock_response(text, status_code=200):
    """httpx.Response를 흉내내는 객체 생성."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def test_crawl_extracts_unique_article_links():
    """
    목록 페이지에서 /article/ 링크를 추출하되:
    - 중복 URL은 제거
    - 제목이 10자 미만인 링크는 _parse_news_link에서 스킵
    """
    crawler = HankyungCrawler()

    mock_client = AsyncMock()
    # 목록 페이지 응답
    mock_client.get = AsyncMock(side_effect=[
        _mock_response(SAMPLE_LIST_HTML),      # 목록
        _mock_response(SAMPLE_DETAIL_HTML),     # 상세 1 (삼성전자)
        _mock_response(SAMPLE_DETAIL_HTML),     # 상세 2 (SK하이닉스)
        _mock_response(SAMPLE_DETAIL_HTML),     # 상세 3 (제목없 → 스킵됨)
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # httpx.AsyncClient를 mock으로 대체
    import httpx
    original_client = httpx.AsyncClient

    def fake_client(**kwargs):
        return mock_client

    httpx.AsyncClient = fake_client
    try:
        result = asyncio.run(crawler.crawl(max_news=10))
    finally:
        httpx.AsyncClient = original_client

    # 중복 제거 후 3개 고유 링크, 그 중 "제목없"(3자)은 스킵 → 2개
    assert len(result) == 2
    assert result[0].source == "HANKYUNG"
    assert "삼성전자" in result[0].title


def test_fetch_news_content_extracts_body_and_image():
    """상세 페이지에서 .article-body 본문과 article img를 추출해야 한다."""
    crawler = HankyungCrawler()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_DETAIL_HTML))

    content, image_url = asyncio.run(
        crawler._fetch_news_content("https://example.com/article/1", mock_client)
    )

    assert "15조원" in content
    assert image_url == "https://www.hankyung.com/images/photo.jpg"


def test_fetch_news_content_fallback_on_missing_body():
    """본문 셀렉터에 매칭되는 요소가 없으면 '본문 없음'을 반환해야 한다."""
    crawler = HankyungCrawler()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response("<html><body></body></html>"))

    content, image_url = asyncio.run(
        crawler._fetch_news_content("https://example.com/article/1", mock_client)
    )

    assert content == "본문 없음"
    assert image_url is None


def test_fetch_news_content_returns_fallback_on_error():
    """HTTP 요청 실패 시 '본문 없음'과 None을 반환해야 한다."""
    crawler = HankyungCrawler()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection timeout"))

    content, image_url = asyncio.run(
        crawler._fetch_news_content("https://example.com/article/1", mock_client)
    )

    assert content == "본문 없음"
    assert image_url is None


def test_crawl_returns_empty_list_on_network_error():
    """목록 페이지 요청이 실패하면 빈 리스트를 반환해야 한다."""
    crawler = HankyungCrawler()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("network error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx
    original_client = httpx.AsyncClient

    def fake_client(**kwargs):
        return mock_client

    httpx.AsyncClient = fake_client
    try:
        result = asyncio.run(crawler.crawl(max_news=10))
    finally:
        httpx.AsyncClient = original_client

    assert result == []
