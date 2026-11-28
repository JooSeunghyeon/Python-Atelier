"""mock.patch lookup site와 autospec 설계를 검증한다."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import invoice_from_import
import invoice_injected
import invoice_qualified
import rate_source
from patch_probe import (
    probe_attribute_access,
    probe_injection_default_trap,
    probe_lookup_site,
    probe_patch_typo,
    probe_signature_drift,
    probe_spec_vs_autospec,
)


class TestRealFunctionBehavior(unittest.TestCase):
    """진짜 함수의 정상 동작을 고정한다."""

    def test_fetch_rate_known_currencies(self) -> None:
        """알려진 통화의 환율을 돌려준다."""
        self.assertEqual(rate_source.fetch_rate("USD"), 1.0)
        self.assertEqual(rate_source.fetch_rate("EUR"), 1.1)
        self.assertEqual(rate_source.fetch_rate("GBP"), 1.3)
        self.assertEqual(rate_source.fetch_rate("JPY"), 0.0091)

    def test_fetch_rate_unknown_currency(self) -> None:
        """알 수 없는 통화는 UnknownCurrency를 낸다."""
        with self.assertRaises(rate_source.UnknownCurrency) as cm:
            rate_source.fetch_rate("XXX")
        self.assertIn("알 수 없는 통화", str(cm.exception))
        self.assertIn("XXX", str(cm.exception))

    def test_fetch_rate_timeout_parameter(self) -> None:
        """timeout 인자를 받는다."""
        # 호출 가능성만 확인 (네트워크 없음)
        result = rate_source.fetch_rate("USD", timeout=2.0)
        self.assertEqual(result, 1.0)

    def test_convert_from_import(self) -> None:
        """from-import 방식의 convert가 올바른 값을 돌려준다."""
        self.assertEqual(invoice_from_import.convert(10.0, "USD"), 10.0)
        self.assertEqual(invoice_from_import.convert(10.0, "EUR"), 11.0)

    def test_convert_qualified(self) -> None:
        """모듈 속성 접근 방식의 convert가 올바른 값을 돌려준다."""
        self.assertEqual(invoice_qualified.convert(10.0, "USD"), 10.0)
        self.assertEqual(invoice_qualified.convert(10.0, "GBP"), 13.0)

    def test_convert_injected(self) -> None:
        """주입 설계의 convert가 올바른 값을 돌려준다."""
        self.assertEqual(invoice_injected.convert(10.0, "USD"), 10.0)
        self.assertEqual(invoice_injected.convert(10.0, "JPY"), 0.091)

    def test_convert_with_custom_fetcher(self) -> None:
        """주입 설계에 사용자 정의 fetcher를 넘길 수 있다."""
        def custom_fetcher(currency: str) -> float:
            return 5.0

        result = invoice_injected.convert(10.0, "USD", fetch_rate=custom_fetcher)
        self.assertEqual(result, 50.0)


class TestLookupSiteSuccess(unittest.TestCase):
    """패치 대상 위치에 따른 효과를 고정한다."""

    def test_patch_definition_qualified_works(self) -> None:
        """정의 모듈 패치는 모듈 속성 접근 방식에 효과가 있다."""
        with mock.patch("rate_source.fetch_rate", return_value=2.0):
            result = invoice_qualified.convert(10.0, "USD")
            self.assertEqual(result, 20.0)

    def test_patch_usage_from_import_works(self) -> None:
        """사용 위치 패치는 from-import 방식에 효과가 있다."""
        with mock.patch("invoice_from_import.fetch_rate", return_value=2.0):
            result = invoice_from_import.convert(10.0, "USD")
            self.assertEqual(result, 20.0)

    def test_patch_usage_qualified_no_effect(self) -> None:
        """사용 위치 패치는 모듈 속성 접근 방식에 효과가 없다."""
        with mock.patch("invoice_from_import.fetch_rate", return_value=2.0):
            result = invoice_qualified.convert(10.0, "USD")
            self.assertEqual(result, 10.0)  # 진짜 값

    def test_injection_works_without_patch(self) -> None:
        """주입 설계는 패치 없이 테스트할 수 있다."""
        def mock_fetcher(currency: str) -> float:
            return 3.0

        result = invoice_injected.convert(10.0, "USD", fetch_rate=mock_fetcher)
        self.assertEqual(result, 30.0)


class TestLookupSiteSilentFailure(unittest.TestCase):
    """조용한 실패를 고정한다."""

    def test_patch_definition_from_import_no_effect(self) -> None:
        """정의 모듈 패치는 from-import 방식에 효과가 없다(조용한 실패)."""
        with mock.patch("rate_source.fetch_rate", return_value=2.0):
            result = invoice_from_import.convert(10.0, "USD")
            self.assertEqual(result, 10.0)  # 진짜 값이 나옴

    def test_default_mock_accepts_wrong_args(self) -> None:
        """기본 Mock은 잘못된 인자 조합을 통과시킨다."""
        with mock.patch("invoice_from_import.fetch_rate") as mock_fetch:
            # 진짜 시그니처: fetch_rate(currency, *, timeout=1.0)
            # 하지만 기본 Mock은 어떤 인자로든 호출 가능
            mock_fetch("USD", "extra", 1, 2, bogus=1)  # 오류 없음

    def test_create_true_hides_typo(self) -> None:
        """create=True는 오타 이름을 통과시킨다."""
        with mock.patch("invoice_from_import.fetch_rat", create=True):
            pass  # 오류 없음

    def test_spec_true_does_not_check_args(self) -> None:
        """spec=True는 인자 수를 검사하지 않는다."""
        with mock.patch("invoice_from_import.fetch_rate", spec=True) as mock_fetch:
            mock_fetch("USD", "extra", 1, 2)  # 오류 없음

    def test_injection_default_bound_trap(self) -> None:
        """기본값으로 묶인 주입은 패치 후에도 진짜 함수를 부른다."""
        with mock.patch("rate_source.fetch_rate", return_value=2.0):
            result = invoice_injected.convert_default_bound(10.0, "USD")
            self.assertEqual(result, 10.0)  # 진짜 값이 나옴


class TestAutospecDefense(unittest.TestCase):
    """autospec이 오류를 드러내는 경우를 고정한다."""

    def test_autospec_rejects_wrong_args(self) -> None:
        """autospec은 잘못된 인자 조합을 TypeError로 거절한다."""
        with mock.patch("invoice_from_import.fetch_rate", autospec=True):
            with self.assertRaises(TypeError):
                invoice_from_import.fetch_rate("USD", "extra")

    def test_autospec_rejects_nonexistent_attribute(self) -> None:
        """autospec은 존재하지 않는 속성 읽기를 AttributeError로 거절한다."""
        with mock.patch("invoice_from_import.fetch_rate", autospec=True) as mock_fetch:
            with self.assertRaises(AttributeError):
                _ = mock_fetch.nonexistent

    def test_patch_target_typo_raises(self) -> None:
        """패치 대상 이름 오타는 AttributeError를 낸다."""
        with self.assertRaises(AttributeError) as cm:
            with mock.patch("invoice_from_import.fetch_rat"):
                pass
        self.assertIn("fetch_rat", str(cm.exception))

    def test_injection_none_default_works_after_patch(self) -> None:
        """None 기본값 주입은 패치 후 패치된 함수를 쓴다."""
        with mock.patch("rate_source.fetch_rate", return_value=2.0):
            result = invoice_injected.convert(10.0, "USD")
            self.assertEqual(result, 20.0)


class TestSignatureDrift(unittest.TestCase):
    """시그니처 드리프트를 고정한다."""

    def test_signature_drift_mock_passes(self) -> None:
        """기본 Mock은 시그니처가 바뀌어도 테스트를 통과시킨다."""
        # 시나리오: 정의 함수에 새 키워드 인자가 추가되었지만,
        # 사용 코드는 낡은 규약으로 부른다.
        # 기본 Mock 패치는 이런 불일치를 통과시킨다.
        
        # 새 시그니처를 가진 함수
        def new_fetch_rate(currency: str, *, timeout: float = 1.0, retries: int = 3) -> float:
            return 1.0

        # 원본 함수를 임시로 교체
        original_fetch = rate_source.fetch_rate
        rate_source.fetch_rate = new_fetch_rate
        
        try:
            # 기본 Mock 패치: 낡은 호출 방식도 통과
            with mock.patch.object(invoice_qualified, "rate_source") as mock_module:
                mock_module.fetch_rate = mock.MagicMock(return_value=2.0)
                # 호출 코드가 낡은 규약(retries 없이)으로 부르지만 오류 없음
                result = invoice_qualified.convert(10.0, "USD")
                self.assertEqual(result, 20.0)
        finally:
            rate_source.fetch_rate = original_fetch

    def test_signature_drift_autospec_fails(self) -> None:
        """autospec은 시그니처가 바뀌면 TypeError를 낸다."""
        # 시나리오: 정의 함수에 필수 인자가 추가되었지만,
        # 사용 코드는 낡은 규약으로 부른다.
        # autospec 패치는 이런 불일치를 TypeError로 드러낸다.
        
        # 필수 인자가 추가된 새 시그니처를 가진 함수
        def new_fetch_rate(currency: str, region: str, *, timeout: float = 1.0) -> float:
            return 1.0

        # 원본 함수를 임시로 교체
        original_fetch = rate_source.fetch_rate
        rate_source.fetch_rate = new_fetch_rate
        invoice_from_import.fetch_rate = new_fetch_rate
        
        try:
            # autospec 패치: 필수 인자가 부족하면 TypeError
            with mock.patch.object(invoice_from_import, "fetch_rate", autospec=True):
                with self.assertRaises(TypeError) as cm:
                    # 호출 코드가 낡은 규약(region 없이)으로 부르면 TypeError
                    invoice_from_import.convert(10.0, "USD")
                # 메시지는 버전마다 다를 수 있으므로 TypeError만 확인
        finally:
            rate_source.fetch_rate = original_fetch
            invoice_from_import.fetch_rate = original_fetch


class TestPatchRestoration(unittest.TestCase):
    """패치가 복원되는 지점을 고정한다."""

    def test_with_exit_restores_original(self) -> None:
        """with 블록을 벗어나면 원래 함수로 복원된다."""
        original = rate_source.fetch_rate
        with mock.patch("rate_source.fetch_rate", return_value=2.0):
            self.assertIsNot(rate_source.fetch_rate, original)
        self.assertIs(rate_source.fetch_rate, original)

    def test_exception_still_restores(self) -> None:
        """예외가 나도 with 종료 시 복원된다."""
        original = rate_source.fetch_rate
        try:
            with mock.patch("rate_source.fetch_rate", return_value=2.0):
                self.assertIsNot(rate_source.fetch_rate, original)
                raise ValueError("test exception")
        except ValueError:
            pass
        self.assertIs(rate_source.fetch_rate, original)

    def test_nested_patch_restoration_order(self) -> None:
        """중첩 패치는 역순으로 복원된다."""
        original = rate_source.fetch_rate
        with mock.patch("rate_source.fetch_rate", return_value=1.0):
            first_mock = rate_source.fetch_rate
            with mock.patch("rate_source.fetch_rate", return_value=2.0):
                second_mock = rate_source.fetch_rate
                self.assertIsNot(second_mock, first_mock)
            # 안쪽 패치가 먼저 복원됨
            self.assertIs(rate_source.fetch_rate, first_mock)
        # 바깥쪽 패치가 나중에 복원됨
        self.assertIs(rate_source.fetch_rate, original)


class TestDecoratorArgumentOrder(unittest.TestCase):
    """데코레이터 여러 개의 인자 순서를 고정한다."""

    def test_multiple_decorators_bottom_up(self) -> None:
        """@mock.patch 데코레이터를 여러 개 쌓으면 아래부터 순서대로 인자가 들어온다."""
        @mock.patch("rate_source.fetch_rate", return_value=2.0)
        @mock.patch("invoice_from_import.fetch_rate", return_value=3.0)
        def test_func(mock_invoice: mock.MagicMock, mock_rate: mock.MagicMock) -> None:
            # 아래 데코레이터(rate_source)가 첫 인자, 위 데코레이터(invoice_from_import)가 둘째 인자
            self.assertEqual(mock_rate.return_value, 2.0)
            self.assertEqual(mock_invoice.return_value, 3.0)

        test_func()


class TestMockCallAssertions(unittest.TestCase):
    """Mock 호출 단언을 고정한다."""

    def test_assert_called_once_with_timeout(self) -> None:
        """timeout 인자 전달을 assert_called_once_with로 확인한다."""
        with mock.patch("rate_source.fetch_rate", return_value=1.0) as mock_fetch:
            invoice_qualified.convert(10.0, "USD")
            mock_fetch.assert_called_once_with("USD")

    def test_assert_called_with_explicit_timeout(self) -> None:
        """명시 timeout 인자를 확인한다."""
        with mock.patch("rate_source.fetch_rate", return_value=1.0) as mock_fetch:
            rate_source.fetch_rate("EUR", timeout=5.0)
            mock_fetch.assert_called_once_with("EUR", timeout=5.0)


class TestBoundaryConditions(unittest.TestCase):
    """경계 조건을 고정한다."""

    def test_amount_zero(self) -> None:
        """amount가 0이면 결과도 0이다."""
        result = invoice_from_import.convert(0.0, "EUR")
        self.assertEqual(result, 0.0)

    def test_amount_negative(self) -> None:
        """amount가 음수면 결과도 음수다."""
        result = invoice_from_import.convert(-10.0, "GBP")
        self.assertEqual(result, -13.0)

    def test_amount_bool_true(self) -> None:
        """bool(True)은 1.0으로 계산된다."""
        result = invoice_from_import.convert(True, "USD")
        self.assertEqual(result, 1.0)

    def test_amount_bool_false(self) -> None:
        """bool(False)은 0.0으로 계산된다."""
        result = invoice_from_import.convert(False, "USD")
        self.assertEqual(result, 0.0)

    def test_unknown_currency_propagates(self) -> None:
        """알 수 없는 통화는 UnknownCurrency를 전파한다."""
        with self.assertRaises(rate_source.UnknownCurrency):
            invoice_from_import.convert(10.0, "XXX")


class TestProbeScenarios(unittest.TestCase):
    """probe 함수들의 시나리오를 고정한다."""

    def test_probe_lookup_site(self) -> None:
        """probe_lookup_site가 예상 키와 값을 돌려준다."""
        result = probe_lookup_site()
        self.assertEqual(result["real_from_import"], 10.0)
        self.assertEqual(result["real_qualified"], 10.0)
        self.assertEqual(result["patch_definition_from_import"], 10.0)  # 효과 없음
        self.assertEqual(result["patch_definition_qualified"], 20.0)  # 효과 있음
        self.assertEqual(result["patch_usage_from_import"], 20.0)  # 효과 있음
        self.assertEqual(result["patch_usage_qualified"], 10.0)  # 효과 없음

    def test_probe_signature_drift(self) -> None:
        """probe_signature_drift가 예상 결과를 돌려준다."""
        result = probe_signature_drift()
        self.assertEqual(result["mock_wrong_args"], "pass")
        self.assertEqual(result["autospec_wrong_args"], "TypeError")

    def test_probe_attribute_access(self) -> None:
        """probe_attribute_access가 예상 결과를 돌려준다."""
        result = probe_attribute_access()
        self.assertEqual(result["mock_nonexistent"], "pass")
        self.assertEqual(result["autospec_nonexistent"], "AttributeError")

    def test_probe_patch_typo(self) -> None:
        """probe_patch_typo가 예상 결과를 돌려준다."""
        result = probe_patch_typo()
        self.assertEqual(result["typo_no_create"], "AttributeError")
        self.assertEqual(result["typo_create"], "pass")

    def test_probe_spec_vs_autospec(self) -> None:
        """probe_spec_vs_autospec이 예상 결과를 돌려준다."""
        result = probe_spec_vs_autospec()
        self.assertEqual(result["spec_wrong_args"], "pass")
        self.assertEqual(result["autospec_wrong_args"], "TypeError")

    def test_probe_injection_default_trap(self) -> None:
        """probe_injection_default_trap이 예상 결과를 돌려준다."""
        result = probe_injection_default_trap()
        self.assertEqual(result["real_default_bound"], 10.0)
        self.assertEqual(result["real_none_default"], 10.0)
        self.assertEqual(result["patched_default_bound"], 10.0)  # 효과 없음
        self.assertEqual(result["patched_none_default"], 20.0)  # 효과 있음


if __name__ == "__main__":
    unittest.main()
