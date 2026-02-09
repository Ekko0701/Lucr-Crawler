"""
SQLAlchemy 모델 - Spring Entity와 동일한 테이블에 매핑

주의: 컬럼명과 타입은 Spring Entity와 정확히 일치해야 합니다.
  - News.java      → News 모델         (테이블: news)
  - CrawlJob.java  → CrawlJobModel     (테이블: crawl_jobs)

테이블은 Spring이 ddl-auto: update로 이미 생성했으므로,
Python은 기존 테이블에 매핑만 합니다.

@author Ekko0701
@since 2026-02-06
"""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.config.database import Base


class News(Base):
    """
    news 테이블 매핑 (Spring의 News Entity와 동일)

    컬럼 매핑 예시:
      Java:   @Column(name = "title", nullable = false, length = 500)
      Python: title = Column(String(500), nullable=False)
    """
    __tablename__ = "news"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    source = Column(String(100), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    view_count = Column(Integer, default=0)
    published_at = Column(DateTime)
    crawled_at = Column(DateTime, default=datetime.now)
    sentiment_score = Column(Numeric(3, 2))
    is_high_view = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CrawlJobModel(Base):
    """
    crawl_jobs 테이블 매핑 (Spring의 CrawlJob Entity와 동일)

    컬럼 매핑 예시:
      Java:   @Column(name = "status", nullable = false, length = 20)
      Python: status = Column(String(20), nullable=False, default="PENDING")
    """
    __tablename__ = "crawl_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(20), nullable=False, default="PENDING")
    total_articles = Column(Integer, default=0)
    media_results = Column(Text)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at = Column(DateTime)
