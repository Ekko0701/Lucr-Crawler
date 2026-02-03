import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser
import re

from app.models.news import CrawledNews
from app.utils.logger import log


class HeraldCrawler:
    """헤럴드경제 뉴스 크롤러"""
    
    def __init__(self):
        self.base_url = "https://biz.heraldcorp.com"
        # 경제 뉴스 페이지
        self.news_list_url = f"{self.base_url}/economy"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """헤럴드경제 뉴스 크롤링"""
        log.info(f"헤럴드경제 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(self.news_list_url, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # 뉴스 링크 찾기 (article 페이지만)
                all_links = soup.select('a[href*="/article/"]')
                
                crawled_news = []
                seen_urls = set()
                
                for link in all_links:
                    if len(crawled_news) >= max_news:
                        break
                    
                    try:
                        href = link.get('href', '')
                        if not href or href in seen_urls:
                            continue
                        
                        # 절대 URL로 변환
                        if href.startswith('/'):
                            href = self.base_url + href
                        elif not href.startswith('http'):
                            continue
                        
                        seen_urls.add(href)
                        
                        title = link.get_text(strip=True)
                        
                        # 제목에서 날짜 패턴 제거 (예: 2026.02.03 18:34)
                        title = re.sub(r'\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}', '', title).strip()
                        
                        # 제목이 너무 길면 500자로 자르기
                        if len(title) > 500:
                            title = title[:500]
                        
                        if not title or len(title) < 10:
                            continue
                        
                        news = await self._parse_news_url(title, href, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"헤럴드경제 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"헤럴드경제 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_news_url(self, title: str, url: str, client: httpx.AsyncClient) -> CrawledNews:
        """뉴스 URL에서 상세 정보 추출"""
        published_at = datetime.now()
        content, image_url, pub_date = await self._fetch_news_content(url, client)
        
        if pub_date:
            published_at = pub_date
        
        return CrawledNews(
            title=title,
            content=content,
            url=url,
            source="HERALD",
            published_at=published_at,
            image_url=image_url
        )
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str, datetime]:
        """뉴스 상세 페이지에서 본문 추출"""
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 본문 추출 시도
            content_selectors = [
                '.article_view',
                '#articleText',
                '.article_txt',
                '.article_body'
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
            image_tag = soup.select_one('.article_photo img, .art_photo img, img[src*="wimg.herald"]')
            image_url = image_tag.get('src') if image_tag and image_tag.get('src') else None
            
            # 발행 시간 추출
            pub_date = None
            date_tag = soup.select_one('.article_date, .date, time')
            if date_tag:
                try:
                    date_str = date_tag.get_text(strip=True)
                    # "2025.11.18 09:35" 형식 파싱
                    pub_date = parser.parse(date_str.replace('.', '-'))
                except:
                    pass
            
            return content[:5000], image_url, pub_date
        except Exception as e:
            log.error(f"헤럴드경제 본문 가져오기 실패 ({url}): {e}")
            return "본문 없음", None, None
