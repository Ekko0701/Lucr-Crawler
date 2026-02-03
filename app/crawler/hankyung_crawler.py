import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser

from app.models.news import CrawledNews
from app.utils.logger import log


class HankyungCrawler:
    """한국경제 뉴스 크롤러"""
    
    def __init__(self):
        self.base_url = "https://www.hankyung.com"
        self.news_list_url = f"{self.base_url}/economy"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """
        한국경제 뉴스 크롤링
        
        Args:
            max_news: 크롤링할 최대 뉴스 개수
            
        Returns:
            크롤링한 뉴스 리스트
        """
        log.info(f"한국경제 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.news_list_url, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # /article/ 링크를 가진 모든 a 태그 찾기
                article_links = soup.find_all('a', href=lambda x: x and '/article/' in x)
                
                # 중복 URL 제거 (set 사용)
                seen_urls = set()
                unique_links = []
                for link in article_links:
                    url = link.get('href', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        unique_links.append(link)
                
                log.info(f"한국경제: {len(unique_links)}개의 고유 뉴스 링크 발견")
                
                crawled_news = []
                
                for link in unique_links[:max_news]:
                    try:
                        news = await self._parse_news_link(link, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"한국경제 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"한국경제 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_news_link(self, link, client: httpx.AsyncClient) -> CrawledNews:
        """개별 뉴스 링크 파싱"""
        title = link.get_text(strip=True)
        news_url = link.get('href', '')
        
        # 제목이 없거나 너무 짧으면 스킵
        if not title or len(title) < 10:
            return None
        
        if not news_url:
            return None
        
        # 상대 경로를 절대 경로로 변환
        if not news_url.startswith('http'):
            news_url = self.base_url + news_url
        
        # 현재 시간으로 설정 (실제로는 기사 페이지에서 파싱 가능)
        published_at = datetime.now()
        
        # 본문 가져오기
        content, image_url = await self._fetch_news_content(news_url, client)
        
        return CrawledNews(
            title=title,
            content=content,
            url=news_url,
            source="HANKYUNG",
            published_at=published_at,
            image_url=image_url
        )
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        """뉴스 상세 페이지에서 본문과 이미지 추출"""
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 본문 추출 (우선순위: .article-body > #articletxt > [itemprop="articleBody"])
            content_tag = soup.select_one('.article-body')
            if not content_tag:
                content_tag = soup.select_one('#articletxt')
            if not content_tag:
                content_tag = soup.select_one('[itemprop="articleBody"]')
            
            content = content_tag.get_text(strip=True) if content_tag else "본문 없음"
            
            # 이미지 추출
            image_tag = soup.select_one('article img')
            image_url = None
            if image_tag and 'src' in image_tag.attrs:
                image_url = image_tag['src']
                # 상대 경로를 절대 경로로 변환
                if image_url and not image_url.startswith('http'):
                    image_url = self.base_url + image_url
            
            return content[:5000], image_url
            
        except Exception as e:
            log.error(f"한국경제 뉴스 본문 가져오기 실패 ({url}): {e}")
            return "본문 없음", None
