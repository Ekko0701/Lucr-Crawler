"""
Lucr Crawler Worker - RabbitMQ Consumer 실행

기존 FastAPI(main.py)와 별도로 실행되는 Worker 프로세스입니다.
RabbitMQ에서 크롤링 요청 메시지를 수신하고 처리합니다.

실행 방법:
    python -m app.worker

@author Ekko0701
@since 2026-02-06
"""
from app.messaging.consumer import CrawlConsumer
from app.utils.logger import log


def main():
    log.info("=== Lucr Crawler Worker 시작 ===")
    log.info("RabbitMQ 큐 대기 중... (종료: Ctrl+C)")

    try:
        consumer = CrawlConsumer()
        consumer.start()  # 무한 대기
    except KeyboardInterrupt:
        log.info("Worker 종료 (Ctrl+C)")
    except Exception as e:
        log.error(f"Worker 오류: {e}")
        raise


if __name__ == "__main__":
    main()
