"""
Yahoo Finance 뉴스 크롤러 (Selenium 기반)

작성자: charlie0701
작성일: 2026-02-03
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from typing import List
import asyncio
import re

from app.models.news import CrawledNews
from app.utils.logger import log


class YahooCrawler:
    """Yahoo Finance 뉴스 크롤러 (Selenium 기반)"""
    
    def __init__(self):
        self.base_url = "https://finance.yahoo.com"
        self.news_list_url = f"{self.base_url}/topic/stock-market-news"
    
    def _create_driver(self):
        """Chrome 드라이버 생성"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 백그라운드 실행
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        # 자동으로 ChromeDriver 다운로드 및 설치
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        return driver
    
    async def crawl(self, max_news: int = 50) -> List[CrawledNews]:
        """Yahoo Finance 뉴스 크롤링 (Selenium 사용)"""
        log.info(f"Yahoo Finance 뉴스 크롤링 시작 (최대 {max_news}개)")
        
        crawled_news = []
        driver = None
        
        try:
            # 동기 함수를 비동기로 실행
            driver = await asyncio.to_thread(self._create_driver)
            
            # 뉴스 리스트 페이지 로드
            await asyncio.to_thread(driver.get, self.news_list_url)
            await asyncio.sleep(2)  # JavaScript 렌더링 대기
            
            # 뉴스 링크 추출
            news_links = await asyncio.to_thread(self._extract_news_links, driver)
            log.info(f"Yahoo Finance 뉴스 링크 {len(news_links)}개 발견")
            
            # 각 뉴스 기사 크롤링
            for link_info in news_links[:max_news]:
                try:
                    news = await self._fetch_news_content(driver, link_info['url'], link_info['title'])
                    if news:
                        crawled_news.append(news)
                except Exception as e:
                    log.error(f"Yahoo Finance 뉴스 파싱 실패 ({link_info['url']}): {e}")
                    continue
            
            log.info(f"Yahoo Finance 뉴스 크롤링 완료: {len(crawled_news)}개")
            return crawled_news
            
        except Exception as e:
            log.error(f"Yahoo Finance 뉴스 크롤링 실패: {e}")
            return []
        finally:
            if driver:
                await asyncio.to_thread(driver.quit)
    
    def _extract_news_links(self, driver) -> List[dict]:
        """뉴스 링크 추출"""
        try:
            # 여러 선택자 시도
            selectors = [
                'h3 a',
                'a[data-test-locator="stream-item-title"]',
                'a[href*="/news/"]'
            ]
            
            links = []
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        href = el.get_attribute('href')
                        title = el.text.strip()
                        if href and title and '/news/' in href and len(title) > 10:
                            links.append({'url': href, 'title': title})
                except:
                    continue
            
            # 중복 제거
            seen = set()
            unique_links = []
            for item in links:
                if item['url'] not in seen:
                    seen.add(item['url'])
                    unique_links.append(item)
            
            return unique_links
            
        except Exception as e:
            log.error(f"Yahoo Finance 링크 추출 실패: {e}")
            return []
    
    async def _fetch_news_content(self, driver, url: str, title: str) -> CrawledNews:
        """뉴스 본문 추출"""
        try:
            await asyncio.to_thread(driver.get, url)
            await asyncio.sleep(1.5)
            
            # 본문 추출
            content = ""
            content_selectors = [
                '.caas-body',
                'article[class*="body"]',
                '.article-wrap',
                'article'
            ]
            
            for selector in content_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    content = element.text.strip()
                    if content:
                        break
                except:
                    continue
            
            # 이미지 추출
            image_url = None
            image_selectors = [
                '.caas-img img',
                'article img',
                'img[class*="featured"]'
            ]
            
            for selector in image_selectors:
                try:
                    img_element = driver.find_element(By.CSS_SELECTOR, selector)
                    image_url = img_element.get_attribute('src')
                    if image_url:
                        break
                except:
                    continue
            
            # 제목 정규화 (500자 제한)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 500:
                title = title[:500]
            
            return CrawledNews(
                title=title,
                content=content[:5000] if content else "Content not available",
                url=url,
                source="YAHOO_FINANCE",
                published_at=datetime.now(),
                image_url=image_url
            )
            
        except Exception as e:
            log.error(f"Yahoo Finance 본문 추출 실패: {e}")
            return None
