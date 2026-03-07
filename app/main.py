from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

from app.crawler.hankyung_crawler import HankyungCrawler
from app.crawler.mk_crawler import MKCrawler
from app.crawler.edaily_crawler import EdailyCrawler
from app.crawler.herald_crawler import HeraldCrawler
from app.crawler.yahoo_crawler import YahooCrawler
from app.crawler.chosunbiz_crawler import ChosunbizCrawler
from app.services.news_service import NewsService
from app.utils.logger import log

# 환경변수 로드
load_dotenv()

MAX_NEWS = int(os.getenv("MAX_NEWS_PER_SOURCE", "50"))


# 앱 라이프사이클 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 코드"""
    log.info("🚀 Lucr Crawler 시작")
    yield
    log.info("🛑 Lucr Crawler 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="Lucr News Crawler",
    description="금융 뉴스 자동 수집 시스템",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """헬스 체크"""
    return {
        "service": "Lucr News Crawler",
        "status": "running",
        "version": "1.0.0"
    }


@app.post("/crawl/hankyung")
async def crawl_hankyung_news(background_tasks: BackgroundTasks):
    """한국경제 뉴스 크롤링"""
    log.info("한국경제 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_hankyung_crawler)
    return {"message": "한국경제 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/mk")
async def crawl_mk_news(background_tasks: BackgroundTasks):
    """매일경제 뉴스 크롤링"""
    log.info("매일경제 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_mk_crawler)
    return {"message": "매일경제 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/edaily")
async def crawl_edaily_news(background_tasks: BackgroundTasks):
    """이데일리 뉴스 크롤링"""
    log.info("이데일리 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_edaily_crawler)
    return {"message": "이데일리 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/herald")
async def crawl_herald_news(background_tasks: BackgroundTasks):
    """헤럴드경제 뉴스 크롤링"""
    log.info("헤럴드경제 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_herald_crawler)
    return {"message": "헤럴드경제 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/yahoo")
async def crawl_yahoo_news(background_tasks: BackgroundTasks):
    """Yahoo Finance 뉴스 크롤링"""
    log.info("Yahoo Finance 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_yahoo_crawler)
    return {"message": "Yahoo Finance 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/chosunbiz")
async def crawl_chosunbiz_news(background_tasks: BackgroundTasks):
    """조선비즈 뉴스 크롤링"""
    log.info("조선비즈 뉴스 크롤링 요청 받음")
    background_tasks.add_task(run_chosunbiz_crawler)
    return {"message": "조선비즈 뉴스 크롤링이 시작되었습니다.", "status": "started"}


@app.post("/crawl/all")
async def crawl_all_news(background_tasks: BackgroundTasks):
    """
    모든 출처의 뉴스 크롤링
    
    Returns:
        크롤링 시작 메시지
    """
    log.info("전체 뉴스 크롤링 요청 받음")
    
    # 백그라운드에서 크롤링 실행
    background_tasks.add_task(run_all_crawlers)
    
    return {
        "message": "전체 뉴스 크롤링이 시작되었습니다 (6개 언론사).",
        "status": "started"
    }


async def run_hankyung_crawler():
    """한국경제 크롤러 실행"""
    crawler = HankyungCrawler()
    await _run_crawler(crawler, "한국경제")


async def run_mk_crawler():
    """매일경제 크롤러 실행"""
    crawler = MKCrawler()
    await _run_crawler(crawler, "매일경제")


async def run_edaily_crawler():
    """이데일리 크롤러 실행"""
    crawler = EdailyCrawler()
    await _run_crawler(crawler, "이데일리")


async def run_herald_crawler():
    """헤럴드경제 크롤러 실행"""
    crawler = HeraldCrawler()
    await _run_crawler(crawler, "헤럴드경제")


async def run_yahoo_crawler():
    """Yahoo Finance 크롤러 실행"""
    crawler = YahooCrawler()
    await _run_crawler(crawler, "Yahoo Finance")


async def run_chosunbiz_crawler():
    """조선비즈 크롤러 실행"""
    crawler = ChosunbizCrawler()
    await _run_crawler(crawler, "조선비즈")


async def _run_crawler(crawler, source_name: str):
    """
    공통 크롤러 실행 로직 (FastAPI HTTP 저장 경로).

    저장 방식:
      - CrawledNews -> NewsCreate DTO 변환 후 Spring API로 POST

    참고:
      - 실서비스의 메인 비동기 파이프라인( Spring -> RabbitMQ -> Worker )은
        `app.messaging.consumer`에서 동작하며 DB에 직접 저장한다.
    """
    news_service = NewsService()
    
    try:
        log.info(f"{source_name} 뉴스 크롤링 시작 (최대 {MAX_NEWS}개)")
        news_list = await crawler.crawl(max_news=MAX_NEWS)
        
        if not news_list:
            log.warning(f"{source_name}: 크롤링된 뉴스가 없습니다.")
            return
        
        success_count = 0
        duplicate_count = 0
        error_count = 0
        
        for news in news_list:
            try:
                if await news_service.check_url_exists(news.url):
                    log.info(f"{source_name}: 이미 존재하는 뉴스 (스킵)")
                    duplicate_count += 1
                    continue
                
                # FastAPI 경로에서만 DTO 변환 후 HTTP 전송을 수행한다.
                # Worker 경로는 이 변환 없이 DB에 직접 INSERT한다.
                news_dto = news.to_create_dto()
                result = await news_service.create_news(news_dto)
                
                if result:
                    success_count += 1
                    log.info(f"{source_name}: 뉴스 저장 성공 [{success_count}]")
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                log.error(f"{source_name}: 뉴스 처리 중 오류: {e}")
                continue
        
        log.info(f"""
        ✅ {source_name} 뉴스 크롤링 완료
        📊 크롤링: {len(news_list)}개
        ✨ 저장 성공: {success_count}개
        🔄 중복 스킵: {duplicate_count}개
        ❌ 오류: {error_count}개
        """)
        
    except Exception as e:
        log.error(f"{source_name}: 크롤러 실행 중 오류 발생: {e}")
    finally:
        await news_service.close()


async def run_all_crawlers():
    """모든 크롤러 실행"""
    log.info("=== 전체 크롤러 실행 시작 ===")
    
    # 1. 한국경제
    await run_hankyung_crawler()
    
    # 2. 매일경제
    await run_mk_crawler()
    
    # 3. 이데일리
    await run_edaily_crawler()
    
    # 4. 헤럴드경제
    await run_herald_crawler()
    
    # 5. 조선비즈
    await run_chosunbiz_crawler()
    
    # 6. Yahoo Finance
    await run_yahoo_crawler()
    
    log.info("=== 전체 크롤러 실행 완료 ===")


if __name__ == "__main__":
    import uvicorn
    
    # 개발 서버 실행
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 코드 변경 시 자동 재시작
        log_level="info"
    )
