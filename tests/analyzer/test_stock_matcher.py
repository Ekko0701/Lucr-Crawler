"""
StockMatcher 단위 테스트.

핵심 전략:
- 실제 DB/SQLAlchemy/psycopg2 없이 동작하도록 import 경계를 통째로 stub 처리한다.
- match 규칙(이름/코드 카운트, 짧은 종목명 제외, 예외 폴백)을 검증한다.
"""

import sys
from types import SimpleNamespace

from app.analyzer.stock_matcher import StockMatcher


class DummyResult:
    """session.execute(...).fetchall() 결과를 흉내내는 객체."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class DummySession:
    """StockMatcher가 기대하는 최소 세션 인터페이스 execute/close 제공."""

    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def execute(self, _query):
        # query 내용은 테스트에서 중요하지 않으므로 무시한다.
        return DummyResult(self._rows)

    def close(self):
        self.closed = True


def _install_stock_dependencies(monkeypatch, session_local):
    # StockMatcher.refresh_stock_dict()는 함수 내부에서 아래 모듈을 import한다.
    # - app.config.database.SessionLocal
    # - sqlalchemy.text
    # 테스트에서는 실제 모듈 import 시 psycopg2 등이 필요해지므로,
    # sys.modules에 최소 기능만 가진 가짜 모듈을 주입해 격리한다.
    monkeypatch.setitem(
        sys.modules,
        "app.config.database",
        SimpleNamespace(SessionLocal=session_local),
    )
    monkeypatch.setitem(
        sys.modules,
        "sqlalchemy",
        SimpleNamespace(text=lambda query: query),
    )


def _patch_session_local(monkeypatch, rows):
    # 정상 DB 응답 시나리오를 간단히 세팅하기 위한 헬퍼.
    _install_stock_dependencies(monkeypatch, lambda: DummySession(rows))


def test_match_counts_mentions_by_name_and_code(monkeypatch):
    # 2개 종목을 사전에 로드하고, 본문에 종목명+코드가 함께 등장하는 케이스를 검증한다.
    rows = [
        ("005930", "삼성전자"),
        ("000660", "SK하이닉스"),
    ]
    _patch_session_local(monkeypatch, rows)

    matcher = StockMatcher()
    text = "삼성전자, 005930 강세. SK하이닉스 반등."
    result = matcher.match(text)

    # 005930은 종목명 1회 + 코드 1회 -> 총 2회
    assert result["005930"] == 2
    # 000660은 종목명으로 1회만 등장
    assert result["000660"] == 1


def test_short_name_is_excluded_from_pattern(monkeypatch):
    # 길이 1의 종목명은 MIN_STOCK_NAME_LENGTH 규칙에 의해 패턴 생성에서 제외되어야 한다.
    rows = [
        ("123456", "A"),
        ("005930", "삼성전자"),
    ]
    _patch_session_local(monkeypatch, rows)

    matcher = StockMatcher()
    result = matcher.match("A 와 삼성전자 언급")

    # "A"는 종목명 패턴이 생성되지 않으므로 매칭되면 안 된다.
    assert "123456" not in result
    assert result["005930"] == 1


def test_match_returns_empty_when_text_is_blank(monkeypatch):
    # 입력 텍스트가 비어 있으면 매칭을 수행하지 않고 빈 dict를 반환해야 한다.
    rows = [("005930", "삼성전자")]
    _patch_session_local(monkeypatch, rows)

    matcher = StockMatcher()

    assert matcher.match("") == {}


def test_refresh_stock_dict_fallback_on_exception(monkeypatch):
    # DB 연결/조회 실패 시 refresh_stock_dict는 예외를 삼키고
    # 내부 사전/패턴을 빈 상태로 초기화하는 폴백 경로를 가진다.
    def broken_session_local():
        raise RuntimeError("db unavailable")

    _install_stock_dependencies(monkeypatch, broken_session_local)

    matcher = StockMatcher()

    assert matcher.stock_count == 0
    assert matcher.match("삼성전자") == {}


def test_get_stock_name_and_stock_count(monkeypatch):
    # 보조 API(get_stock_name, stock_count)가 로딩된 사전을 기준으로 동작하는지 검증한다.
    rows = [
        ("005930", "삼성전자"),
        ("000660", "SK하이닉스"),
    ]
    _patch_session_local(monkeypatch, rows)

    matcher = StockMatcher()

    assert matcher.stock_count == 2
    assert matcher.get_stock_name("005930") == "삼성전자"
    assert matcher.get_stock_name("999999") is None
