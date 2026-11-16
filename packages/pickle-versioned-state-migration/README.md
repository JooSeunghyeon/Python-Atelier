# pickle 복원 시 __init__ 생략, 버전 상태 마이그레이션, find_class 제한 확인

pickle로 객체를 직렬화하고 복원할 때 발생하는 여러 함정과 이를 해결하는 패턴을 확인한다.

## 확인하는 내용

### 1. V1→V2 복원 시 __init__ 생략 함정

`pickle.loads()`는 객체를 복원할 때 `__init__`을 호출하지 않는다. 실제 운영에서는 배포 사이에 같은 모듈/클래스 이름의 정의가 바뀌는데, 이 예제에서는 그 상황을 한 프로세스 안에서 재현하기 위해 `replace_class_in_module` 헬퍼로 모듈 속성을 교체한다. 클래스 정의가 변경되어 새 필드가 추가된 경우, V1으로 저장된 객체를 V2 클래스로 복원하면 새 필드(`email`)가 없어 `AttributeError`가 발생한다.

**코드 예시 (타입 힌트 생략, 실제 소스는 타입 힌트 포함):**
```python
class UserV1:
    def __init__(self, name):
        self.name = name

class UserV2:
    def __init__(self, name, email=""):
        self.name = name
        self.email = email

# V1으로 저장
user_v1 = UserV1("Alice")
pickled = pickle.dumps(user_v1)

# 실제 운영에서는 배포 사이에 클래스 정의 변경
# 테스트/데모에서는 모듈 속성 교체로 재현
replace_class_in_module(__name__, 'UserV1', UserV2)

# 복원 시 __init__ 호출 안 됨 → email 없음
restored = pickle.loads(pickled)
print(restored.email)  # AttributeError!
```

### 2. 상태 버전 관리와 마이그레이션

레거시 클래스에서 진화된 클래스로 전환할 때, `__getstate__`와 `__setstate__`를 사용하여 상태 버전을 관리하고 복원 시 마이그레이션을 수행한다.

**레거시 V1 (버전 키 없음, 타입 힌트 생략):**
```python
class UserV1Legacy:
    def __init__(self, name):
        self.name = name
```

**레거시 V2 (버전 키 포함, 타입 힌트 생략):**
```python
class UserV2Legacy:
    def __init__(self, name, email=""):
        self.name = name
        self.email = email
        self._state_version = 2
    
    def __getstate__(self):
        return {
            '_state_version': 2,
            'name': self.name,
            'email': self.email
        }
    
    def __setstate__(self, state):
        self._state_version = state['_state_version']
        self.name = state['name']
        self.email = state['email']
```

**진화된 최신 클래스 (항상 버전 3, 타입 힌트 생략):**
```python
class UserVersioned:
    def __init__(self, full_name, email=""):
        self.full_name = full_name
        self.email = email
        self._state_version = 3
    
    def __getstate__(self):
        return {
            '_state_version': 3,
            'full_name': self.full_name,
            'email': self.email
        }
    
    def __setstate__(self, state):
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
```

실제 운영에서는 배포 사이에 레거시 클래스 정의가 진화된 클래스로 바뀐다. 레거시 V1으로 pickle한 바이트를 모듈의 V1 클래스를 UserVersioned로 교체한 후 복원하면, 버전 키가 없으므로 기본값 1로 처리되어 마이그레이션된다.

### 3. pickle 불가 속성 처리

`threading.Lock` 같은 pickle 불가 속성을 그대로 두면 `TypeError: cannot pickle '_thread.lock' object`가 발생한다.

`__getstate__`에서 pickle 불가 속성을 제외하고, `__setstate__`에서 새로 생성하여 처리한다. 복원된 객체의 Lock은 원본과 다른 새 객체이며, 원본이 잡혀 있어도 복원본은 풀려 있다.

**타입 힌트 생략 코드 예시:**
```python
class ResourceWithLockFixed:
    def __init__(self, name):
        self.name = name
        self.lock = threading.Lock()
    
    def __getstate__(self):
        return {'name': self.name}
    
    def __setstate__(self, state):
        self.name = state['name']
        self.lock = threading.Lock()
```

