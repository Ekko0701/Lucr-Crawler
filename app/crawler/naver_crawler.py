import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser

from app.models.news import CrawledNews
from app.utils.logger import log


class NaverFinanceCrawler:
    """네이버 금융 뉴스 크롤러"""
    
    def __init__(self):
        self.base_url = "https://finance.naver.com"
        self.news_list_url = f"{self.base_url}/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """
        네이버 금융 뉴스 크롤링
        
        Args:
            max_news: 크롤링할 최대 뉴스 개수
            
        Returns:
            크롤링한 뉴스 리스트
        """
        log.info(f"네이버 금융 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 뉴스 목록 페이지 가져오기
                response = await client.get(self.news_list_url, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                # 수정: .articleSubject를 직접 선택
                news_items = soup.select('.articleSubject')
                
                crawled_news = []
                
                for item in news_items[:max_news]:
                    try:
                        news = await self._parse_news_item(item, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"네이버 금융 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"네이버 금융 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_news_item(self, item, client: httpx.AsyncClient) -> CrawledNews:
        """
        개별 뉴스 아이템 파싱
        
        Args:
            item: BeautifulSoup 뉴스 아이템 (dt.articleSubject)
            client: HTTP 클라이언트
            
        Returns:
            파싱된 뉴스 데이터
        """
        # 제목과 URL 추출 (item이 이미 .articleSubject이므로 a 태그만 찾기)
        title_tag = item.select_one('a')
        if not title_tag:
            return None
        
        title = title_tag.get_text(strip=True)
        news_url = title_tag.get('href', '')
        
        if not news_url:
            return None
        
        # 상대 URL을 절대 URL로 변환
        if not news_url.startswith('http'):
            news_url = self.base_url + news_url
        
        # 날짜 추출 (부모 요소에서 찾기)
        parent = item.parent
        date_tag = parent.select_one('.date') if parent else None
        published_at = self._parse_date(date_tag.get_text(strip=True) if date_tag else None)
        
        # 뉴스 상세 페이지에서 본문 가져오기
        content, image_url = await self._fetch_news_content(news_url, client)
        
        return CrawledNews(
            title=title,
            content=content,
            url=news_url,
            source="NAVER_FINANCE",
            published_at=published_at,
            image_url=image_url
        )
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        """
        뉴스 상세 페이지에서 본문과 이미지 추출
        
        Args:
            url: 뉴스 URL
            client: HTTP 클라이언트
            
        Returns:
            (본문, 이미지 URL)
        """
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 본문 추출
            content_tag = soup.select_one('#newsct_article, .news_end')
            content = content_tag.get_text(strip=True) if content_tag else "본문 없음"
            
            # 이미지 추출
            image_tag = soup.select_one('.end_photo_org img, .img_desc img')
            image_url = image_tag['src'] if image_tag and 'src' in image_tag.attrs else None
            
            return content[:5000], image_url  # 본문 최대 5000자
            
        except Exception as e:
            log.error(f"뉴스 본문 가져오기 실패 ({url}): {e}")
            return "본문 없음", None
    
    def _parse_date(self, date_str: str) -> datetime:
        """
        날짜 문자열을 datetime으로 변환
        
        Args:
            date_str: 날짜 문자열 (예: "2026.02.03 14:30")
            
        Returns:
            datetime 객체
        """
        try:
            # "2026.02.03 14:30" 형식 파싱
            return parser.parse(date_str.replace('.', '-'))
        except:
            # 파싱 실패 시 현재 시간
            return datetime.now()
