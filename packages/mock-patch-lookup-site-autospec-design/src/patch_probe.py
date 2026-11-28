"""mock.patch lookup site와 autospec 차이를 보여주는 시나리오를 실행한다.

실행: python3 src/patch_probe.py
"""

from __future__ import annotations

import sys
from unittest import mock

import invoice_from_import
import invoice_injected
import invoice_qualified
import rate_source


def probe_lookup_site() -> dict[str, float]:
    """패치 대상 위치에 따른 효과를 비교한다.

    Returns:
        시나리오별 결과 딕셔너리
    """
    result: dict[str, float] = {}

    # 진짜 함수 호출 (기준)
    result["real_from_import"] = invoice_from_import.convert(10.0, "USD")
    result["real_qualified"] = invoice_qualified.convert(10.0, "USD")

    # 시나리오 A: 정의 모듈 패치 + from-import 사용 (효과 없음)
    with mock.patch("rate_source.fetch_rate", return_value=2.0):
        result["patch_definition_from_import"] = invoice_from_import.convert(
            10.0, "USD"
        )

    # 시나리오 A: 정의 모듈 패치 + 모듈 속성 접근 사용 (효과 있음)
    with mock.patch("rate_source.fetch_rate", return_value=2.0):
        result["patch_definition_qualified"] = invoice_qualified.convert(10.0, "USD")

    # 시나리오 B: 사용 위치 패치 + from-import (효과 있음)
    with mock.patch("invoice_from_import.fetch_rate", return_value=2.0):
        result["patch_usage_from_import"] = invoice_from_import.convert(10.0, "USD")

    # 시나리오 B: 사용 위치 패치 + 모듈 속성 접근 (효과 없음)
    with mock.patch("invoice_from_import.fetch_rate", return_value=2.0):
        result["patch_usage_qualified"] = invoice_qualified.convert(10.0, "USD")

    return result


def probe_signature_drift() -> dict[str, str]:
    """기본 Mock과 autospec의 시그니처 드리프트 탐지 차이를 비교한다.

    Returns:
        시나리오별 결과 딕셔너리 ("pass" 또는 예외 타입 이름)
    """
    result: dict[str, str] = {}

    # 기본 Mock: 잘못된 인자 조합을 통과시킴
    with mock.patch("invoice_from_import.fetch_rate") as mock_fetch:
        try:
            invoice_from_import.convert(10.0, "USD")
            # 기본 Mock은 어떤 인자로든 호출 가능
            mock_fetch("USD", "extra", 1, 2, bogus=1)
            result["mock_wrong_args"] = "pass"
        except Exception as e:
            result["mock_wrong_args"] = type(e).__name__

    # autospec: 잘못된 인자 조합을 TypeError로 거절
    with mock.patch("invoice_from_import.fetch_rate", autospec=True):
        try:
            invoice_from_import.convert(10.0, "USD")
            # autospec Mock은 시그니처를 강제
            invoice_from_import.fetch_rate("USD", "extra")
            result["autospec_wrong_args"] = "pass"
        except Exception as e:
            result["autospec_wrong_args"] = type(e).__name__

    return result


def probe_attribute_access() -> dict[str, str]:
    """Mock과 autospec의 속성 접근 차이를 비교한다.

    Returns:
        시나리오별 결과 딕셔너리
    """
    result: dict[str, str] = {}

    # 기본 Mock: 임의 속성 읽기를 허용
    with mock.patch("invoice_from_import.fetch_rate") as mock_fetch:
        try:
            _ = mock_fetch.nonexistent_attribute
            result["mock_nonexistent"] = "pass"
        except Exception as e:
            result["mock_nonexistent"] = type(e).__name__

    # autospec: 존재하지 않는 속성 읽기를 AttributeError로 거절
    with mock.patch("invoice_from_import.fetch_rate", autospec=True) as mock_fetch:
        try:
            _ = mock_fetch.nonexistent_attribute
            result["autospec_nonexistent"] = "pass"
        except Exception as e:
            result["autospec_nonexistent"] = type(e).__name__

    return result


def probe_patch_typo() -> dict[str, str]:
    """패치 대상 이름 오타를 탐지한다.

    Returns:
        시나리오별 결과 딕셔너리
    """
    result: dict[str, str] = {}

    # 오타 이름 패치 (기본: AttributeError)
    try:
        with mock.patch("invoice_from_import.fetch_rat"):
            pass
        result["typo_no_create"] = "pass"
    except Exception as e:
        result["typo_no_create"] = type(e).__name__

    # 오타 이름 패치 + create=True (오류 없이 통과)
    try:
        with mock.patch("invoice_from_import.fetch_rat", create=True):
            pass
        result["typo_create"] = "pass"
    except Exception as e:
        result["typo_create"] = type(e).__name__

    return result


def probe_spec_vs_autospec() -> dict[str, str]:
    """spec=True와 autospec=True의 차이를 비교한다.

    Returns:
        시나리오별 결과 딕셔너리
    """
    result: dict[str, str] = {}

    # spec=True: 호출 인자를 검사하지 않음
    with mock.patch("invoice_from_import.fetch_rate", spec=True) as mock_fetch:
        try:
            mock_fetch("USD", "extra", 1, 2)
            result["spec_wrong_args"] = "pass"
        except Exception as e:
            result["spec_wrong_args"] = type(e).__name__

    # autospec=True: 호출 인자를 검사
    with mock.patch("invoice_from_import.fetch_rate", autospec=True) as mock_fetch:
        try:
            mock_fetch("USD", "extra", 1, 2)
            result["autospec_wrong_args"] = "pass"
        except Exception as e:
            result["autospec_wrong_args"] = type(e).__name__

    return result


def probe_injection_default_trap() -> dict[str, float]:
    """주입 설계의 기본값 함정을 보여준다.

    Returns:
        시나리오별 결과 딕셔너리
    """
    result: dict[str, float] = {}

    # 진짜 함수 호출
    result["real_default_bound"] = invoice_injected.convert_default_bound(10.0, "USD")
    result["real_none_default"] = invoice_injected.convert(10.0, "USD")

    # 정의 모듈 패치 후 기본값으로 묶인 함수 호출 (효과 없음)
    with mock.patch("rate_source.fetch_rate", return_value=2.0):
        result["patched_default_bound"] = invoice_injected.convert_default_bound(
            10.0, "USD"
        )

    # 정의 모듈 패치 후 None 기본값 함수 호출 (효과 있음)
    with mock.patch("rate_source.fetch_rate", return_value=2.0):
        result["patched_none_default"] = invoice_injected.convert(10.0, "USD")

    return result


def _format_table(title: str, data: dict[str, float | str]) -> None:
    """결과를 표로 출력한다."""
    print(f"\n## {title}\n")
    max_key_len = max(len(k) for k in data.keys())
    for key, value in data.items():
        print(f"{key:<{max_key_len}} : {value}")


if __name__ == "__main__":
    print("=== mock.patch lookup site와 autospec 비교 ===")

    lookup_result = probe_lookup_site()
    _format_table("1. 패치 대상 위치에 따른 효과", lookup_result)

    drift_result = probe_signature_drift()
    _format_table("2. 시그니처 드리프트 탐지", drift_result)

    attr_result = probe_attribute_access()
    _format_table("3. 속성 접근 차이", attr_result)

    typo_result = probe_patch_typo()
    _format_table("4. 패치 대상 오타 탐지", typo_result)

    spec_result = probe_spec_vs_autospec()
    _format_table("5. spec vs autospec", spec_result)

    injection_result = probe_injection_default_trap()
    _format_table("6. 주입 설계 기본값 함정", injection_result)

    sys.exit(0)
