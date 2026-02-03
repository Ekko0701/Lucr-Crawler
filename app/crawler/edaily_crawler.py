import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List

from app.models.news import CrawledNews
from app.utils.logger import log


class EdailyCrawler:
    """이데일리 뉴스 크롤러"""
    
    def __init__(self):
        self.base_url = "https://www.edaily.co.kr"
        self.news_list_url = f"{self.base_url}/news/newsList.asp?newsType=politics&DirCode=0010"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """이데일리 뉴스 크롤링"""
        log.info(f"이데일리 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.news_list_url, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                news_items = soup.select('.newslist li, .articlelist li')
                
                crawled_news = []
                
                for item in news_items[:max_news]:
                    try:
                        news = await self._parse_news_item(item, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"이데일리 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"이데일리 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_news_item(self, item, client: httpx.AsyncClient) -> CrawledNews:
        """개별 뉴스 아이템 파싱"""
        title_tag = item.select_one('a')
        if not title_tag:
            return None
        
        title = title_tag.get_text(strip=True)
        news_url = title_tag.get('href', '')
        
        if not news_url:
            return None
        
        if not news_url.startswith('http'):
            news_url = self.base_url + news_url
        
        published_at = datetime.now()
        content, image_url = await self._fetch_news_content(news_url, client)
        
        return CrawledNews(
            title=title,
            content=content,
            url=news_url,
            source="EDAILY",
            published_at=published_at,
            image_url=image_url
        )
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        """뉴스 본문 추출"""
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            content_tag = soup.select_one('.news_body, .newsContents, #newsBody')
            content = content_tag.get_text(strip=True) if content_tag else "본문 없음"
            
            image_tag = soup.select_one('.news_photo img')
            image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else None
            
            return content[:5000], image_url
        except Exception as e:
            log.error(f"이데일리 본문 가져오기 실패: {e}")
            return "본문 없음", None
