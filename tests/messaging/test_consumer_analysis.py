"""
CrawlConsumer._analyze_news_batch 단위 테스트.

목표:
- 감정/키워드/종목 분석기가 정상일 때 결과 필드가 각 뉴스에 채워지는지 검증
- 특정 분석기에서 예외가 발생해도 나머지 분석 단계가 계속 수행되는지 검증
"""

from types import SimpleNamespace

from app.messaging.consumer import CrawlConsumer


def _news(title, content):
    """테스트용 뉴스 객체 생성 헬퍼 (CrawledNews와 동일 속성만 최소 구성)."""
    return SimpleNamespace(
        title=title,
        content=content,
        sentiment_score=None,
        keywords=[],
        stock_codes={},
    )


class _SentimentStub:
    """입력 텍스트 길이에 따라 고정 점수를 반환하는 감정 분석 더블."""

    def analyze(self, text):
        return 0.75 if "호재" in text else -0.25


class _KeywordStub:
    """입력 텍스트 배치와 동일 길이의 키워드 목록을 반환하는 더블."""

    def extract_batch(self, texts, top_n=10):
        assert top_n == 10
        return [["삼성전자", "실적"] if "삼성" in t else ["금리", "인하"] for t in texts]


class _StockStub:
    """텍스트에 포함된 단어를 기준으로 종목코드 매칭 결과를 반환하는 더블."""

    def match(self, text):
        return {"005930": 2} if "삼성" in text else {}


def test_analyze_news_batch_applies_all_analyzers():
    """
    3개 분석기가 모두 정상일 때 기대 결과:
    - sentiment_score 설정
    - keywords 설정
    - stock_codes 설정
    """
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.sentiment_analyzer = _SentimentStub()
    consumer.keyword_extractor = _KeywordStub()
    consumer.stock_matcher = _StockStub()

    news_list = [
        _news("삼성전자 호재", "실적 개선"),
        _news("거시경제", "금리 인하 기대"),
    ]

    result = consumer._analyze_news_batch(news_list)

    assert result[0].sentiment_score == 0.75
    assert result[0].keywords == ["삼성전자", "실적"]
    assert result[0].stock_codes == {"005930": 2}

    assert result[1].sentiment_score == -0.25
    assert result[1].keywords == ["금리", "인하"]
    assert result[1].stock_codes == {}


def test_analyze_news_batch_continues_when_keyword_extractor_fails():
    """
    키워드 추출 단계만 실패해도 전체 처리가 멈추면 안 된다.

    기대 결과:
    - sentiment_score는 정상 반영
    - keyword 단계는 건너뛰므로 기본값([]) 유지
    - stock 매칭은 계속 수행되어 결과 반영
    """

    class _BrokenKeywordStub:
        def extract_batch(self, _texts, top_n=10):
            raise RuntimeError("keyword extractor failed")

    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.sentiment_analyzer = _SentimentStub()
    consumer.keyword_extractor = _BrokenKeywordStub()
    consumer.stock_matcher = _StockStub()

    news_list = [_news("삼성전자 호재", "실적 개선")]
    result = consumer._analyze_news_batch(news_list)

    assert result[0].sentiment_score == 0.75
    assert result[0].keywords == []
    assert result[0].stock_codes == {"005930": 2}
