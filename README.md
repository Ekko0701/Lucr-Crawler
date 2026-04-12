# Lucr News Crawler 📰

**금융 뉴스 자동 수집 시스템**

6개 주요 언론사의 금융/경제 뉴스를 자동으로 크롤링하여 데이터베이스에 저장합니다.

---

## 🎯 지원 언론사

### 한국 언론사 (5개)
- **한국경제** (Hankyung) - 웹 크롤링
- **매일경제** (MK) - RSS 피드
- **이데일리** (Edaily) - RSS 피드
- **헤럴드경제** (Herald) - 웹 크롤링
- **조선비즈** (Chosunbiz) - RSS 피드

### 글로벌 언론사 (1개)
- **Yahoo Finance** - Selenium (JavaScript 렌더링)

---

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate    # Windows

# Python 패키지 설치
pip install -r requirements.txt
```

`requirements.txt`에 포함된 주요 패키지:
- `fastapi` - 웹 프레임워크
- `httpx` - 비동기 HTTP 클라이언트
- `beautifulsoup4` - HTML/XML 파싱
- `selenium==4.26.1` - 브라우저 자동화
- `webdriver-manager==4.0.2` - ChromeDriver 자동 관리

### 2. Selenium 설정 (Yahoo Finance용)

#### Chrome 브라우저 설치

```bash
# macOS
brew install --cask google-chrome

# Ubuntu/Debian
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f
```

#### ChromeDriver 자동 설치

**webdriver-manager**가 첫 실행 시 자동으로 ChromeDriver를 다운로드합니다!

```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
```

**장점**:
- ✅ 수동 설치 불필요
- ✅ Chrome 버전과 자동 매칭
- ✅ 크로스 플랫폼 지원

#### 설치 확인

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Chrome 옵션 설정
chrome_options = Options()
chrome_options.add_argument('--headless')  # 백그라운드 실행
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

# ChromeDriver 자동 설치 및 브라우저 실행
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# 테스트
driver.get("https://www.google.com")
print(driver.title)  # 출력: Google
driver.quit()
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일 수정:
```env
BACKEND_URL=http://localhost:8080/api/news
MAX_NEWS_PER_SOURCE=50
```

### 4. 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 크롤링 실행

```bash
# 전체 크롤러 실행 (6개 언론사)
curl -X POST http://localhost:8000/crawl/all

# 개별 크롤러 실행
curl -X POST http://localhost:8000/crawl/hankyung
curl -X POST http://localhost:8000/crawl/yahoo
```

---

## 📖 API 문서

### Swagger UI

서버 실행 후 접속:
```
http://localhost:8000/docs
```

### 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 헬스 체크 |
| POST | `/crawl/all` | 전체 크롤러 실행 (6개) |
| POST | `/crawl/hankyung` | 한국경제 크롤링 |
| POST | `/crawl/mk` | 매일경제 크롤링 |
| POST | `/crawl/edaily` | 이데일리 크롤링 |
| POST | `/crawl/herald` | 헤럴드경제 크롤링 |
| POST | `/crawl/chosunbiz` | 조선비즈 크롤링 |
| POST | `/crawl/yahoo` | Yahoo Finance 크롤링 |

---

## 🏗 프로젝트 구조

```
Lucr-Crawler/
├── app/
│   ├── crawler/              # 크롤러 모듈
│   │   ├── hankyung_crawler.py
│   │   ├── mk_crawler.py
│   │   ├── edaily_crawler.py
│   │   ├── herald_crawler.py
│   │   ├── chosunbiz_crawler.py
│   │   └── yahoo_crawler.py
│   ├── models/               # 데이터 모델
│   │   └── news.py
│   ├── services/             # 비즈니스 로직
│   │   └── news_service.py
│   ├── utils/                # 유틸리티
│   │   └── logger.py
│   └── main.py               # FastAPI 앱
├── Documents/
│   ├── Crawler/
│   │   ├── AllMediaCrawlers.md  # 전체 크롤러 문서
│   │   └── KoreanMediaCrawlers.md
│   └── 크롤러_테스트_가이드.md
├── requirements.txt
└── README.md
```

---

## 🔧 기술 스택

### 프레임워크
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **Uvicorn**: ASGI 서버

### 크롤링
- **httpx**: 비동기 HTTP 클라이언트
- **BeautifulSoup4**: HTML/XML 파싱
- **lxml**: 고속 파서
- **Selenium**: 브라우저 자동화 (JavaScript 렌더링)
- **webdriver-manager**: ChromeDriver 자동 관리

### 데이터 처리
- **Pydantic**: 데이터 검증
- **python-dateutil**: 날짜 파싱
- **loguru**: 구조화된 로깅

---

## 📊 성능 지표

| 항목 | 값 |
|------|-----|
| **평균 수집량** | ~280개/실행 (6개 언론사) |
| **실행 시간** | 3-7분 (전체) |
| **메모리 사용** | ~400MB (Selenium 포함) |
| **CPU 사용** | 중간 |

### 크롤러별 성능

| 크롤러 | 방식 | 속도 | 수집량 |
|--------|------|------|--------|
| 한국경제 | 웹 | 빠름 | ~50 |
| 매일경제 | RSS | 매우 빠름 | ~50 |
| 이데일리 | RSS | 매우 빠름 | ~50 |
| 헤럴드경제 | 웹 | 빠름 | ~40 |
| 조선비즈 | RSS | 매우 빠름 | ~40 |
| Yahoo | Selenium | 느림 | ~25 |

---

## 🐳 Docker 배포

```dockerfile
FROM python:3.11-slim

# Chrome 설치
RUN apt-get update && apt-get install -y \
    wget gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🧪 테스트

```bash
# 서버 상태 확인
curl http://localhost:8000/

# 개별 크롤러 테스트
curl -X POST http://localhost:8000/crawl/hankyung

# 전체 크롤러 테스트
curl -X POST http://localhost:8000/crawl/all

# 로그 확인
tail -f logs/crawler.log
```

---

## 🛠 문제 해결

### Selenium 오류

**ChromeDriver 버전 불일치**:
```bash
# webdriver-manager가 자동으로 처리하므로 재설치
pip uninstall webdriver-manager
pip install webdriver-manager==4.0.2
```

**Headless 모드에서 실패**:
```python
# 디버깅을 위해 headless 모드 비활성화
# chrome_options.add_argument('--headless')  # 주석 처리
```

**메모리 부족**:
```python
# 이미지 로드 비활성화
prefs = {"profile.managed_default_content_settings.images": 2}
chrome_options.add_experimental_option("prefs", prefs)
```

### 크롤링 실패

**타임아웃**:
- `requirements.txt`의 `httpx` 타임아웃 설정 확인
- 네트워크 연결 상태 확인

**셀렉터 변경**:
- 사이트 구조가 변경되면 CSS 선택자 업데이트 필요
- 해당 크롤러 파일의 `content_selectors` 수정

---

## 📚 문서

- [전체 크롤러 문서](./Documents/Crawler/AllMediaCrawlers.md)
- [테스트 가이드](./Documents/크롤러_테스트_가이드.md)

---

## 🤝 기여

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

---

---

**버전**: 2.0  
**최종 업데이트**: 2026-02-03
