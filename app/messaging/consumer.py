"""
크롤링 요청 Consumer (RabbitMQ → Python)

역할:
  Spring이 RabbitMQ에 발행한 크롤링 요청 메시지를 수신하고,
  실제 크롤링을 실행한 뒤 결과를 PostgreSQL에 저장합니다.

전체 메시지 흐름:
  1. Spring CrawlJobPublisher → Exchange(lucr.crawl.exchange) → "crawl.request" 키로 발행
  2. RabbitMQ Binding 규칙에 따라 Request Queue(lucr.crawl.request)로 라우팅
  3. 이 Consumer가 Queue에서 메시지를 꺼내 처리:
     a. CrawlJob 상태를 RUNNING으로 업데이트
     b. 6개 언론사 크롤러를 순차 실행
     c. 수집된 뉴스를 PostgreSQL에 직접 저장 (HTTP 호출 없이)
     d. CrawlJob 상태를 COMPLETED / FAILED로 업데이트
     e. 완료 이벤트를 RabbitMQ에 역발행 (Publisher 사용)
  4. Spring CrawlResultListener(미구현)가 완료 이벤트 수신

ACK/NACK 메커니즘:
  - ACK  (Acknowledge):  "이 메시지 처리 완료" → RabbitMQ가 큐에서 메시지 삭제
  - NACK (Negative ACK): "이 메시지 처리 실패" → requeue=False면 DLQ로 이동 또는 폐기
  - auto_ack=False: 수동 ACK 모드. 처리 완료 후 명시적으로 ACK를 보내야 함
    → 만약 Worker가 처리 중 죽으면, ACK를 안 보냈으므로 RabbitMQ가 다른 Consumer에 재전달

@author Ekko0701
@since 2026-02-06
"""
import pika
import json
import asyncio
import os
from dotenv import load_dotenv

# ── 크롤러 import ──
# 각 언론사별 크롤러 (BaseCrawler를 상속, crawl() 메서드 구현)
from app.crawler.hankyung_crawler import HankyungCrawler    # 한국경제
from app.crawler.mk_crawler import MKCrawler                # 매일경제
from app.crawler.edaily_crawler import EdailyCrawler        # 이데일리
from app.crawler.herald_crawler import HeraldCrawler        # 헤럴드경제
from app.crawler.yahoo_crawler import YahooCrawler          # Yahoo Finance
from app.crawler.chosunbiz_crawler import ChosunbizCrawler  # 조선비즈

# ── 내부 서비스 import ──
from app.services.db_manager import DBManager               # PostgreSQL 직접 저장
from app.messaging.publisher import CrawlResultPublisher    # 완료 이벤트 발행
from app.utils.logger import log

load_dotenv()


