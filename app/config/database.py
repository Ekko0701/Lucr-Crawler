"""
SQLAlchemy 데이터베이스 설정

역할:
  - PostgreSQL 연결 Engine 생성
  - Session 팩토리 생성
  - 모든 SQLAlchemy 모델의 Base 클래스 정의

사용법:
  from app.config.database import SessionLocal, Base
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from dotenv import load_dotenv

load_dotenv()

# .env에서 DB 접속정보를 조합하여 연결 URL 생성
# 형식: postgresql://유저:비밀번호@호스트:포트/DB이름
DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'lucr_db')}"
)

# Engine: DB 연결 풀 관리 (앱 전체에서 1개만 생성)
# echo=False: SQL 로그 출력 안함 (True로 바꾸면 디버깅용 SQL 출력)
engine = create_engine(DATABASE_URL, echo=False)

# SessionLocal: 호출할 때마다 새 세션(트랜잭션 단위) 생성
# autocommit=False: 명시적으로 commit() 해야 반영
# autoflush=False: 명시적으로 flush() 해야 DB에 전송
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# 모든 SQLAlchemy 모델의 부모 클래스
class Base(DeclarativeBase):
    pass
