"""
StockMatcher — 뉴스에서 종목 언급 감지기

동작 원리:
    1. 초기화 시 PostgreSQL의 stocks 테이블에서 종목 데이터를 메모리에 로드
       → {종목코드: 종목명} 딕셔너리 생성
    2. 종목명과 종목코드 각각에 대해 정규식 패턴을 미리 컴파일
    3. 뉴스 텍스트에서 패턴 검색 → 언급된 종목코드와 횟수 반환

한계:
    - 종목명이 짧으면 오탐 가능 (예: "SK" → "SK하이닉스" 외 "SK에너지"도 매칭)
    - 동음이의어 처리 불가 (예: "삼성"은 삼성전자/삼성물산/삼성SDI 모두 매칭 가능)
    - 종목 데이터가 stocks 테이블에 없으면 매칭 불가

주의사항:
    - stocks 테이블에 종목 데이터가 있어야 동작합니다.
    - 데이터가 없으면 모든 뉴스에 대해 빈 딕셔너리를 반환합니다.
    - 종목 추가 후 refresh_stock_dict()를 호출해 사전을 갱신합니다.

@author Ekko0701
@since 2026-03-03
"""

import re
from typing import Optional
from app.utils.logger import log


class StockMatcher:
    """
    뉴스 텍스트에서 종목 언급을 감지하는 매처

    초기화 시 DB에서 종목 사전을 로드합니다.
    크롤링 세션 동안 사전을 메모리에 유지하여 DB 쿼리를 최소화합니다.

    사용 예시:
        matcher = StockMatcher()
        result = matcher.match("삼성전자 실적 호조, SK하이닉스도 강세")
        # result → {"005930": 1, "000660": 1}
        #           삼성전자     SK하이닉스
    """

    # 종목 언급을 확인할 최소 종목명 길이
    # 너무 짧은 이름(예: "LG", "SK")은 오탐 가능성이 높습니다.
    MIN_STOCK_NAME_LENGTH = 2

    def __init__(self):
        """
        StockMatcher 초기화

        PostgreSQL stocks 테이블에서 종목 사전을 로드합니다.
        종목 데이터가 없으면 경고만 출력하고 빈 사전으로 초기화합니다.
        (stocks 테이블이 비어 있어도 다른 분석 모듈은 정상 동작합니다.)
        """
        self._stock_dict: dict[str, str] = {}   # {종목코드: 종목명}
        self._patterns: list[tuple[str, re.Pattern]] = []  # [(종목코드, 패턴)]
        self.refresh_stock_dict()

    def refresh_stock_dict(self):
        """
        PostgreSQL에서 종목 데이터를 다시 로드하고 정규식 패턴을 재컴파일합니다.

        언제 호출하나:
            - 새 종목이 추가된 경우
            - 종목명이 변경된 경우
            - Worker 재시작 없이 사전을 갱신하고 싶은 경우
        """
        try:
            from app.config.database import SessionLocal
            from sqlalchemy import text

            session = SessionLocal()
            try:
                # stocks 테이블에서 종목코드와 종목명 조회
                # Stock.java: code (PK, 종목코드), name (종목명)
                result = session.execute(
                    text("SELECT code, name FROM stocks ORDER BY LENGTH(name) DESC")
                ).fetchall()

                self._stock_dict = {row[0]: row[1] for row in result}

                # 종목명 길이 내림차순 정렬로 쿼리함:
                # "삼성전자우"보다 "삼성전자"가 먼저 매칭되는 문제를 방지하기 위해
                # 긴 이름부터 정렬합니다.
                # 예: "삼성전자우"가 먼저 패턴에 등록되어야 "삼성전자우" 언급이
                #     "삼성전자"로 잘못 집계되지 않습니다.

            finally:
                session.close()

            # 정규식 패턴 컴파일
            self._patterns = []
            for code, name in self._stock_dict.items():
                # 너무 짧은 이름은 오탐 방지를 위해 건너뜁니다.
                if len(name) < self.MIN_STOCK_NAME_LENGTH:
                    continue

                # 패턴: 종목명 또는 종목코드 (6자리 숫자)
                # \b: 단어 경계 (앞뒤에 한글/숫자가 아닌 문자가 있어야 매칭)
                # 한국어는 \b가 완벽히 동작하지 않으므로 look-around를 사용합니다.
                name_pattern = re.compile(
                    r"(?<![가-힣a-zA-Z])" + re.escape(name) + r"(?![가-힣a-zA-Z])"
                )
                code_pattern = re.compile(r"\b" + re.escape(code) + r"\b")

                self._patterns.append((code, name_pattern))
                self._patterns.append((code, code_pattern))

            log.info(
                f"종목 사전 로드 완료: {len(self._stock_dict)}개 종목, "
                f"{len(self._patterns)}개 패턴"
            )

        except Exception as e:
            log.warning(
                f"종목 사전 로드 실패: {e}\n"
                f"→ 종목 매칭 기능을 사용하려면 stocks 테이블에 데이터가 있어야 합니다.\n"
                f"→ 'POST /api/v1/stocks'로 종목을 먼저 등록하세요."
            )
            self._stock_dict = {}
            self._patterns = []

    def match(self, text: str) -> dict[str, int]:
        """
        뉴스 텍스트에서 종목 언급을 감지합니다.

        Args:
            text: 뉴스 텍스트 (제목 + 본문 권장)

        Returns:
            {종목코드: 언급횟수} 딕셔너리
            예: {"005930": 3, "000660": 1}
            언급된 종목이 없으면 빈 딕셔너리 반환

        주의:
            동일 뉴스에서 "삼성전자"와 "005930(종목코드)"을 모두 언급하면
            각각 1회씩 카운트됩니다. 총 2회가 아닌 1회로 집계하려면
            코드 패턴을 제거하거나 중복 처리 로직을 추가해야 합니다.
        """
        if not text or not self._patterns:
            return {}

        mention_counts: dict[str, int] = {}

        for code, pattern in self._patterns:
            matches = pattern.findall(text)
            if matches:
                mention_counts[code] = mention_counts.get(code, 0) + len(matches)

        if mention_counts:
            log.debug(f"종목 감지: {mention_counts}")

        return mention_counts

    def match_batch(self, texts: list[str]) -> list[dict[str, int]]:
        """
        여러 뉴스 텍스트의 종목 언급을 일괄 감지합니다.

        Args:
            texts: 뉴스 텍스트 리스트

        Returns:
            각 뉴스별 {종목코드: 언급횟수} 딕셔너리 리스트 (입력 순서 보장)
        """
        return [self.match(text) for text in texts]

    def get_stock_name(self, code: str) -> Optional[str]:
        """
        종목코드로 종목명을 조회합니다.

        Args:
            code: 종목코드 (예: "005930")

        Returns:
            종목명 (예: "삼성전자") 또는 None (코드 없음)
        """
        return self._stock_dict.get(code)

    @property
    def stock_count(self) -> int:
        """로드된 종목 수를 반환합니다."""
        return len(self._stock_dict)