### 4. 신뢰할 수 없는 입력 경계: RestrictedUnpickler

`pickle.Unpickler`를 상속하여 `find_class`를 허용 목록(allowlist)으로 제한하는 `RestrictedUnpickler`와 `safe_loads` 함수를 구현한다.

허용되지 않은 전역 객체(예: `builtins.eval`, `os.system` 등)를 참조하는 pickle 데이터는 `pickle.UnpicklingError`로 거부된다. 허용된 클래스라도 속성값에 허용되지 않은 전역이 섞여 있으면 거부된다.

**타입 힌트 생략 코드 예시:**
```python
class RestrictedUnpickler(pickle.Unpickler):
    def __init__(self, file, allowed_globals):
        super().__init__(file)
        self.allowed_globals = allowed_globals
    
    def find_class(self, module, name):
        if (module, name) not in self.allowed_globals:
            raise pickle.UnpicklingError(
                f"허용되지 않은 전역 객체: {module}.{name}"
            )
        return super().find_class(module, name)
```

**주의:** pickle은 신뢰할 수 없는 데이터에 안전하지 않으며, `find_class` 제한은 완전한 보안 경계가 아니라 위험을 줄이는 방법이다. 신뢰할 수 없는 데이터는 pickle 대신 JSON 등 안전한 형식을 사용해야 한다.

### 5. copy.deepcopy/copy.copy도 __getstate__/__setstate__ 사용

`copy.deepcopy()`와 `copy.copy()`도 내부적으로 `__getstate__`/`__setstate__`를 거친다. Lock 같은 pickle 불가 속성이 복사 시 새로 생성되며, 원본이 잡혀 있어도 복사본은 풀려 있다.

### 6. 모든 pickle 프로토콜 버전 지원

프로토콜 0부터 `HIGHEST_PROTOCOL`(5)까지 모든 버전에서 상태 마이그레이션이 정상 작동한다.

## 실행 방법

**데모 실행:**
```bash
cd packages/pickle-versioned-state-migration
python3 src/pickle_state_migration.py
```

**테스트 실행:**
```bash
cd packages/pickle-versioned-state-migration
python3 -m unittest discover -s tests -v
```

## 실행 결과

### 사용 Python 버전

```
Python 3.12.3
```

### 데모 출력

```
=== V1→V2 복원 시 AttributeError 함정 ===
V1으로 pickle: name=Alice
복원 성공: type=UserV2, name=Alice
__init__ 호출 횟수: 0
email 접근 시도...
AttributeError 발생: 'UserV2' object has no attribute 'email'

=== 레거시 V1 → 최신 버전 마이그레이션 ===
레거시 V1으로 pickle: name=Bob
복원 성공: full_name=Bob, email=, version=3

=== 레거시 V2 → 최신 버전 마이그레이션 ===
레거시 V2로 pickle: name=Charlie, email=charlie@example.com, version=2
복원 성공: full_name=Charlie, email=charlie@example.com, version=3

=== 미래 버전 상태 복원 시 ValueError ===
미래 버전(99)으로 pickle: data=test_data
ValueError 발생: 알 수 없는 상태 버전: 99

=== threading.Lock pickle 시도 시 TypeError ===
TypeError 발생: cannot pickle '_thread.lock' object

=== __getstate__/__setstate__로 Lock 처리 ===
원본 락 획득: True
원본 락 잡은 상태에서 pickle 성공: name=res2
복원 성공: name=res2
복원된 락 is 원본 락: False
복원된 락 획득 (원본이 잡혀 있어도 복원본은 풀림): True

=== RestrictedUnpickler: 허용된 클래스 ===
복원 성공: full_name=David, email=david@example.com

=== RestrictedUnpickler: 허용되지 않은 전역 객체 거부 ===
UnpicklingError 발생: 허용되지 않은 전역 객체: __main__.UserVersioned

=== RestrictedUnpickler: builtins 전역 함수 거부 ===
UnpicklingError 발생: 허용되지 않은 전역 객체: builtins.print

=== RestrictedUnpickler: 허용된 클래스 + 허용되지 않은 속성 거부 ===
UnpicklingError 발생: 허용되지 않은 전역 객체: builtins.eval

=== copy.deepcopy/copy.copy도 __getstate__/__setstate__를 사용 ===
원본 락 획득: True
deepcopy: name=res3, 복원된 락 is 원본 락: False
deepcopy된 락 획득 (원본이 잡혀 있어도 복사본은 풀림): True
copy: name=res3, 복원된 락 is 원본 락: False
copy된 락 획득: True

=== 모든 pickle 프로토콜에서 상태 마이그레이션 ===
프로토콜 0: full_name=Frank, email=, version=3
프로토콜 1: full_name=Frank, email=, version=3
프로토콜 2: full_name=Frank, email=, version=3
프로토콜 3: full_name=Frank, email=, version=3
프로토콜 4: full_name=Frank, email=, version=3
프로토콜 5: full_name=Frank, email=, version=3

=== 이미 최신 버전인 상태 재복원 ===
V3로 pickle: full_name=Grace, email=grace@example.com, version=3
V3로 복원: full_name=Grace, email=grace@example.com, version=3

=== 모든 데모 완료 ===
```

