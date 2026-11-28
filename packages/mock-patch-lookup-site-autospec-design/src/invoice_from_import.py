"""from-import 방식으로 의존 함수를 가져오는 모듈.

정의 모듈(rate_source)을 패치하면 효과가 없고,
사용 위치(invoice_from_import.fetch_rate)를 패치해야 한다.
"""

from __future__ import annotations

from rate_source import fetch_rate


def convert(amount: float, currency: str) -> float:
    """금액을 USD로 변환한다.

    Args:
        amount: 금액
        currency: 통화 코드

    Returns:
        USD 금액
    """
    rate = fetch_rate(currency)
    return amount * rate
