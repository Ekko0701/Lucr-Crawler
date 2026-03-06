"""
analyzer 패키지 — Phase 2 AI/NLP 분석 모듈

포함 모듈:
    SentimentAnalyzer  : 뉴스 감정 분석 (금융 감성 사전 기반)
    KeywordExtractor   : TF-IDF 키워드 추출 (kiwipiepy 형태소 분석)
    StockMatcher       : 종목명/코드 언급 감지 (정규식 + DB 사전)

사용 예시:
    from app.analyzer import SentimentAnalyzer, KeywordExtractor, StockMatcher

    analyzer  = SentimentAnalyzer()
    extractor = KeywordExtractor()
    matcher   = StockMatcher(db_session)

    score    = analyzer.analyze("삼성전자 실적 호조로 주가 급등")
    keywords = extractor.extract(["삼성전자 실적 호조로 주가 급등", ...])
    stocks   = matcher.match("삼성전자 실적 호조로 주가 급등")

@author Ekko0701
@since 2026-03-03
"""

from app.analyzer.sentiment_analyzer import SentimentAnalyzer
from app.analyzer.keyword_extractor import KeywordExtractor
from app.analyzer.stock_matcher import StockMatcher

__all__ = ["SentimentAnalyzer", "KeywordExtractor", "StockMatcher"]