### 테스트 결과

```
test_copy_creates_new_lock ... ok
test_deepcopy_creates_new_lock ... ok
test_migration_logic_is_executed ... ok
test_module_replacement_is_required ... ok
test_all_protocols_support_migration ... ok
test_allowed_class_loads_successfully ... ok
test_allowed_class_with_forbidden_attribute ... ok
test_builtin_function_rejected ... ok
test_different_module_same_class_name_rejected ... ok
test_disallowed_class_raises_unpickling_error ... ok
test_eval_function_rejected ... ok
test_lock_is_new_object_after_restore ... ok
test_lock_with_getstate_picklable ... ok
test_lock_without_getstate_raises_type_error ... ok
test_v1_to_v2_missing_attribute ... ok
test_already_latest_version_unchanged ... ok
test_future_version_via_pickle_loads ... ok
test_future_version_via_setstate ... ok
test_v1_legacy_to_versioned_migration ... ok
test_v2_legacy_to_versioned_migration ... ok

----------------------------------------------------------------------
Ran 20 tests in 0.001s

OK
```

## 변이 검사 결과 (Python 3.12.3)

### 변이 (a): 모듈 속성 교체 제거

`test_v1_to_v2_missing_attribute`에서 `original_class = replace_class_in_module(module_name, 'UserV1', UserV2)`를 `original_class = UserV1`로 변경했을 때:

```
----------------------------------------------------------------------
Ran 20 tests in 0.001s

FAILED (failures=1)
```

**실패한 테스트:**
- `test_v1_to_v2_missing_attribute` - AssertionError: `<class 'pickle_state_migration.UserV1'> is not <class 'pickle_state_migration.UserV2'>`

**결과:** 모듈 속성 교체 없이는 복원된 객체 타입이 UserV1 그대로이며 클래스 진화가 반영되지 않음

### 변이 (b): __setstate__ 마이그레이션 로직 제거

`UserVersioned.__setstate__`의 마이그레이션 로직을 `self.__dict__.update(state)`로 단순화했을 때:

```
----------------------------------------------------------------------
Ran 20 tests in 0.004s

FAILED (failures=3, errors=8)
```

**실패한 테스트:**
- `test_migration_logic_is_executed` - AssertionError: 'dummy' != 'Jane' (필드 변환 실패)
- `test_future_version_via_pickle_loads` - AssertionError: ValueError not raised
- `test_future_version_via_setstate` - AssertionError: ValueError not raised
- `test_v1_legacy_to_versioned_migration` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_v2_legacy_to_versioned_migration` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=0)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=1)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=2)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=3)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=4)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'
- `test_all_protocols_support_migration (protocol=5)` (ERROR) - AttributeError: 'UserVersioned' object has no attribute 'full_name'

**결과:** 마이그레이션 로직 제거 시 버전별 필드 변환(name→full_name) 및 기본값 처리가 실패하고 미래 버전 검증도 동작하지 않음

### 변이 (c): find_class 허용 목록 검사 우회

`RestrictedUnpickler.find_class`의 허용 목록 검사를 제거하고 `return super().find_class(module, name)`만 실행했을 때:

```
----------------------------------------------------------------------
Ran 20 tests in 0.001s

