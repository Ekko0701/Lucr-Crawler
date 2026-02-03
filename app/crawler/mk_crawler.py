import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser

from app.models.news import CrawledNews
from app.utils.logger import log


class MKCrawler:
    """매일경제 뉴스 크롤러 (RSS 기반)"""
    
    def __init__(self):
        self.base_url = "https://www.mk.co.kr"
        # RSS 피드 URL (증권 뉴스)
        self.rss_url = "https://www.mk.co.kr/rss/50200011/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """매일경제 RSS 피드 크롤링"""
        log.info(f"매일경제 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.rss_url, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'xml')
                items = soup.find_all('item')
                
                crawled_news = []
                
                for item in items[:max_news]:
                    try:
                        news = await self._parse_rss_item(item, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"매일경제 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"매일경제 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_rss_item(self, item, client: httpx.AsyncClient) -> CrawledNews:
        """RSS 아이템 파싱"""
        title_tag = item.find('title')
        link_tag = item.find('link')
        desc_tag = item.find('description')
        pubdate_tag = item.find('pubDate')
        
        if not title_tag or not link_tag:
            return None
        
        title = title_tag.get_text(strip=True)
        news_url = link_tag.get_text(strip=True)
        
        # 설명 (요약)을 임시 본문으로 사용
        description = desc_tag.get_text(strip=True) if desc_tag else ""
        
        # 발행 시간 파싱
        published_at = datetime.now()
        if pubdate_tag:
            try:
                pubdate_str = pubdate_tag.get_text(strip=True)
                published_at = parser.parse(pubdate_str)
            except:
                pass
        
        # 상세 페이지에서 본문 가져오기
        content, image_url = await self._fetch_news_content(news_url, client)
        
        # 본문이 없으면 설명을 사용
        if content == "본문 없음" and description:
            content = description
        
        return CrawledNews(
            title=title,
            content=content,
            url=news_url,
            source="MK",
            published_at=published_at,
            image_url=image_url
        )
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        """뉴스 상세 페이지에서 본문 추출"""
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 본문 추출 시도
            content_selectors = [
                '.news_cnt_detail_wrap',
                '.art_txt',
                '#article-view-content-div',
                '.news_content'
            ]
            
            content = None
            for selector in content_selectors:
                content_tag = soup.select_one(selector)
                if content_tag:
                    content = content_tag.get_text(strip=True)
                    break
            
            if not content:
                content = "본문 없음"
            
            # 이미지 추출
            image_tag = soup.select_one('.thumb_area img, .view_img img, .news_photo img')
            image_url = image_tag.get('src') if image_tag and image_tag.get('src') else None
            
            return content[:5000], image_url
        except Exception as e:
            log.error(f"매일경제 본문 가져오기 실패 ({url}): {e}")
            return "본문 없음", None
