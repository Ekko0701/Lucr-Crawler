"""
크롤링 완료 이벤트 Publisher (Python → RabbitMQ → Spring)

역할:
  크롤링이 끝나면 Spring에 "완료했어, 총 N건 저장했어"라는 이벤트를 발행합니다.
  Spring 측의 CrawlResultListener(미구현)가 이 메시지를 수신하여
  관리자 알림, 캐시 갱신 등 후속 처리를 수행합니다.

메시지 흐름:
  publish() 호출
    → Python dict → JSON 문자열로 직렬화 (json.dumps)
    → pika로 RabbitMQ에 연결
    → Exchange(lucr.crawl.exchange)에 "crawl.result" Routing Key로 발행
    → RabbitMQ가 Binding 규칙에 따라 Result Queue(lucr.crawl.result)로 라우팅
    → Spring Listener가 큐에서 메시지를 소비

Spring 측 대응:
  - Exchange: RabbitMQConfig.CRAWL_EXCHANGE ("lucr.crawl.exchange")
  - Routing Key: RabbitMQConfig.CRAWL_RESULT_KEY ("crawl.result")
  - Queue: RabbitMQConfig.CRAWL_RESULT_QUEUE ("lucr.crawl.result")

@author Ekko0701
@since 2026-02-06
"""
import pika
import json
import os
from dotenv import load_dotenv

from app.utils.logger import log

load_dotenv()


class CrawlResultPublisher:
    """
    크롤링 완료 이벤트를 RabbitMQ로 발행하는 Publisher

    Spring의 CrawlJobPublisher와 대칭적인 역할:
      - Spring CrawlJobPublisher: 요청 발행 (crawl.request)
      - Python CrawlResultPublisher: 결과 발행 (crawl.result)

    매 publish() 호출마다 새 연결을 생성하고 닫습니다.
    크롤링 완료 시 1번만 호출되므로 연결 풀 없이 단순 구조로 충분합니다.
    """

    # ── Spring RabbitMQConfig.java와 동일한 상수 ──
    # Exchange: 메시지 라우터. Routing Key를 보고 적절한 Queue에 전달
    EXCHANGE = "lucr.crawl.exchange"
    # Routing Key: Exchange가 이 키를 보고 lucr.crawl.result Queue로 라우팅
    ROUTING_KEY = "crawl.result"

    def __init__(self):
        """
        RabbitMQ 연결 파라미터 초기화

        .env에서 읽어오는 값:
          - RABBITMQ_HOST: RabbitMQ 서버 주소 (기본: localhost)
          - RABBITMQ_PORT: AMQP 포트 (기본: 5672, 관리 UI는 15672)
          - RABBITMQ_USER: 인증 사용자명
          - RABBITMQ_PASSWORD: 인증 비밀번호

        PlainCredentials: 평문 사용자/비밀번호 인증 방식
        ConnectionParameters: 연결 시 사용할 호스트/포트/인증 정보를 묶은 객체
        """
        credentials = pika.PlainCredentials(
            os.getenv("RABBITMQ_USER", "charlie0701"),
            os.getenv("RABBITMQ_PASSWORD", "alpha5059"),
        )
        self.params = pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            credentials=credentials,
        )

    def publish(self, job_id: str, status: str,
                total_articles: int = 0, media_results: dict = None):
        """
        크롤링 완료/실패 이벤트를 RabbitMQ에 발행

        Args:
            job_id:         작업 UUID (Spring이 생성한 CrawlJob의 ID)
            status:         "COMPLETED" (성공) 또는 "FAILED" (실패)
            total_articles: 전체 언론사에서 수집된 총 기사 수
            media_results:  언론사별 수집 결과 dict
                            예: {"hankyung": 45, "mk": 38, ...}

        발행되는 JSON 메시지 예시:
        {
            "jobId": "550e8400-e29b-41d4-a716-446655440000",
            "status": "COMPLETED",
            "totalArticles": 245,
            "mediaResults": {"hankyung": 45, "mk": 38, "edaily": 42, ...}
        }

        주의: 키 이름은 camelCase (Spring Jackson이 파싱하는 형식)
        """
        # Spring이 JSON으로 역직렬화할 메시지 본문
        # 키 이름을 camelCase로 작성해야 Spring의 Jackson이 올바르게 파싱
        message = {
            "jobId": job_id,
            "status": status,
            "totalArticles": total_articles,
            "mediaResults": media_results or {},
        }

        try:
            # 1. RabbitMQ에 TCP 연결 생성
            #    BlockingConnection: 동기 방식 연결 (메시지 1개 보내고 닫으므로 적합)
            connection = pika.BlockingConnection(self.params)

            # 2. Channel 생성 (하나의 Connection 안에서 논리적 통신 경로)
            #    실제 메시지 발행/소비는 Channel을 통해 수행
            channel = connection.channel()

            # 3. 메시지 발행
            channel.basic_publish(
                exchange=self.EXCHANGE,       # 목적지 Exchange (Topic Exchange)
                routing_key=self.ROUTING_KEY,  # Exchange가 Queue를 찾는 키
                body=json.dumps(message),      # Python dict → JSON 문자열
                properties=pika.BasicProperties(
                    content_type="application/json",  # Spring이 JSON으로 인식
                    delivery_mode=2,  # 2 = persistent (메시지 영속화)
                    #   1 = transient (메모리만, RabbitMQ 재시작 시 소실)
                    #   2 = persistent (디스크 저장, RabbitMQ 재시작 시에도 유지)
                ),
            )

            # 4. 연결 종료 (리소스 해제)
            connection.close()

            log.info(f"완료 이벤트 발행: jobId={job_id}, status={status}, total={total_articles}")

        except Exception as e:
            # 연결 실패, 발행 실패 등
            # 완료 이벤트 발행 실패는 크롤링 자체에 영향을 주지 않음
            # (DB에는 이미 저장 완료된 상태)
            log.error(f"완료 이벤트 발행 실패: {e}")
