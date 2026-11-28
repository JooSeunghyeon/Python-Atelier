"""환율 조회 의존 함수를 제공한다.

테스트에서 패치 대상이 되는 함수를 담는다.
"""

from __future__ import annotations


class UnknownCurrency(ValueError):
    """알 수 없는 통화 코드가 주어졌을 때 발생하는 예외."""

    pass


_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.1,
    "GBP": 1.3,
    "JPY": 0.0091,
}


def fetch_rate(currency: str, *, timeout: float = 1.0) -> float:
    """통화 코드에 대한 환율을 돌려준다.

    Args:
        currency: 통화 코드 (대문자, 예: "USD")
        timeout: 타임아웃 초 (기본값 1.0, 테스트에서 전달 여부 확인용)

    Returns:
        환율 (USD 대비)

    Raises:
        UnknownCurrency: 알 수 없는 통화 코드
    """
    if currency not in _RATES:
        raise UnknownCurrency(f"알 수 없는 통화: {currency}")
    return _RATES[currency]
