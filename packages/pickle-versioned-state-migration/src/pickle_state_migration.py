"""pickle 복원 시 __init__ 생략, 버전 상태 마이그레이션, find_class 제한을 확인한다."""

import pickle
import io
import threading
import copy
import sys
from typing import Any


class UserV1:
    """버전 1 사용자 클래스: name 필드만 있다."""
    
    def __init__(self, name: str):
        self.name: str = name
        self.init_call_count: int = getattr(self.__class__, '_init_call_count', 0) + 1
        self.__class__._init_call_count = self.init_call_count


class UserV2:
    """버전 2 사용자 클래스: email 필드가 추가되었다.
    
    pickle.loads는 __init__을 호출하지 않으므로 V1으로 저장된 객체를 
    V2 클래스로 복원하면 email 속성이 없어 AttributeError가 발생한다.
    """
    
    def __init__(self, name: str, email: str = ""):
        self.name: str = name
        self.email: str = email
        self.init_call_count: int = getattr(self.__class__, '_init_call_count', 0) + 1
        self.__class__._init_call_count = self.init_call_count


class UserV1Legacy:
    """레거시 V1: __getstate__/__setstate__ 없이 name만 있다."""
    
    def __init__(self, name: str):
        self.name: str = name


class UserV2Legacy:
    """레거시 V2: __getstate__/__setstate__로 버전 키를 포함한다."""
    
    def __init__(self, name: str, email: str = ""):
        self.name: str = name
        self.email: str = email
        self._state_version: int = 2
    
    def __getstate__(self) -> dict[str, Any]:
        return {
            '_state_version': 2,
            'name': self.name,
            'email': self.email
        }
    
    def __setstate__(self, state: dict[str, Any]) -> None:
        self._state_version = state['_state_version']
        self.name = state['name']
        self.email = state['email']


class UserVersioned:
    """진화된 사용자 클래스: 항상 최신 버전(3) 상태를 사용하고 옛 버전을 마이그레이션한다."""
    
    def __init__(self, full_name: str, email: str = ""):
        self.full_name: str = full_name
        self.email: str = email
        self._state_version: int = 3
    
    def __getstate__(self) -> dict[str, Any]:
        """항상 버전 3 형식으로 직렬화한다."""
        return {
            '_state_version': 3,
            'full_name': self.full_name,
            'email': self.email
        }
    
    def __setstate__(self, state: dict[str, Any]) -> None:
        """옛 버전 상태를 최신 버전으로 마이그레이션한다."""
        version = state.get('_state_version', 1)
        
        if version == 1:
            self._state_version = 3
            self.full_name = state['name']
            self.email = ""
        elif version == 2:
            self._state_version = 3
            self.full_name = state['name']
            self.email = state['email']
        elif version == 3:
            self._state_version = version
            self.full_name = state['full_name']
            self.email = state['email']
        else:
            raise ValueError(f"알 수 없는 상태 버전: {version}")


class UserFutureVersion:
    """미래 버전 테스트용: 버전 99를 쓴다."""
    
    def __init__(self, data: str):
        self.data: str = data
        self._state_version: int = 99
    
    def __getstate__(self) -> dict[str, Any]:
        return {
            '_state_version': 99,
            'data': self.data
        }


class ResourceWithLock:
    """pickle 불가 속성(threading.Lock)을 포함하는 클래스."""
    
    def __init__(self, name: str):
        self.name: str = name
        self.lock: threading.Lock = threading.Lock()
    
    def acquire(self) -> bool:
        """락을 획득한다."""
        return self.lock.acquire(blocking=False)
    
    def release(self) -> None:
        """락을 해제한다."""
        self.lock.release()


class ResourceWithLockFixed:
    """pickle 불가 속성을 __getstate__/__setstate__로 처리하는 클래스."""
    
    def __init__(self, name: str):
        self.name: str = name
        self.lock: threading.Lock = threading.Lock()
    
    def __getstate__(self) -> dict[str, Any]:
        """락을 제외하고 상태를 반환한다."""
        return {'name': self.name}
    
    def __setstate__(self, state: dict[str, Any]) -> None:
        """상태를 복원하고 새 락을 생성한다."""
        self.name = state['name']
        self.lock = threading.Lock()
    
    def acquire(self) -> bool:
        """락을 획득한다."""
        return self.lock.acquire(blocking=False)
    
    def release(self) -> None:
        """락을 해제한다."""
        self.lock.release()


