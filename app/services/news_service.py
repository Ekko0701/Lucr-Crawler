import httpx
import os
from typing import Optional
from dotenv import load_dotenv

from app.models.news import NewsCreate
from app.utils.logger import log

# 환경변수 로드
load_dotenv()

SPRING_API_URL = os.getenv("SPRING_API_URL", "http://localhost:8081")


class NewsService:
    """Spring Backend API 통신 서비스"""
    
    def __init__(self):
        self.base_url = SPRING_API_URL
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def check_url_exists(self, url: str) -> bool:
        """
        URL 중복 확인
        
        Args:
            url: 확인할 뉴스 URL
            
        Returns:
            True: 이미 존재, False: 존재하지 않음
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/news/exists",
                params={"url": url}
            )
            
            if response.status_code == 200:
                data = response.json()
                exists = data.get("data", False)
                log.debug(f"URL 존재 여부 확인: {url} → {exists}")
                return exists
            else:
                log.warning(f"URL 확인 실패 (status: {response.status_code}): {url}")
                return False
                
        except Exception as e:
            log.error(f"URL 확인 중 오류 발생: {e}")
            return False
    
    async def create_news(self, news: NewsCreate) -> Optional[dict]:
        """
        Spring API로 뉴스 생성 요청
        
        Args:
            news: 생성할 뉴스 데이터
            
        Returns:
            생성된 뉴스 정보 또는 None
        """
        try:
            # Pydantic 모델을 JSON으로 변환
            news_dict = news.model_dump(mode='json')
            
            response = await self.client.post(
                f"{self.base_url}/api/v1/news",
                json=news_dict,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 201:
                result = response.json()
                log.info(f"뉴스 생성 성공: {news.title[:30]}...")
                return result.get("data")
            elif response.status_code == 409:
                log.warning(f"중복된 URL (이미 존재): {news.url}")
                return None
            else:
                log.error(f"뉴스 생성 실패 (status: {response.status_code}): {response.text}")
                return None
                
        except Exception as e:
            log.error(f"뉴스 생성 중 오류 발생: {e}")
            return None
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.client.aclose()