class CrawlConsumer:
    """
    RabbitMQ 크롤링 요청 메시지를 수신하고 처리하는 Consumer

    동작 방식:
      - start()를 호출하면 RabbitMQ Queue에 연결하여 무한 대기(blocking)
      - Queue에 메시지가 들어오면 _on_message() 콜백이 자동 호출
      - _on_message()에서 크롤링 실행 → DB 저장 → 완료 이벤트 발행
      - 처리 완료 후 ACK, 실패 시 NACK

    RabbitMQ Consumer 패턴:
      Push 방식 - basic_consume()으로 콜백을 등록하면,
      RabbitMQ가 메시지를 "밀어넣어" 줍니다 (polling 아님).
    """

    # ── Spring RabbitMQConfig.CRAWL_REQUEST_QUEUE과 동일한 큐 이름 ──
    # Spring이 CrawlJobPublisher에서 "crawl.request" Routing Key로 발행하면
    # Binding 규칙에 따라 이 Queue로 도착합니다.
    QUEUE = "lucr.crawl.request"

    def __init__(self):
        """
        Consumer 초기화: RabbitMQ 연결 파라미터 + 내부 서비스 인스턴스 생성

        의존성:
          - DBManager: 크롤링된 뉴스를 PostgreSQL에 직접 저장 + CrawlJob 상태 업데이트
          - CrawlResultPublisher: 크롤링 완료/실패 이벤트를 RabbitMQ에 역발행
        """
        # PlainCredentials: 평문 사용자/비밀번호 인증
        credentials = pika.PlainCredentials(
            os.getenv("RABBITMQ_USER", "charlie0701"),
            os.getenv("RABBITMQ_PASSWORD", "alpha5059"),
        )
        # ConnectionParameters: 연결 정보를 묶은 객체 (실제 연결은 start()에서 수행)
        # heartbeat=600: 크롤링은 수 분이 걸리므로 heartbeat 간격을 10분으로 설정
        #   기본값(60초)이면 크롤링 중 heartbeat 응답을 못 보내서 RabbitMQ가 연결을 끊음
        #   BlockingConnection은 단일 스레드라 크롤링 중 heartbeat 프레임 처리 불가
        # blocked_connection_timeout=300: RabbitMQ가 flow control로 연결을 차단했을 때
        #   5분까지 대기 (기본값은 무한 대기)
        self.params = pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "localhost"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self.db = DBManager()                    # PostgreSQL 직접 조작
        self.publisher = CrawlResultPublisher()  # 완료 이벤트 Publisher

    def start(self):
        """
        Consumer를 시작하고 RabbitMQ Queue에서 메시지를 무한 대기합니다.

        이 메서드를 호출하면 다음 순서로 동작합니다:
          1. RabbitMQ에 TCP 연결 (BlockingConnection)
          2. Channel 생성 (논리적 통신 경로)
          3. Queue 선언 (이미 존재하면 무시, 없으면 생성)
          4. QoS 설정 (한 번에 처리할 메시지 수)
          5. 콜백 등록 (메시지 도착 시 _on_message 호출)
          6. 무한 대기 루프 진입 (start_consuming)

        주의:
          - start_consuming()은 블로킹 호출이므로 이 이후의 코드는 실행되지 않음
          - Worker 종료는 Ctrl+C (KeyboardInterrupt)로 수행
        """
        # 1. RabbitMQ에 TCP 연결 생성
        #    BlockingConnection: 동기 방식. Consumer처럼 장시간 연결 유지에 적합
        connection = pika.BlockingConnection(self.params)

        # 2. Channel 생성
        #    하나의 Connection 안에서 여러 Channel을 만들 수 있음
        #    Consumer는 보통 1개 Channel이면 충분
        channel = connection.channel()

        # 3. Queue 선언 (멱등 연산: 이미 존재하면 아무것도 안 함)
        #    Spring이 @Bean으로 이미 생성했지만, Python이 먼저 실행될 경우를 대비
        #    durable=True: RabbitMQ 재시작 시에도 Queue가 유지됨
        #    (Spring QueueBuilder.durable()과 동일)
        channel.queue_declare(queue=self.QUEUE, durable=True)

        # 4. QoS (Quality of Service) 설정
        #    prefetch_count=1: RabbitMQ가 이 Consumer에게 한 번에 1개 메시지만 전달
        #    → 현재 메시지를 ACK하기 전까지 다음 메시지를 보내지 않음
        #    → 크롤링은 무거운 작업이므로 1개씩 순차 처리가 안전
        #    → 만약 여러 Worker를 띄우면 Round-Robin으로 분배됨
        channel.basic_qos(prefetch_count=1)

        # 5. Consumer 등록: Queue에 메시지가 도착하면 _on_message 콜백 호출
        #    auto_ack=False (기본값): 수동 ACK 모드
        #    → _on_message에서 명시적으로 basic_ack() 또는 basic_nack() 호출 필요
        channel.basic_consume(
            queue=self.QUEUE,
            on_message_callback=self._on_message,
        )

        log.info(f"Consumer 시작: '{self.QUEUE}' 큐 대기 중...")

        # 6. 무한 대기 루프 진입
        #    Queue에 메시지가 올 때까지 블로킹
        #    메시지가 오면 _on_message 콜백이 호출되고, 처리 후 다시 대기
        channel.start_consuming()

    def _on_message(self, channel, method, properties, body):
        """
        메시지 수신 시 자동 호출되는 콜백 함수

        RabbitMQ가 Queue에서 메시지를 꺼내 이 함수의 파라미터로 전달합니다.

        Args:
            channel:    현재 사용 중인 Channel 객체
                        ACK/NACK 응답을 보내는 데 사용
            method:     메시지 전달 메타데이터
                        - method.delivery_tag: 메시지 고유 ID (ACK/NACK 시 사용)
                        - method.routing_key: 이 메시지의 Routing Key
                        - method.exchange: 이 메시지가 발행된 Exchange
            properties: 메시지 속성 (content_type, delivery_mode, headers 등)
            body:       메시지 본문 (bytes)
                        Spring이 보낸 JSON: {"jobId": "550e8400-...", "maxArticles": 50}

        처리 흐름:
            성공 시: 파싱 → RUNNING → 크롤링 → DB저장 → COMPLETED → 이벤트발행 → ACK
            실패 시: 에러캐치 → FAILED → 이벤트발행 → NACK

        ACK/NACK 설명:
            - basic_ack(delivery_tag):   "처리 완료" → RabbitMQ가 큐에서 삭제
            - basic_nack(delivery_tag, requeue=False):
              "처리 실패, 재시도 안 함" → 메시지 폐기 (DLQ 설정 시 DLQ로 이동)
            - delivery_tag: RabbitMQ가 메시지마다 부여하는 일련번호
              (같은 Channel 내에서 유일)
        """
        job_id = None
        try:
            # ── Step 1: 메시지 파싱 ──
            # body는 bytes이므로 json.loads()가 자동으로 UTF-8 디코딩
            message = json.loads(body)
            job_id = message.get("jobId")              # Spring CrawlJob의 UUID
            max_articles = message.get("maxArticles", 50)  # 언론사당 최대 수집 건수 (기본 50)

            log.info(f"크롤링 요청 수신: jobId={job_id}, maxArticles={max_articles}")

            # ── Step 2: CrawlJob 상태 → RUNNING ──
            # DB의 crawl_jobs 테이블에서 해당 Job을 PENDING → RUNNING으로 업데이트
            self.db.update_job_status(job_id, "RUNNING")

            # ── Step 3: 6개 언론사 크롤러 순차 실행 + DB 저장 ──
            # 크롤러는 async로 구현되어 있으므로 asyncio.run()으로 동기 환경에서 실행
            # asyncio.run(): 새 이벤트 루프를 생성하고, 코루틴 완료 후 루프를 닫음
            # pika의 _on_message 콜백은 동기 함수이므로 asyncio.run() 필요
            media_results = asyncio.run(self._run_all_crawlers(max_articles))

            # ── Step 4: 총 수집 건수 계산 ──
            # media_results: {"hankyung": 45, "mk": 38, ...}
            total = sum(media_results.values())

            # ── Step 5: CrawlJob 상태 → COMPLETED ──
            # 총 수집 건수와 언론사별 결과를 DB에 기록
            self.db.update_job_status(
                job_id, "COMPLETED",
                total_articles=total,
                media_results=media_results,
            )

            # ── Step 6: Spring에 완료 이벤트 발행 ──
            # Publisher를 통해 Exchange(lucr.crawl.exchange) → "crawl.result" 키로 발행
            # Spring Listener가 이 이벤트를 수신하여 후속 처리 (알림, 캐시 갱신 등)
            self.publisher.publish(job_id, "COMPLETED", total, media_results)

            # ── Step 7: ACK 전송 ──
            # "이 메시지 처리 완료"를 RabbitMQ에 알림
            # → RabbitMQ가 Queue에서 해당 메시지를 영구 삭제
            # → ACK를 보내지 않으면 RabbitMQ는 메시지를 Unacked 상태로 유지하고,
            #   Consumer가 죽으면 다른 Consumer에게 재전달
            channel.basic_ack(delivery_tag=method.delivery_tag)

            log.info(f"크롤링 완료: jobId={job_id}, total={total}")

        except Exception as e:
            log.error(f"크롤링 처리 실패: {e}")

            # ── 실패 처리 ──
            # 주의: ACK 전송 단계에서 연결 끊김(heartbeat timeout 등)으로 실패한 경우,
            # 크롤링 자체는 성공하고 DB에 COMPLETED가 이미 기록된 상태일 수 있음.
            # 이 경우 FAILED로 덮어쓰면 안 되므로, 현재 DB 상태를 확인 후 처리.
            if job_id:
                try:
                    from app.config.database import SessionLocal
                    from app.models.db_models import CrawlJobModel
                    import uuid as uuid_mod
                    session = SessionLocal()
                    current_job = session.query(CrawlJobModel).filter(
                        CrawlJobModel.id == uuid_mod.UUID(job_id)
                    ).first()
                    current_status = current_job.status if current_job else None
                    session.close()
                except Exception:
                    current_status = None

                if current_status == "COMPLETED":
                    # 이미 COMPLETED로 기록됨 → FAILED로 덮어쓰지 않음
                    log.warning(
                        f"ACK 전송 실패했으나 크롤링은 성공 (DB 상태: COMPLETED): jobId={job_id}"
                    )
                else:
                    # 실제 크롤링 실패 → FAILED 기록
                    self.db.update_job_status(job_id, "FAILED", error_message=str(e))
                    self.publisher.publish(job_id, "FAILED")

            # ── NACK 전송 ──
            # requeue=False: 이 메시지를 Queue에 다시 넣지 않음 (무한 재시도 방지)
            # → DLQ(Dead Letter Queue) 설정이 있으면 DLQ로 이동, 없으면 폐기
            # requeue=True로 하면 큐 맨 뒤에 다시 들어가지만,
            # 크롤링 실패는 재시도해도 대부분 같은 결과이므로 False가 적절
            try:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            except Exception:
                # 연결이 이미 끊어진 경우 NACK도 실패할 수 있음 → 무시
                log.warning("NACK 전송 실패 (연결 끊김)")

    async def _run_all_crawlers(self, max_articles: int) -> dict:
        """
        등록된 모든 크롤러를 순차 실행하고 언론사별 저장 건수를 반환합니다.

        실행 순서:
          1. 크롤러 인스턴스 리스트 생성
          2. 각 크롤러의 crawl() 메서드 호출 (비동기, 최대 max_articles건 수집)
          3. 수집된 뉴스를 DBManager.save_news()로 1건씩 PostgreSQL에 저장
          4. URL 중복 뉴스는 자동 스킵 (save_news에서 처리)
          5. 특정 크롤러 실패 시 해당 크롤러만 0건으로 기록, 나머지는 계속 진행

        Args:
            max_articles: 언론사당 최대 수집할 기사 수
                          예: 50이면 한경 50건, 매경 50건, ... (최대 총 300건)

        Returns:
            언론사별 성공적으로 저장된 기사 수 dict
            예: {"hankyung": 45, "mk": 38, "edaily": 42,
                 "herald": 50, "chosunbiz": 33, "yahoo": 47}
            (중복 URL로 스킵된 건수는 제외)
        """
        # 크롤러 목록: (식별자명, 크롤러 인스턴스) 튜플 리스트
        # 식별자명은 media_results dict의 키로 사용되며,
        # Spring 측에서 언론사별 결과를 구분하는 데 활용
        crawlers = [
            ("hankyung", HankyungCrawler()),     # 한국경제
            ("mk", MKCrawler()),                 # 매일경제
            ("edaily", EdailyCrawler()),          # 이데일리
            ("herald", HeraldCrawler()),          # 헤럴드경제
            ("chosunbiz", ChosunbizCrawler()),    # 조선비즈
            ("yahoo", YahooCrawler()),            # Yahoo Finance
        ]

        media_results = {}  # 언론사별 저장 건수를 누적할 dict

        for name, crawler in crawlers:
            try:
                log.info(f"{name} 크롤링 시작")

                # crawler.crawl(): 비동기 메서드로, CrawledNews 객체 리스트 반환
                # max_news: 이 언론사에서 최대 수집할 기사 수
                news_list = await crawler.crawl(max_news=max_articles)

                # 수집된 뉴스를 1건씩 DB에 저장
                # save_news()는 URL 중복 시 False를 반환하므로 성공 건수만 카운트
                success_count = 0
                for news in news_list:
                    if self.db.save_news(news):
                        success_count += 1

                media_results[name] = success_count
                log.info(f"{name} 완료: {success_count}/{len(news_list)}건 저장")

            except Exception as e:
                # 특정 크롤러 실패 시 해당 크롤러만 0건 기록
                # 나머지 크롤러는 정상 진행 (전체 중단하지 않음)
                log.error(f"{name} 크롤링 실패: {e}")
                media_results[name] = 0

        return media_results
