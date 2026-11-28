"""주입 설계로 의존 함수를 받는 모듈.

패치 없이 테스트할 수 있지만, 기본값을 함정으로 묶으면 패치가 안 먹는다.
"""

from __future__ import annotations

from collections.abc import Callable

import rate_source


def convert_default_bound(
    amount: float,
    currency: str,
    *,
    fetch_rate: Callable[[str], float] = rate_source.fetch_rate,
) -> float:
    """함정: 기본값을 정의 시점에 묶는다.

    이후 rate_source.fetch_rate를 패치해도 이 함수의 기본값은 바뀌지 않는다.

    Args:
        amount: 금액
        currency: 통화 코드
        fetch_rate: 환율 조회 함수 (기본값: 정의 시점의 rate_source.fetch_rate)

    Returns:
        USD 금액
    """
    rate = fetch_rate(currency)
    return amount * rate


def convert(
    amount: float,
    currency: str,
    *,
    fetch_rate: Callable[[str], float] | None = None,
) -> float:
    """권장: 기본값을 None으로 두고 호출 시점에 조회한다.

    이후 rate_source.fetch_rate를 패치하면 이 함수도 패치된 함수를 쓴다.

    Args:
        amount: 금액
        currency: 통화 코드
        fetch_rate: 환율 조회 함수 (None이면 호출 시점의 rate_source.fetch_rate)

    Returns:
        USD 금액
    """
    if fetch_rate is None:
        fetch_rate = rate_source.fetch_rate
    rate = fetch_rate(currency)
    return amount * rate
