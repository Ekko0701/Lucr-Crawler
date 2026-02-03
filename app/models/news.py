from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal


class NewsCreate(BaseModel):
    """Spring API로 보낼 뉴스 생성 DTO"""
    title: str = Field(..., min_length=5, max_length=500)
    content: str = Field(..., min_length=1)  # 10 → 1로 완화
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
    """크롤링한 원본 뉴스 데이터"""
    title: str
    content: str
    url: str
    source: str
    published_at: datetime
    image_url: Optional[str] = None
    
    def to_create_dto(self) -> NewsCreate:
        """Spring API 요청용 DTO로 변환"""
        return NewsCreate(
            title=self.title,
            content=self.content,
            url=self.url,
            source=self.source,
            published_at=self.published_at,
            image_url=self.image_url
        )
