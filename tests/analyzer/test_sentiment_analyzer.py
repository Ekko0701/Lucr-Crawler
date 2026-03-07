"""
SentimentAnalyzer 단위 테스트.

의도:
- 감정 점수의 기본 규칙(양수/음수/중립)을 빠르게 검증한다.
- 빈 입력, 공백 변형, 배치 처리 등 실전에서 자주 깨지는 경계 케이스를 고정한다.
"""

from app.analyzer.sentiment_analyzer import SentimentAnalyzer


def test_analyze_empty_and_blank_returns_zero():
    # 비어 있는 입력은 분석할 키워드가 없으므로 항상 중립(0.0)이어야 한다.
    analyzer = SentimentAnalyzer()
    assert analyzer.analyze("") == 0.0
    assert analyzer.analyze("   ") == 0.0


def test_analyze_positive_text_returns_positive_score():
    # 긍정 키워드 위주 문장에서 점수가 양수인지 확인한다.
    # 정확한 절대값보다 "방향성(positive)"이 핵심이다.
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("삼성전자 역대최대 실적 달성과 주가상승 기대")
    assert score > 0
    # 구현 상 점수는 항상 [-1, 1] 범위를 벗어나지 않아야 한다.
    assert -1.0 <= score <= 1.0


def test_analyze_negative_text_returns_negative_score():
    # 부정 키워드 위주 문장에서 점수가 음수인지 검증한다.
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("영업손실 확대와 주가하락 우려로 투자주의")
    assert score < 0
    assert -1.0 <= score <= 1.0


def test_analyze_mixed_keywords_is_near_neutral():
    # 긍정/부정 키워드가 동일하게 1개씩 잡히는 문장.
    # 공식 (pos-neg)/(pos+neg+1)에 따라 0.0이 되어야 한다.
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("호실적 발표에도 일부 사업은 적자 상태")
    assert score == 0.0


def test_analyze_supports_whitespace_variation_for_multiword_keyword():
    # 사전 키워드 "실적 개선"은 내부에서 \s* 정규식으로 컴파일된다.
    # 따라서 공백이 여러 칸이어도 동일 키워드로 매칭되어야 한다.
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze("2분기 실적    개선 기대감이 커졌다")
    assert score > 0


def test_analyze_batch_preserves_input_order():
    # analyze_batch는 리스트 컴프리헨션 기반이므로 입력 순서를 보존해야 한다.
    # 각 위치별로 positive / negative / neutral을 명확히 배치해 검증한다.
    analyzer = SentimentAnalyzer()
    texts = [
        "호실적과 주가상승",
        "적자전환과 급락",
        "단순 사실 전달 기사",
    ]
    scores = analyzer.analyze_batch(texts)

    assert len(scores) == 3
    assert scores[0] > 0
    assert scores[1] < 0
    assert scores[2] == 0.0
