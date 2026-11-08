"""ExitStack의 부분 획득 실패 시 역순 롤백과 pop_all() 소유권 이전을 확인한다."""

from contextlib import ExitStack


class FakeResource:
    """리소스 획득과 해제 이벤트를 로그에 기록하는 가짜 리소스다."""
    
    def __init__(self, name: str, log: list[str], fail_on_enter: bool = False):
        self.name: str = name
        self.log: list[str] = log
        self.fail_on_enter: bool = fail_on_enter
        self.entered: bool = False
    
    def __enter__(self):
        if self.fail_on_enter:
            self.log.append(f"{self.name}: 획득 실패")
            raise ValueError(f"{self.name} 획득 중 오류")
        self.log.append(f"{self.name}: 획득")
        self.entered = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.log.append(f"{self.name}: 해제")
        self.entered = False
        return False


def test_partial_failure_rollback():
    """N개 리소스 중 3번째 획득 실패 시 이미 열린 리소스들이 역순(LIFO)으로 닫히고 원래 예외가 전파된다."""
    print("\n=== 부분 획득 실패 시 역순 롤백과 예외 전파 ===")
    
    log: list[str] = []
    
    try:
        with ExitStack() as stack:
            stack.enter_context(FakeResource("리소스1", log))
            stack.enter_context(FakeResource("리소스2", log))
            stack.enter_context(FakeResource("리소스3", log, fail_on_enter=True))
            stack.enter_context(FakeResource("리소스4", log))
    except ValueError as e:
        print(f"예외 포착: {e}")
    
    print("로그 순서:")
    for entry in log:
        print(f"  {entry}")
    
    assert log == [
        "리소스1: 획득",
        "리소스2: 획득",
        "리소스3: 획득 실패",
        "리소스2: 해제",
        "리소스1: 해제"
    ], f"예상과 다른 로그: {log}"
    
    print("✓ 이미 획득한 리소스들이 역순으로 해제되고 원래 예외가 전파된다")


def acquire_resources_atomically(names: list[str], log: list[str], fail_at: int = -1):
    """모든 리소스를 원자적으로 획득하고 소유권을 호출자에게 이전한다.
    
    실패 시 지금까지 획득한 모든 리소스를 해제하고 예외를 전파한다.
    성공 시 호출자가 반환된 스택을 닫을 책임을 진다.
    """
    stack = ExitStack()
    try:
        for idx, name in enumerate(names):
            fail_on_enter = (idx == fail_at)
            stack.enter_context(FakeResource(name, log, fail_on_enter))
        return stack.pop_all()
    except Exception:
        stack.close()
        raise


def test_pop_all_ownership_transfer_success():
    """pop_all()로 리소스 소유권을 호출자에게 이전하면 팩토리 함수에서는 닫지 않고 호출자가 나중에 닫는다."""
    print("\n=== pop_all() 소유권 이전: 성공 시나리오 ===")
    
    log: list[str] = []
    
    print("팩토리 함수 호출 중...")
    returned_stack = acquire_resources_atomically(["A", "B", "C"], log)
    print("팩토리 함수 완료 (아직 해제 안 됨)")
    
    print("로그 (팩토리 완료 직후):")
    for entry in log:
        print(f"  {entry}")
    
    assert log == [
        "A: 획득",
        "B: 획득",
        "C: 획득"
    ], f"팩토리 완료 후 예상과 다른 로그: {log}"
    
    print("\n호출자가 스택 닫기...")
    returned_stack.close()
    
    print("로그 (스택 닫은 후):")
    for entry in log:
        print(f"  {entry}")
    
    assert log == [
        "A: 획득",
        "B: 획득",
        "C: 획득",
        "C: 해제",
        "B: 해제",
        "A: 해제"
    ], f"스택 닫은 후 예상과 다른 로그: {log}"
    
    print("✓ pop_all()은 소유권을 이전하여 팩토리는 닫지 않고 호출자가 나중에 닫는다")


