import sys
from loguru import logger
from pathlib import Path


def setup_logger():
    """로거 초기 설정"""
    
    # 기본 로거 제거
    logger.remove()
    
    # 콘솔 출력 (개발 환경)
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # 파일 출력 (운영 환경)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger.add(
        "logs/crawler_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 매일 자정에 새 파일
        retention="30 days",  # 30일 보관
        compression="zip",  # 압축
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG"
    )
    
    logger.info("Logger initialized successfully")
    return logger


# 전역 로거 인스턴스
log = setup_logger()