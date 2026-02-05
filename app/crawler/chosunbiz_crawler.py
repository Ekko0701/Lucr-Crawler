"""
조선비즈 뉴스 크롤러 (RSS 기반)

작성자: charlie0701
작성일: 2026-02-03
"""

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser as date_parser
import re

from app.models.news import CrawledNews
from app.utils.logger import log


class ChosunbizCrawler:
    """조선비즈 뉴스 크롤러 (RSS 기반)"""
    
    def __init__(self):
        self.base_url = "https://biz.chosun.com"
        # 조선닷컴 경제 섹션 RSS 피드
        self.rss_url = "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """조선비즈 뉴스 크롤링 (RSS 피드 사용)"""
        log.info(f"조선비즈 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # RSS 피드 가져오기
                response = await client.get(self.rss_url, headers=self.headers)
                response.raise_for_status()
                
                # XML 파싱
                soup = BeautifulSoup(response.text, 'xml')
                items = soup.find_all('item')
                
                crawled_news = []
                
                for item in items[:max_news]:
                    try:
                        news = await self._parse_rss_item(item, client)
                        if news:
                            crawled_news.append(news)
                    except Exception as e:
                        log.error(f"조선비즈 뉴스 파싱 실패: {e}")
                        continue
                
                log.info(f"조선비즈 뉴스 크롤링 완료: {len(crawled_news)}개")
                return crawled_news
                
        except Exception as e:
            log.error(f"조선비즈 뉴스 크롤링 실패: {e}")
            return []
    
    async def _parse_rss_item(self, item, client: httpx.AsyncClient) -> CrawledNews:
        """RSS 아이템 파싱"""
        try:
            # RSS 기본 정보 추출
            title = item.find('title').get_text(strip=True) if item.find('title') else ""
            link = item.find('link').get_text(strip=True) if item.find('link') else ""
            description = item.find('description').get_text(strip=True) if item.find('description') else ""
            pub_date_str = item.find('pubDate').get_text(strip=True) if item.find('pubDate') else None
            
            if not title or not link:
                return None
            
            # 제목 정규화 (500자 제한)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 500:
                title = title[:500]
            
            # 날짜 파싱
            try:
                published_at = date_parser.parse(pub_date_str) if pub_date_str else datetime.now()
            except:
                published_at = datetime.now()
            
            # 본문 가져오기 (RSS description을 fallback으로 사용)
            content, image_url = await self._fetch_news_content(link, client)
            
            if not content or content == "본문 없음":
                content = description[:5000] if description else "본문 없음"
            
            return CrawledNews(
                title=title,
                content=content,
                url=link,
                source="CHOSUNBIZ",
                published_at=published_at,
                image_url=image_url
            )
            
        except Exception as e:
            log.error(f"조선비즈 RSS 아이템 파싱 오류: {e}")
            return None
    
    async def _fetch_news_content(self, url: str, client: httpx.AsyncClient) -> tuple[str, str]:
        """뉴스 본문 추출"""
        try:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 본문 추출 (여러 선택자 시도)
            content_selectors = [
                '.article-body',
                '.story-news-content',
                'article .content',
                '.news-body',
                '[itemprop="articleBody"]'
            ]
            
            content = ""
            for selector in content_selectors:
                content_tag = soup.select_one(selector)
                if content_tag:
                    content = content_tag.get_text(separator=' ', strip=True)
                    break
            
            # 이미지 추출
            image_tag = soup.select_one('.article-body img, article img, .story-news-content img')
            image_url = None
            if image_tag and 'src' in image_tag.attrs:
                image_url = image_tag['src']
                if not image_url.startswith('http'):
                    image_url = f"https:{image_url}" if image_url.startswith('//') else f"{self.base_url}{image_url}"
            
            return content[:5000] if content else "본문 없음", image_url
            
        except Exception as e:
            log.error(f"조선비즈 본문 가져오기 실패: {e}")
            return "본문 없음", None
