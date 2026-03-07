"""
KeywordExtractor — TF-IDF 기반 한국어 키워드 추출기

동작 원리:
    1. kiwipiepy로 각 뉴스 텍스트를 형태소 분석 → 명사(NNG, NNP) 추출
    2. 불용어(stopwords) 필터링 (1글자 명사, 의미없는 단어 제거)
    3. 추출된 명사 리스트를 TF-IDF 행렬로 변환
    4. 각 뉴스에서 TF-IDF 점수 상위 N개 키워드 반환

주의:
    TF-IDF는 '여러 문서 집합' 안에서의 상대적 중요도를 측정합니다.
    문서가 1건뿐이면 IDF 값이 의미없어지므로 배치(batch) 단위로 처리합니다.
    최소 3건 이상의 뉴스를 함께 처리하는 것을 권장합니다.

@author Ekko0701
@since 2026-03-03
"""

from typing import Optional
from app.utils.logger import log


class KeywordExtractor:
    """
    TF-IDF 기반 한국어 뉴스 키워드 추출기

    한 번 초기화하면 여러 배치 처리에 재사용합니다.
    kiwipiepy Kiwi 인스턴스는 생성 비용이 크므로 싱글턴처럼 관리합니다.

    사용 예시:
        extractor = KeywordExtractor()

        texts = [
            "삼성전자 3분기 영업이익 10조 돌파, 반도체 실적 호조",
            "현대차 전기차 판매 급증, 글로벌 점유율 확대",
        ]
        keywords_per_news = extractor.extract_batch(texts, top_n=5)
        # [
        #   ["삼성전자", "영업이익", "반도체", "실적", "분기"],
        #   ["현대차", "전기차", "판매", "점유율", "글로벌"],
        # ]
    """

    # ── 불용어 목록 ──────────────────────────────────────────────────
    # 한국어 뉴스에서 자주 등장하지만 키워드로 의미없는 단어들입니다.
    # 형태소 분석 후 명사만 걸러내지만, 이 목록으로 추가 필터링합니다.
    STOPWORDS = {
        # 시간/날짜
        "오늘", "어제", "내일", "이번", "지난", "다음", "올해", "작년",
        "올해", "내년", "최근", "현재", "당시", "이후", "이전", "기간",
        "연간", "분기", "반기", "월간", "일간", "주간",

        # 일반 명사
        "것", "수", "때", "중", "등", "및", "더", "또", "이",
        "그", "저", "씩", "곳", "점", "면", "건", "개", "명",
        "경우", "통해", "따라", "위해", "위한", "대한", "관련",
        "관련해", "대해", "대하여", "대비", "기준", "대상", "측면",

        # 기관/직함 (너무 일반적인 것)
        "정부", "국회", "당국", "관계자", "측", "팀", "부서",
        "대표", "사장", "회장", "부회장", "이사", "임원",

        # 뉴스 관련
        "기자", "뉴스", "보도", "발표", "언급", "강조", "설명",
        "밝혔다", "말했다", "했다", "이다", "된다", "있다",
        "취재", "인터뷰", "기사", "보고", "자료",

        # 수량/비율 (숫자와 함께 오지만 단독으로 의미없는 것)
        "억", "조", "만", "천", "백", "퍼센트", "프로", "배",
        "달러", "원", "위안", "엔", "유로",
    }

    def __init__(self):
        """
        KeywordExtractor 초기화

        kiwipiepy Kiwi 모델을 로드합니다.
        최초 초기화 시 딥러닝 모델 파일을 로드하므로 1~3초 소요됩니다.
        이후 추출은 빠르게 동작합니다.
        """
        try:
            from kiwipiepy import Kiwi
            # Kiwi() 생성 시 딥러닝 언어 모델을 로드합니다.
            # num_workers=0: 멀티프로세싱 비활성화 (단일 스레드 환경에서 안전)
            self._kiwi = Kiwi(num_workers=0)
            log.info("Kiwi 형태소 분석기 초기화 완료")
        except ImportError:
            log.error(
                "kiwipiepy가 설치되지 않았습니다. "
                "'pip install kiwipiepy==0.22.2'을 실행하세요."
            )
            raise

    def _extract_nouns(self, text: str) -> list[str]:
        """
        텍스트에서 명사를 추출합니다.

        kiwipiepy의 형태소 분석 결과에서 일반명사(NNG)와 고유명사(NNP)만 선택합니다.
        불용어와 1글자 명사는 제거합니다.

        Args:
            text: 분석할 텍스트

        Returns:
            명사 리스트 (중복 포함 — TF 계산에 필요)

        kiwipiepy 품사 태그:
            NNG: 일반명사 (예: 주가, 실적, 반도체)
            NNP: 고유명사 (예: 삼성전자, 현대차, 코스피)
            그 외: 동사(VV), 형용사(VA), 조사(JX) 등 → 제외
        """
        if not text or not text.strip():
            return []

        nouns = []
        try:
            # kiwi.tokenize(): 텍스트를 형태소 단위로 분석
            # 결과: List[Token], Token.form = 형태소, Token.tag = 품사 태그
            tokens = self._kiwi.tokenize(text)
            for token in tokens:
                # NNG(일반명사) 또는 NNP(고유명사)만 선택
                if token.tag in ("NNG", "NNP"):
                    noun = token.form
                    # 필터링 조건:
                    # 1. 2글자 이상 (1글자 명사는 의미 불명확)
                    # 2. 불용어 목록에 없음
                    # 3. 순수 숫자가 아님 (예: "2024", "100")
                    if (
                        len(noun) >= 2
                        and noun not in self.STOPWORDS
                        and not noun.isdigit()
                    ):
                        nouns.append(noun)
        except Exception as e:
            log.warning(f"형태소 분석 실패: {e}")

        return nouns

    def extract_batch(
        self, texts: list[str], top_n: int = 10
    ) -> list[list[str]]:
        """
        여러 뉴스 텍스트에서 TF-IDF 키워드를 일괄 추출합니다.

        Args:
            texts:  뉴스 텍스트 리스트 (제목 + 본문 권장)
            top_n:  각 뉴스에서 추출할 최대 키워드 수 (기본 10)

        Returns:
            각 뉴스별 키워드 리스트 (TF-IDF 점수 내림차순 정렬)
            입력 순서와 출력 순서가 일치합니다.

        주의:
            - 입력 texts가 비어 있으면 빈 리스트를 반환합니다.
            - 텍스트 수가 너무 적으면 (< 3건) TF-IDF 의미가 희석됩니다.
        """
        if not texts:
            return []

        # 1. 각 텍스트를 형태소 분석 → 명사 추출 → 공백으로 연결
        #    TF-IDF는 단어 단위로 처리하므로 공백 구분 문자열이 필요합니다.
        corpus = []
        for text in texts:
            nouns = self._extract_nouns(text)
            # 명사가 없으면 빈 문자열 대신 더미 토큰을 넣어 TF-IDF가 오류 없이 동작하게 합니다.
            corpus.append(" ".join(nouns) if nouns else "__empty__")

        # 2. TF-IDF 행렬 계산
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            # TfidfVectorizer 설정:
            #   min_df=1: 최소 1개 문서에 등장한 단어만 포함 (기본값)
            #   max_df=0.8: 80% 이상의 문서에 등장하는 단어는 제외
            #               (너무 흔한 단어는 IDF가 낮아 키워드로 의미없음)
            #   sublinear_tf=True: TF에 log 스케일 적용 (자연 로그)
            #                      고빈도 단어의 가중치를 완화합니다.
            vectorizer = TfidfVectorizer(
                min_df=1,
                max_df=0.8,
                sublinear_tf=True,
            )

            # tfidf_matrix: (뉴스 수, 어휘 수) 형태의 희소 행렬
            tfidf_matrix = vectorizer.fit_transform(corpus)

            # 어휘 목록: index → 단어
            feature_names = vectorizer.get_feature_names_out()

        except Exception as e:
            log.error(f"TF-IDF 계산 실패: {e}")
            return [[] for _ in texts]

        # 3. 각 뉴스별 상위 top_n 키워드 추출
        import numpy as np

        results = []
        for i, row in enumerate(tfidf_matrix):
            # row.toarray(): 해당 뉴스의 TF-IDF 점수 벡터 (numpy array)
            scores = row.toarray().flatten()

            # TF-IDF 점수 내림차순으로 인덱스 정렬
            # argsort()는 오름차순이므로 [::-1]로 뒤집습니다.
            top_indices = scores.argsort()[::-1][:top_n]

            # 점수가 0보다 큰 키워드만 포함 (0이면 해당 뉴스에 등장하지 않은 단어)
            keywords = [
                feature_names[idx]
                for idx in top_indices
                if scores[idx] > 0 and feature_names[idx] != "__empty__"
            ]
            results.append(keywords)

        log.debug(
            f"키워드 추출 완료: {len(texts)}건 처리, "
            f"평균 {sum(len(k) for k in results)/max(len(results), 1):.1f}개/건"
        )
        return results

    def extract_single(self, text: str, top_n: int = 10) -> list[str]:
        """
        단일 뉴스 텍스트에서 키워드를 추출합니다.

        주의: 단일 텍스트는 TF-IDF의 IDF 계산이 불가합니다.
        이 경우 TF 기반(단순 빈도)으로 폴백합니다.

        Args:
            text:  분석할 텍스트
            top_n: 최대 키워드 수

        Returns:
            키워드 리스트 (빈도 내림차순)
        """
        nouns = self._extract_nouns(text)
        if not nouns:
            return []

        # 단순 빈도 기반 정렬 (Counter 사용)
        from collections import Counter
        counter = Counter(nouns)
        return [word for word, _ in counter.most_common(top_n)]