FAILED (failures=5)
```

**실패한 테스트:**
- `test_allowed_class_with_forbidden_attribute` - AssertionError: UnpicklingError not raised
- `test_builtin_function_rejected` - AssertionError: UnpicklingError not raised
- `test_different_module_same_class_name_rejected` - AssertionError: UnpicklingError not raised
- `test_disallowed_class_raises_unpickling_error` - AssertionError: UnpicklingError not raised
- `test_eval_function_rejected` - AssertionError: UnpicklingError not raised

**결과:** find_class 제한 제거 시 허용되지 않은 전역 객체(builtins.eval, 다른 모듈 클래스, 속성의 위험 함수)가 모두 통과

### 변이 (d): ResourceWithLockFixed.__setstate__에서 Lock 재생성 제거

`__setstate__`에서 `self.lock = threading.Lock()` 라인을 제거했을 때:

```
----------------------------------------------------------------------
Ran 20 tests in 0.001s

FAILED (errors=4)
```

**실패한 테스트:**
- `test_copy_creates_new_lock` (ERROR) - AttributeError: 'ResourceWithLockFixed' object has no attribute 'lock'
- `test_deepcopy_creates_new_lock` (ERROR) - AttributeError: 'ResourceWithLockFixed' object has no attribute 'lock'
- `test_lock_is_new_object_after_restore` (ERROR) - AttributeError: 'ResourceWithLockFixed' object has no attribute 'lock'
- `test_lock_with_getstate_picklable` (ERROR) - AttributeError: 'ResourceWithLockFixed' object has no attribute 'lock'

**결과:** Lock 재생성 제거 시 복원된 객체에 lock 속성이 없어 AttributeError 발생

### 결론

모든 변이에서 테스트가 실패하므로, 테스트가 실제 구현 결함을 잡는다는 것을 확인했다.

## 핵심 함정 정리

1. **pickle.loads는 __init__을 호출하지 않는다**: 실제 운영에서는 배포 사이에 같은 모듈/클래스 이름의 정의가 바뀌는데, V1으로 저장된 객체를 V2 정의로 복원하면 새 필드가 없어 AttributeError가 발생한다. (`replace_class_in_module`은 테스트/데모에서 그 상황을 한 프로세스 안에서 재현하기 위한 장치다.)

2. **상태 버전 관리가 필수다**: 레거시 클래스와 진화된 클래스를 분리하고, `__getstate__`/`__setstate__`로 버전별 마이그레이션을 처리해야 한다. 버전 키가 없는 옛 상태는 기본값 1로 처리한다.

3. **pickle 불가 속성은 제외하고 복원 시 재생성한다**: threading.Lock 같은 속성은 `__getstate__`에서 제외하고 `__setstate__`에서 새로 만든다. 복원된 Lock은 원본과 다른 새 객체이며, 원본이 잡혀 있어도 복원본은 풀려 있다.

4. **신뢰할 수 없는 데이터는 pickle을 사용하지 않는다**: `find_class` 제한은 위험을 줄이지만 완전한 보안 경계가 아니다. 허용된 클래스라도 속성값에 허용되지 않은 전역이 섞여 있으면 거부된다. 신뢰할 수 없는 데이터에는 JSON 등 안전한 형식을 사용해야 한다.

5. **copy.deepcopy/copy.copy도 __getstate__/__setstate__를 거친다**: pickle 불가 속성이 복사 시에도 새로 생성되며, 원본이 잡혀 있어도 복사본은 풀려 있다.

6. **모든 pickle 프로토콜에서 마이그레이션이 동작한다**: 프로토콜 버전과 무관하게 상태 마이그레이션이 작동한다.