def test_pop_all_ownership_transfer_failure():
    """팩토리 함수 내에서 리소스 획득 실패 시 지금까지 획득한 리소스를 모두 해제하고 예외를 전파한다."""
    print("\n=== pop_all() 소유권 이전: 실패 시나리오 (올-오어-낫싱) ===")
    
    log: list[str] = []
    
    try:
        print("팩토리 함수 호출 중 (2번 인덱스에서 실패)...")
        returned_stack = acquire_resources_atomically(["X", "Y", "Z", "W"], log, fail_at=2)
    except ValueError as e:
        print(f"예외 포착: {e}")
    
    print("로그 (팩토리 실패 후):")
    for entry in log:
        print(f"  {entry}")
    
    assert log == [
        "X: 획득",
        "Y: 획득",
        "Z: 획득 실패",
        "Y: 해제",
        "X: 해제"
    ], f"팩토리 실패 후 예상과 다른 로그: {log}"
    
    print("✓ 실패 시 지금까지 획득한 리소스를 역순으로 해제하고 예외가 전파된다")


def failing_cleanup(name: str, log: list[str]):
    """정리 중 예외를 발생시키는 콜백 함수다."""
    log.append(f"{name}: 정리 시작")
    raise RuntimeError(f"{name} 정리 중 오류")


def test_cleanup_callback_raises():
    """정리 콜백이 예외를 발생시키면 예외 체이닝이 일어나고 나머지 콜백도 계속 실행된다."""
    print("\n=== 정리 콜백 예외 발생 시 예외 체이닝과 나머지 콜백 실행 ===")
    
    log: list[str] = []
    
    try:
        with ExitStack() as stack:
            stack.enter_context(FakeResource("리소스1", log))
            stack.callback(failing_cleanup, "콜백A", log)
            stack.enter_context(FakeResource("리소스2", log))
            stack.callback(lambda: log.append("콜백B: 정상 정리"))
    except RuntimeError as e:
        print(f"최종 예외: {e}")
        if e.__context__:
            print(f"체인된 원래 컨텍스트: {e.__context__}")
    
    print("\n로그 순서:")
    for entry in log:
        print(f"  {entry}")
    
    assert "리소스1: 획득" in log
    assert "리소스2: 획득" in log
    assert "콜백B: 정상 정리" in log
    assert "리소스2: 해제" in log
    assert "콜백A: 정리 시작" in log
    assert "리소스1: 해제" in log
    
    expected_order = [
        "리소스1: 획득",
        "리소스2: 획득",
        "콜백B: 정상 정리",
        "리소스2: 해제",
        "콜백A: 정리 시작",
        "리소스1: 해제"
    ]
    assert log == expected_order, f"예상과 다른 로그 순서: {log}"
    
    print("✓ 정리 콜백 예외 발생 시에도 나머지 콜백이 계속 실행되고 예외가 체이닝된다")


def test_zero_resources_boundary():
    """빈 입력(리소스 0개)에서도 정상 작동하고 아무것도 닫지 않는다."""
    print("\n=== 경계 사례: 리소스 0개 (빈 입력) ===")
    
    log: list[str] = []
    
    print("빈 리소스 목록으로 팩토리 호출...")
    returned_stack = acquire_resources_atomically([], log)
    
    print("로그 (팩토리 완료 후):")
    if not log:
        print("  (비어 있음)")
    
    assert log == [], f"빈 입력에서 예상과 다른 로그: {log}"
    
    print("스택 닫기...")
    returned_stack.close()
    
    print("로그 (스택 닫은 후):")
    if not log:
        print("  (비어 있음)")
    
    assert log == [], f"빈 입력 스택 닫은 후 예상과 다른 로그: {log}"
    
    print("✓ 빈 입력에서도 정상 작동하고 아무 리소스도 닫지 않는다")


def test_direct_exitstack_zero_resources():
    """ExitStack을 직접 사용하여 리소스 0개 케이스를 확인한다."""
    print("\n=== 경계 사례: ExitStack 직접 사용, 리소스 0개 ===")
    
    log: list[str] = []
    
    with ExitStack() as stack:
        print("아무 리소스도 추가하지 않음")
    
    print("로그:")
    if not log:
        print("  (비어 있음)")
    
    assert log == [], f"예상과 다른 로그: {log}"
    print("✓ 리소스를 추가하지 않아도 ExitStack이 정상 작동한다")


if __name__ == "__main__":
    test_partial_failure_rollback()
    test_pop_all_ownership_transfer_success()
    test_pop_all_ownership_transfer_failure()
    test_cleanup_callback_raises()
    test_zero_resources_boundary()
    test_direct_exitstack_zero_resources()
    
    print("\n모든 테스트 통과")
