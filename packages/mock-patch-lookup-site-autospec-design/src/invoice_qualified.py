"""모듈 속성 접근 방식으로 의존 함수를 호출하는 모듈.

정의 모듈(rate_source.fetch_rate)을 패치하면 효과가 있다.
"""

from __future__ import annotations

import rate_source


def convert(amount: float, currency: str) -> float:
    """금액을 USD로 변환한다.

    Args:
        amount: 금액
        currency: 통화 코드

    Returns:
        USD 금액
    """
    rate = rate_source.fetch_rate(currency)
    return amount * rate