class ObjectWithForbiddenGlobal:
    """허용되지 않은 전역 함수를 참조하는 객체."""
    
    def __init__(self, name: str, func):
        self.name: str = name
        self.func = func


class RestrictedUnpickler(pickle.Unpickler):
    """허용 목록으로 제한된 find_class를 제공하는 Unpickler다.
    
    허용되지 않은 전역 객체를 참조하는 pickle 데이터는 거부된다.
    """
    
    def __init__(self, file: io.BytesIO, allowed_globals: set[tuple[str, str]]):
        super().__init__(file)
        self.allowed_globals: set[tuple[str, str]] = allowed_globals
    
    def find_class(self, module: str, name: str) -> Any:
        """허용 목록에 있는 클래스만 로드한다."""
        if (module, name) not in self.allowed_globals:
            raise pickle.UnpicklingError(
                f"허용되지 않은 전역 객체: {module}.{name}"
            )
        return super().find_class(module, name)


def safe_loads(data: bytes, allowed_globals: set[tuple[str, str]]) -> Any:
    """허용 목록으로 제한된 pickle 로드를 수행한다."""
    return RestrictedUnpickler(io.BytesIO(data), allowed_globals).load()


def replace_class_in_module(module_name: str, class_name: str, new_class):
    """모듈의 클래스를 다른 클래스로 교체한다."""
    module = sys.modules[module_name]
    original = getattr(module, class_name)
    setattr(module, class_name, new_class)
    return original


def demo_v1_to_v2_attribute_error():
    """V1으로 저장된 객체를 V2 클래스로 복원하면 AttributeError가 발생한다."""
    print("=== V1→V2 복원 시 AttributeError 함정 ===")
    
    user_v1 = UserV1("Alice")
    pickled = pickle.dumps(user_v1)
    print(f"V1으로 pickle: name={user_v1.name}")
    
    original_class = replace_class_in_module(__name__, 'UserV1', UserV2)
    
    try:
        UserV2._init_call_count = 0
        restored = pickle.loads(pickled)
        print(f"복원 성공: type={type(restored).__name__}, name={restored.name}")
        print(f"__init__ 호출 횟수: {UserV2._init_call_count}")
        print(f"email 접근 시도...")
        _ = restored.email
        print("ERROR: email이 존재한다?")
    except AttributeError as e:
        print(f"AttributeError 발생: {e}")
    finally:
        replace_class_in_module(__name__, 'UserV1', original_class)
    
    print()


def demo_v1_legacy_to_versioned():
    """레거시 V1(버전 키 없음)을 최신 클래스로 복원하면 기본 버전 1로 마이그레이션된다."""
    print("=== 레거시 V1 → 최신 버전 마이그레이션 ===")
    
    user_v1 = UserV1Legacy("Bob")
    pickled = pickle.dumps(user_v1)
    print(f"레거시 V1으로 pickle: name={user_v1.name}")
    
    original_class = replace_class_in_module(__name__, 'UserV1Legacy', UserVersioned)
    
    try:
        restored = pickle.loads(pickled)
        print(f"복원 성공: full_name={restored.full_name}, email={restored.email}, version={restored._state_version}")
    finally:
        replace_class_in_module(__name__, 'UserV1Legacy', original_class)
    
    print()


def demo_v2_legacy_to_versioned():
    """레거시 V2를 최신 클래스로 복원하면 버전 2로 마이그레이션된다."""
    print("=== 레거시 V2 → 최신 버전 마이그레이션 ===")
    
    user_v2 = UserV2Legacy("Charlie", "charlie@example.com")
    pickled = pickle.dumps(user_v2)
    print(f"레거시 V2로 pickle: name={user_v2.name}, email={user_v2.email}, version={user_v2._state_version}")
    
    original_class = replace_class_in_module(__name__, 'UserV2Legacy', UserVersioned)
    
    try:
        restored = pickle.loads(pickled)
        print(f"복원 성공: full_name={restored.full_name}, email={restored.email}, version={restored._state_version}")
    finally:
        replace_class_in_module(__name__, 'UserV2Legacy', original_class)
    
    print()


