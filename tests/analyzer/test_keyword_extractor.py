"""
KeywordExtractor 단위 테스트.

핵심 전략:
- 형태소 분석기(kiwipiepy), TF-IDF(sklearn) 같은 외부 의존성은 전부 stub/mock 처리한다.
- 테스트는 "입력 텍스트 -> 추출 결과" 규칙 검증에만 집중한다.
"""

import sys
from types import SimpleNamespace

from app.analyzer.keyword_extractor import KeywordExtractor


class DummyKiwi:
    """KeywordExtractor가 기대하는 최소 Kiwi 인터페이스만 흉내낸 테스트 더블."""

    def __init__(self, tokens):
        self._tokens = tokens

    def tokenize(self, _text):
        # 실제 형태소 분석 대신, 테스트가 지정한 토큰 목록을 그대로 반환한다.
        return self._tokens


def _install_fake_kiwi(monkeypatch, tokens):
    # KeywordExtractor.__init__에서 `from kiwipiepy import Kiwi`를 수행하므로
    # sys.modules에 가짜 모듈을 주입해 import 경로 자체를 테스트용으로 대체한다.
    fake_module = SimpleNamespace(Kiwi=lambda num_workers=0: DummyKiwi(tokens))
    monkeypatch.setitem(sys.modules, "kiwipiepy", fake_module)


def test_extract_nouns_filters_stopwords_digits_and_single_char(monkeypatch):
    # 다양한 잡음 토큰을 섞어두고, 최종적으로 의미 있는 명사만 남는지 확인한다.
    tokens = [
        SimpleNamespace(form="삼성전자", tag="NNP"),
        SimpleNamespace(form="실적", tag="NNG"),
        SimpleNamespace(form="오늘", tag="NNG"),   # STOPWORDS에 포함
        SimpleNamespace(form="100", tag="NNG"),   # 숫자 토큰
        SimpleNamespace(form="가", tag="NNG"),     # 1글자 명사
        SimpleNamespace(form="급등", tag="VV"),    # 명사가 아닌 품사
    ]
    _install_fake_kiwi(monkeypatch, tokens)

    extractor = KeywordExtractor()
    nouns = extractor._extract_nouns("dummy")

    # 필터링 통과 대상: 2글자 이상 + 명사 + stopword 아님 + 숫자 아님
    assert nouns == ["삼성전자", "실적"]


def test_extract_nouns_returns_empty_for_blank_text(monkeypatch):
    # 빈 문자열/공백 문자열은 tokenize를 호출하더라도 결과가 빈 리스트여야 한다.
    _install_fake_kiwi(monkeypatch, [])
    extractor = KeywordExtractor()

    assert extractor._extract_nouns("") == []
    assert extractor._extract_nouns("   ") == []


def test_extract_single_uses_frequency_order(monkeypatch):
    # extract_single은 TF-IDF가 아니라 Counter 빈도 정렬 경로를 탄다.
    _install_fake_kiwi(monkeypatch, [])
    extractor = KeywordExtractor()
    # 형태소 분석기 결과를 직접 고정해서 순수 빈도 로직만 검증한다.
    extractor._extract_nouns = lambda _text: ["A", "B", "A", "C", "A", "B"]

    keywords = extractor.extract_single("irrelevant", top_n=2)

    # A(3회), B(2회), C(1회) -> 상위 2개는 A, B
    assert keywords == ["A", "B"]


def test_extract_batch_returns_empty_list_for_empty_input(monkeypatch):
    # 배치 입력 자체가 비어 있으면 조기 반환해야 한다.
    _install_fake_kiwi(monkeypatch, [])
    extractor = KeywordExtractor()

    assert extractor.extract_batch([]) == []


def test_extract_batch_returns_empty_keywords_when_tfidf_fails(monkeypatch):
    # TF-IDF 계산 중 예외가 나면 구현은 `[[] for _ in texts]`로 폴백한다.
    _install_fake_kiwi(monkeypatch, [])
    extractor = KeywordExtractor()
    extractor._extract_nouns = lambda _text: ["삼성전자", "실적"]

    class BrokenVectorizer:
        """fit_transform 호출 시 강제로 예외를 발생시키는 더블."""

        def __init__(self, *args, **kwargs):
            pass

        def fit_transform(self, _corpus):
            raise RuntimeError("boom")

    import sklearn.feature_extraction.text as text_module

    monkeypatch.setattr(text_module, "TfidfVectorizer", BrokenVectorizer)

    result = extractor.extract_batch(["a", "b", "c"], top_n=3)

    # 입력 길이(3)에 맞춰 빈 키워드 목록 3개가 반환되어야 한다.
    assert result == [[], [], []]


def test_extract_batch_excludes_empty_placeholder(monkeypatch):
    # 구현은 명사가 없는 문서에 "__empty__" 더미 토큰을 넣어 TF-IDF를 계산한다.
    # 하지만 최종 결과에는 이 플레이스홀더가 노출되면 안 된다.
    _install_fake_kiwi(monkeypatch, [])
    extractor = KeywordExtractor()

    mapping = {
        "t1": ["삼성전자", "실적"],
        "t2": [],
        "t3": ["반도체", "실적"],
    }
    extractor._extract_nouns = lambda text: mapping[text]

    result = extractor.extract_batch(["t1", "t2", "t3"], top_n=5)

    assert len(result) == 3
    # 명사가 없던 두 번째 문서 결과에도 "__empty__"는 포함되면 안 된다.
    assert "__empty__" not in result[1]
