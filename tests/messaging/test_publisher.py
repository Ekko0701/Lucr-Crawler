"""
CrawlResultPublisher 단위 테스트.

핵심 전략:
- pika를 mock해서 실제 RabbitMQ 연결 없이 메시지 포맷과 에러 핸들링을 검증한다.
- Spring Jackson이 파싱할 수 있도록 camelCase 키가 사용되는지 확인한다.
"""

import json
from unittest.mock import MagicMock, patch

from app.messaging.publisher import CrawlResultPublisher


def test_publish_sends_correct_message_format():
    """
    발행 메시지가 Spring이 기대하는 camelCase JSON 형식이어야 한다.
    - jobId, status, totalArticles, mediaResults
    """
    publisher = CrawlResultPublisher()

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch("pika.BlockingConnection", return_value=mock_connection):
        publisher.publish(
            job_id="test-uuid-1234",
            status="COMPLETED",
            total_articles=150,
            media_results={"hankyung": 45, "mk": 38},
        )

    # basic_publish가 1회 호출되었는지
    mock_channel.basic_publish.assert_called_once()

    call_kwargs = mock_channel.basic_publish.call_args
    body_json = json.loads(call_kwargs.kwargs.get("body") or call_kwargs[1].get("body"))

    assert body_json["jobId"] == "test-uuid-1234"
    assert body_json["status"] == "COMPLETED"
    assert body_json["totalArticles"] == 150
    assert body_json["mediaResults"] == {"hankyung": 45, "mk": 38}


def test_publish_uses_correct_exchange_and_routing_key():
    """Exchange와 Routing Key가 Spring RabbitMQConfig와 일치해야 한다."""
    publisher = CrawlResultPublisher()

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch("pika.BlockingConnection", return_value=mock_connection):
        publisher.publish("job-1", "COMPLETED")

    call_kwargs = mock_channel.basic_publish.call_args

    # positional 또는 keyword 인자에서 exchange, routing_key 확인
    if call_kwargs.kwargs:
        assert call_kwargs.kwargs["exchange"] == "lucr.crawl.exchange"
        assert call_kwargs.kwargs["routing_key"] == "crawl.result"
    else:
        assert call_kwargs[1]["exchange"] == "lucr.crawl.exchange"
        assert call_kwargs[1]["routing_key"] == "crawl.result"


def test_publish_sets_persistent_delivery_mode():
    """메시지는 persistent(delivery_mode=2)로 설정되어야 한다."""
    publisher = CrawlResultPublisher()

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch("pika.BlockingConnection", return_value=mock_connection):
        publisher.publish("job-1", "COMPLETED")

    call_kwargs = mock_channel.basic_publish.call_args
    properties = call_kwargs.kwargs.get("properties") or call_kwargs[1].get("properties")

    assert properties.delivery_mode == 2
    assert properties.content_type == "application/json"


def test_publish_defaults_media_results_to_empty_dict():
    """media_results가 None이면 빈 dict로 직렬화되어야 한다."""
    publisher = CrawlResultPublisher()

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch("pika.BlockingConnection", return_value=mock_connection):
        publisher.publish("job-1", "FAILED", total_articles=0, media_results=None)

    body_json = json.loads(
        mock_channel.basic_publish.call_args.kwargs.get("body")
        or mock_channel.basic_publish.call_args[1].get("body")
    )

    assert body_json["mediaResults"] == {}
    assert body_json["totalArticles"] == 0


def test_publish_returns_true_on_success():
    """발행 성공 시 True를 반환하고 connection.close()가 호출되어야 한다."""
    publisher = CrawlResultPublisher()

    mock_connection = MagicMock()
    mock_connection.channel.return_value = MagicMock()

    with patch("pika.BlockingConnection", return_value=mock_connection):
        result = publisher.publish("job-1", "COMPLETED")

    assert result is True
    mock_connection.close.assert_called_once()


def test_publish_returns_false_on_connection_failure():
    """RabbitMQ 연결 실패 시 예외를 전파하지 않되, False를 반환하여 호출자가 실패를 인지할 수 있어야 한다."""
    publisher = CrawlResultPublisher()

    with patch("pika.BlockingConnection", side_effect=Exception("connection refused")):
        result = publisher.publish("job-1", "FAILED")

    assert result is False