def demo_future_version_error():
    """미래 버전 상태를 복원하면 ValueError가 발생한다."""
    print("=== 미래 버전 상태 복원 시 ValueError ===")
    
    future = UserFutureVersion("test_data")
    pickled = pickle.dumps(future)
    print(f"미래 버전(99)으로 pickle: data={future.data}")
    
    original_class = replace_class_in_module(__name__, 'UserFutureVersion', UserVersioned)
    
    try:
        restored = pickle.loads(pickled)
        print(f"ERROR: 미래 버전을 복원했다? full_name={restored.full_name}")
    except ValueError as e:
        print(f"ValueError 발생: {e}")
    finally:
        replace_class_in_module(__name__, 'UserFutureVersion', original_class)
    
    print()


def demo_unpicklable_lock_error():
    """threading.Lock을 그대로 pickle하면 TypeError가 발생한다."""
    print("=== threading.Lock pickle 시도 시 TypeError ===")
    
    resource = ResourceWithLock("res1")
    
    try:
        _ = pickle.dumps(resource)
        print("ERROR: Lock을 pickle할 수 있다?")
    except TypeError as e:
        print(f"TypeError 발생: {e}")
    
    print()


def demo_lock_fixed_with_getstate():
    """__getstate__/__setstate__로 Lock을 처리하면 pickle이 가능하다."""
    print("=== __getstate__/__setstate__로 Lock 처리 ===")
    
    resource = ResourceWithLockFixed("res2")
    
    acquired = resource.acquire()
    print(f"원본 락 획득: {acquired}")
    
    pickled = pickle.dumps(resource)
    print(f"원본 락 잡은 상태에서 pickle 성공: name={resource.name}")
    
    restored = pickle.loads(pickled)
    print(f"복원 성공: name={restored.name}")
    print(f"복원된 락 is 원본 락: {restored.lock is resource.lock}")
    
    acquired_restored = restored.acquire()
    print(f"복원된 락 획득 (원본이 잡혀 있어도 복원본은 풀림): {acquired_restored}")
    
    resource.release()
    restored.release()
    
    print()


def demo_restricted_unpickler_allowed():
    """허용 목록에 있는 클래스는 safe_loads로 복원할 수 있다."""
    print("=== RestrictedUnpickler: 허용된 클래스 ===")
    
    user = UserVersioned("David", "david@example.com")
    pickled = pickle.dumps(user)
    
    allowed = {
        (__name__, 'UserVersioned'),
    }
    
    try:
        restored = safe_loads(pickled, allowed)
        print(f"복원 성공: full_name={restored.full_name}, email={restored.email}")
    except pickle.UnpicklingError as e:
        print(f"UnpicklingError: {e}")
    
    print()


def demo_restricted_unpickler_rejected():
    """허용 목록에 없는 전역 객체를 참조하는 데이터는 거부된다."""
    print("=== RestrictedUnpickler: 허용되지 않은 전역 객체 거부 ===")
    
    user = UserVersioned("Eve", "eve@example.com")
    pickled = pickle.dumps(user)
    
    allowed = {
        (__name__, 'NonExistentClass'),
    }
    
    try:
        restored = safe_loads(pickled, allowed)
        print(f"ERROR: 복원이 성공했다? full_name={restored.full_name}")
    except pickle.UnpicklingError as e:
        print(f"UnpicklingError 발생: {e}")
    
    print()


def demo_restricted_unpickler_builtin_rejected():
    """builtins.print 같은 위험한 전역 함수를 참조하는 데이터는 거부된다."""
    print("=== RestrictedUnpickler: builtins 전역 함수 거부 ===")
    
    pickled = pickle.dumps(print)
    
    allowed = set()
    
    try:
        restored = safe_loads(pickled, allowed)
        print(f"ERROR: 복원이 성공했다? {restored}")
    except pickle.UnpicklingError as e:
        print(f"UnpicklingError 발생: {e}")
    
    print()


