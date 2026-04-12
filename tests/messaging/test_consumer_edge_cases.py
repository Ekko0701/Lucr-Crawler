"""
CrawlConsumer 추가 단위 테스트.

기존 test_consumer_analysis.py는 _analyze_news_batch의 정상/예외 경로를 검증한다.
이 파일은 그 외 엣지 케이스를 보강한다:
- 분석기가 None(초기화 실패)인 경우의 _analyze_news_batch 동작
- 빈 리스트 입력 시 조기 반환
- _on_message의 메시지 파싱 → ACK/NACK 흐름
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.messaging.consumer import CrawlConsumer


def _news(title="제목", content="본문"):
    return SimpleNamespace(
        title=title,
        content=content,
        sentiment_score=None,
        keywords=[],
        stock_codes={},
    )


# ── 분석기 None 분기 ──


def test_analyze_skips_when_all_analyzers_are_none():
    """3개 분석기가 모두 None이면 뉴스 필드가 초기값 그대로 반환되어야 한다."""
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.sentiment_analyzer = None
    consumer.keyword_extractor = None
    consumer.stock_matcher = None

    news_list = [_news("삼성전자 호재", "실적 개선")]
    result = consumer._analyze_news_batch(news_list)

    assert result[0].sentiment_score is None
    assert result[0].keywords == []
    assert result[0].stock_codes == {}


def test_analyze_runs_available_analyzers_only():
    """sentiment만 있고 나머지가 None이면 sentiment만 채워져야 한다."""

    class _SentimentStub:
        def analyze(self, text):
            return 0.5

    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.sentiment_analyzer = _SentimentStub()
    consumer.keyword_extractor = None
    consumer.stock_matcher = None

    news_list = [_news()]
    result = consumer._analyze_news_batch(news_list)

    assert result[0].sentiment_score == 0.5
    assert result[0].keywords == []
    assert result[0].stock_codes == {}


def test_analyze_empty_list_returns_immediately():
    """빈 리스트 입력 시 분석기를 호출하지 않고 그대로 반환해야 한다."""
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    # 분석기를 설정하지 않아도 빈 리스트라면 에러 없이 반환
    consumer.sentiment_analyzer = None
    consumer.keyword_extractor = None
    consumer.stock_matcher = None

    result = consumer._analyze_news_batch([])
    assert result == []


# ── _on_message ACK/NACK 흐름 ──


def test_on_message_acks_on_success():
    """
    정상 처리 시 basic_ack가 호출되어야 한다.
    _run_all_crawlers와 DB 조작을 모두 mock하여 순수 흐름만 검증한다.
    """
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.db = MagicMock()
    consumer.publisher = MagicMock()

    mock_channel = MagicMock()
    mock_method = SimpleNamespace(delivery_tag=42)
    mock_properties = MagicMock()

    message = {"jobId": "test-job-uuid", "maxArticles": 10}
    body = json.dumps(message).encode()

    # _run_all_crawlers를 동기 mock으로 대체
    import asyncio

    async def fake_run_all(max_articles):
        return {"hankyung": 5, "mk": 3}

    with patch.object(consumer, "_run_all_crawlers", side_effect=fake_run_all):
        consumer._on_message(mock_channel, mock_method, mock_properties, body)

    # DB 상태 업데이트 검증
    calls = consumer.db.update_job_status.call_args_list
    assert calls[0].args == ("test-job-uuid", "RUNNING")
    assert calls[1].args[0] == "test-job-uuid"
    assert calls[1].args[1] == "COMPLETED"

    # Publisher 완료 이벤트 발행 검증
    consumer.publisher.publish.assert_called_once()
    pub_args = consumer.publisher.publish.call_args.args
    assert pub_args[0] == "test-job-uuid"
    assert pub_args[1] == "COMPLETED"
    assert pub_args[2] == 8  # total = 5 + 3

    # ACK 검증
    mock_channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_on_message_nacks_on_crawl_failure():
    """
    크롤링 중 예외 발생 시:
    1. DB에 FAILED 상태가 기록되어야 한다
    2. Publisher로 FAILED 이벤트가 발행되어야 한다
    3. basic_ack는 호출되지 않아야 한다
    4. basic_nack(requeue=False)가 호출되어야 한다
    """
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.db = MagicMock()
    consumer.publisher = MagicMock()

    mock_channel = MagicMock()
    mock_method = SimpleNamespace(delivery_tag=99)
    mock_properties = MagicMock()

    message = {"jobId": "fail-job-uuid", "maxArticles": 10}
    body = json.dumps(message).encode()

    import asyncio

    async def fail_run_all(max_articles):
        raise RuntimeError("crawler crashed")

    # _on_message의 except 블록은 지연 import로 SessionLocal/CrawlJobModel을 가져온다.
    # sys.modules에 가짜 모듈을 주입하여 DB 연결 없이 동작하게 한다.
    mock_session = MagicMock()
    mock_job = SimpleNamespace(status="RUNNING")
    mock_session.query.return_value.filter.return_value.first.return_value = mock_job

    fake_db_module = SimpleNamespace(SessionLocal=lambda: mock_session)
    fake_db_models_module = SimpleNamespace(CrawlJobModel=MagicMock())

    import sys
    with patch.object(consumer, "_run_all_crawlers", side_effect=fail_run_all), \
         patch.dict(sys.modules, {
             "app.config.database": fake_db_module,
             "app.models.db_models": fake_db_models_module,
         }):
        consumer._on_message(mock_channel, mock_method, mock_properties, body)

    # 1. DB에 FAILED 상태 기록 검증
    #    update_job_status 호출: 첫 번째는 RUNNING, 두 번째는 FAILED
    status_calls = consumer.db.update_job_status.call_args_list
    assert status_calls[0].args == ("fail-job-uuid", "RUNNING")
    assert status_calls[1].args[0] == "fail-job-uuid"
    assert status_calls[1].args[1] == "FAILED"

    # 2. Publisher로 FAILED 이벤트 발행 검증
    consumer.publisher.publish.assert_called_once()
    pub_args = consumer.publisher.publish.call_args.args
    assert pub_args[0] == "fail-job-uuid"
    assert pub_args[1] == "FAILED"

    # 3. ACK는 호출되지 않아야 한다
    mock_channel.basic_ack.assert_not_called()

    # 4. NACK 검증 (requeue=False)
    mock_channel.basic_nack.assert_called_once_with(delivery_tag=99, requeue=False)


def test_on_message_handles_invalid_json():
    """유효하지 않은 JSON body는 예외를 삼키고 NACK해야 한다."""
    consumer = CrawlConsumer.__new__(CrawlConsumer)
    consumer.db = MagicMock()
    consumer.publisher = MagicMock()

    mock_channel = MagicMock()
    mock_method = SimpleNamespace(delivery_tag=1)
    mock_properties = MagicMock()

    body = b"not-valid-json"

    consumer._on_message(mock_channel, mock_method, mock_properties, body)

    mock_channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)
