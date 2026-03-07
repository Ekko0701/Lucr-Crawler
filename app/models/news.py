"""
Pydantic 모델 정의

CrawledNews 분석 결과 필드:
  - sentiment_score: 감정 분석 점수 (-1.00 ~ 1.00)
  - keywords:        TF-IDF 키워드 리스트
  - stock_codes:     종목코드별 언급 횟수 딕셔너리

@author Ekko0701
@since 2026-03-03
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NewsCreate(BaseModel):
    """Spring API로 보낼 뉴스 생성 DTO"""
    title: str = Field(..., min_length=5, max_length=500)
    content: str = Field(..., min_length=1)
    url: str = Field(..., max_length=2000)
    source: str = Field(..., max_length=50)
    published_at: datetime
    image_url: Optional[str] = Field(None, max_length=2000)
    sentiment_score: Optional[Decimal] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }


class CrawledNews(BaseModel):
    """
    크롤링한 원본 뉴스 데이터

    분석 결과 필드:
        sentiment_score: SentimentAnalyzer가 계산한 감정 점수
                         None이면 분석 전 또는 분석 실패 상태
        keywords:        KeywordExtractor가 추출한 키워드 리스트
                         빈 리스트이면 분석 전 또는 추출 실패
        stock_codes:     StockMatcher가 집계한 종목별 언급 횟수
                         빈 딕셔너리이면 관련 종목 없음 또는 분석 전

    기존 크롤러 호환성:
        3개 신규 필드에 기본값(None/[]/{ })을 설정하므로
        기존 6개 크롤러 코드를 수정하지 않아도 됩니다.
    """
    title: str
    content: str
    url: str
    source: str
    published_at: datetime
    image_url: Optional[str] = None

    # ── 분석 결과 필드 ──
    sentiment_score: Optional[float] = None
    keywords: List[str] = Field(default_factory=list)
    stock_codes: Dict[str, int] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def to_create_dto(self) -> NewsCreate:
        """Spring API 요청용 DTO로 변환 (sentiment_score 포함)"""
        sentiment = None
        if self.sentiment_score is not None:
            # float -> Decimal 변환 + 범위 보장 (-1.0 ~ 1.0)
            clamped = max(-1.0, min(1.0, self.sentiment_score))
            sentiment = Decimal(str(round(clamped, 2)))

        return NewsCreate(
            title=self.title,
            content=self.content,
            url=self.url,
            source=self.source,
            published_at=self.published_at,
            image_url=self.image_url,
            sentiment_score=sentiment,
        )