def demo_restricted_unpickler_mixed_object():
    """허용된 클래스라도 속성에 허용되지 않은 전역이 있으면 거부된다."""
    print("=== RestrictedUnpickler: 허용된 클래스 + 허용되지 않은 속성 거부 ===")
    
    obj = ObjectWithForbiddenGlobal("test", eval)
    pickled = pickle.dumps(obj)
    
    allowed = {
        (__name__, 'ObjectWithForbiddenGlobal'),
    }
    
    try:
        restored = safe_loads(pickled, allowed)
        print(f"ERROR: 복원이 성공했다? name={restored.name}")
    except pickle.UnpicklingError as e:
        print(f"UnpicklingError 발생: {e}")
    
    print()


def demo_copy_uses_getstate():
    """copy.deepcopy와 copy.copy도 __getstate__/__setstate__를 거친다."""
    print("=== copy.deepcopy/copy.copy도 __getstate__/__setstate__를 사용 ===")
    
    resource = ResourceWithLockFixed("res3")
    
    acquired = resource.acquire()
    print(f"원본 락 획득: {acquired}")
    
    deep_copied = copy.deepcopy(resource)
    print(f"deepcopy: name={deep_copied.name}, 복원된 락 is 원본 락: {deep_copied.lock is resource.lock}")
    
    acquired_deep = deep_copied.acquire()
    print(f"deepcopy된 락 획득 (원본이 잡혀 있어도 복사본은 풀림): {acquired_deep}")
    
    shallow_copied = copy.copy(resource)
    print(f"copy: name={shallow_copied.name}, 복원된 락 is 원본 락: {shallow_copied.lock is resource.lock}")
    
    acquired_shallow = shallow_copied.acquire()
    print(f"copy된 락 획득: {acquired_shallow}")
    
    resource.release()
    deep_copied.release()
    shallow_copied.release()
    
    print()


def demo_protocol_versions():
    """모든 pickle 프로토콜 버전에서 상태 마이그레이션이 동작한다."""
    print("=== 모든 pickle 프로토콜에서 상태 마이그레이션 ===")
    
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        user_v1 = UserV1Legacy("Frank")
        pickled = pickle.dumps(user_v1, protocol=protocol)
        
        original_class = replace_class_in_module(__name__, 'UserV1Legacy', UserVersioned)
        
        try:
            restored = pickle.loads(pickled)
            print(f"프로토콜 {protocol}: full_name={restored.full_name}, email={restored.email}, version={restored._state_version}")
        finally:
            replace_class_in_module(__name__, 'UserV1Legacy', original_class)
    
    print()


def demo_already_latest_version():
    """이미 최신 버전인 상태를 재복원해도 정상 작동한다."""
    print("=== 이미 최신 버전인 상태 재복원 ===")
    
    user_v3 = UserVersioned("Grace", "grace@example.com")
    pickled = pickle.dumps(user_v3)
    print(f"V3로 pickle: full_name={user_v3.full_name}, email={user_v3.email}, version={user_v3._state_version}")
    
    restored = pickle.loads(pickled)
    print(f"V3로 복원: full_name={restored.full_name}, email={restored.email}, version={restored._state_version}")
    
    print()


if __name__ == "__main__":
    demo_v1_to_v2_attribute_error()
    demo_v1_legacy_to_versioned()
    demo_v2_legacy_to_versioned()
    demo_future_version_error()
    demo_unpicklable_lock_error()
    demo_lock_fixed_with_getstate()
    demo_restricted_unpickler_allowed()
    demo_restricted_unpickler_rejected()
    demo_restricted_unpickler_builtin_rejected()
    demo_restricted_unpickler_mixed_object()
    demo_copy_uses_getstate()
    demo_protocol_versions()
    demo_already_latest_version()
    
    print("=== 모든 데모 완료 ===")
