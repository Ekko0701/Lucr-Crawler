"""
MKCrawler RSS 파싱 로직 단위 테스트.

핵심 전략:
- RSS XML을 mock으로 제공해 _parse_rss_item()의 파싱 로직을 검증한다.
- 상세 페이지 본문 추출은 다중 셀렉터 폴백 로직을 포함한다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from bs4 import BeautifulSoup

from app.crawler.mk_crawler import MKCrawler


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title>매경 단독: 반도체 수출 사상 최고</title>
    <link>https://www.mk.co.kr/news/stock/2026/0300001</link>
    <description>반도체 수출이 역대 최고를 기록했다.</description>
    <pubDate>Sat, 08 Mar 2026 10:00:00 +0900</pubDate>
  </item>
  <item>
    <title>금리 인하 기대감 확산</title>
    <link>https://www.mk.co.kr/news/economy/2026/0300002</link>
    <description>한은 금리 인하 가능성 높아져.</description>
    <pubDate>Sat, 08 Mar 2026 11:00:00 +0900</pubDate>
  </item>
  <item>
    <description>제목 없는 아이템</description>
  </item>
</channel>
</rss>
"""

SAMPLE_MK_DETAIL_HTML = """
<html>
<body>
  <div class="news_cnt_detail_wrap">
    반도체 수출이 2026년 사상 최고를 기록하며 무역수지가 개선되었다.
  </div>
  <div class="thumb_area">
    <img src="https://img.mk.co.kr/photo.jpg" />
  </div>
</body>
</html>
"""


def _mock_response(text, status_code=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def test_parse_rss_item_extracts_fields():
    """RSS item에서 title, link, pubDate를 올바르게 파싱해야 한다."""
    crawler = MKCrawler()
    soup = BeautifulSoup(SAMPLE_RSS_XML, "xml")
    item = soup.find("item")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_MK_DETAIL_HTML))

    news = asyncio.run(crawler._parse_rss_item(item, mock_client))

    assert news is not None
    assert news.title == "매경 단독: 반도체 수출 사상 최고"
    assert news.url == "https://www.mk.co.kr/news/stock/2026/0300001"
    assert news.source == "MK"
    assert news.published_at.year == 2026
    assert news.published_at.month == 3


def test_parse_rss_item_skips_missing_title():
    """title 태그가 없는 item은 None을 반환해야 한다."""
    crawler = MKCrawler()
    soup = BeautifulSoup(SAMPLE_RSS_XML, "xml")
    items = soup.find_all("item")
    # 세 번째 item은 title이 없음
    item_no_title = items[2]

    mock_client = AsyncMock()

    news = asyncio.run(crawler._parse_rss_item(item_no_title, mock_client))

    assert news is None


def test_parse_rss_item_uses_description_when_no_body():
    """상세 페이지 본문이 없으면 RSS description을 본문으로 사용해야 한다."""
    crawler = MKCrawler()
    soup = BeautifulSoup(SAMPLE_RSS_XML, "xml")
    item = soup.find("item")

    # 상세 페이지에 본문 셀렉터가 매칭되지 않는 HTML
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response("<html><body></body></html>"))

    news = asyncio.run(crawler._parse_rss_item(item, mock_client))

    assert news is not None
    assert news.content == "반도체 수출이 역대 최고를 기록했다."


def test_fetch_news_content_tries_multiple_selectors():
    """첫 번째 셀렉터가 실패하면 다음 셀렉터로 폴백해야 한다."""
    crawler = MKCrawler()

    # .news_cnt_detail_wrap는 없고 .art_txt만 있는 HTML
    html = """
    <html><body>
      <div class="art_txt">두 번째 셀렉터로 찾은 본문입니다.</div>
    </body></html>
    """
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(html))

    content, image_url = asyncio.run(
        crawler._fetch_news_content("https://example.com/1", mock_client)
    )

    assert "두 번째 셀렉터" in content


def test_fetch_news_content_extracts_image():
    """이미지 셀렉터에 맞는 img src를 추출해야 한다."""
    crawler = MKCrawler()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_MK_DETAIL_HTML))

    content, image_url = asyncio.run(
        crawler._fetch_news_content("https://example.com/1", mock_client)
    )

    assert "사상 최고" in content
    assert image_url == "https://img.mk.co.kr/photo.jpg"


def test_crawl_respects_max_news_limit():
    """max_news 파라미터로 수집 건수를 제한해야 한다."""
    crawler = MKCrawler()

    mock_client = AsyncMock()
    # RSS 응답 + 상세 페이지 1건만
    mock_client.get = AsyncMock(side_effect=[
        _mock_response(SAMPLE_RSS_XML),         # RSS 피드
        _mock_response(SAMPLE_MK_DETAIL_HTML),  # 상세 1건
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx
    original_client = httpx.AsyncClient

    def fake_client(**kwargs):
        return mock_client

    httpx.AsyncClient = fake_client
    try:
        result = asyncio.run(crawler.crawl(max_news=1))
    finally:
        httpx.AsyncClient = original_client

    assert len(result) == 1


def test_crawl_returns_empty_on_rss_fetch_error():
    """RSS 피드 요청 실패 시 빈 리스트를 반환해야 한다."""
    crawler = MKCrawler()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("timeout"))
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
