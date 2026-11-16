# pickle 복원 시 __init__ 생략, 버전 상태 마이그레이션, find_class 제한 확인

pickle로 객체를 직렬화하고 복원할 때 발생하는 여러 함정과 이를 해결하는 패턴을 확인한다.

## 확인하는 내용

### 1. V1→V2 복원 시 __init__ 생략 함정

`pickle.loads()`는 객체를 복원할 때 `__init__`을 호출하지 않는다. 클래스 정의가 변경되어 새 필드가 추가된 경우, V1으로 저장된 객체를 모듈의 클래스를 V2로 교체한 후 복원하면 새 필드가 없어 `AttributeError`가 발생한다.

```python
class UserV1:
    def __init__(self, name: str):
        self.name = name

class UserV2:
    def __init__(self, name: str, email: str = ""):
        self.name = name
        self.email = email

# V1으로 저장
user_v1 = UserV1("Alice")
pickled = pickle.dumps(user_v1)

# 모듈의 UserV1을 UserV2로 교체
replace_class_in_module(__name__, 'UserV1', UserV2)

# 복원 시 __init__ 호출 안 됨 → email 없음
restored = pickle.loads(pickled)
print(restored.email)  # AttributeError!
```

### 2. 상태 버전 관리와 마이그레이션

레거시 클래스에서 진화된 클래스로 전환할 때, `__getstate__`와 `__setstate__`를 사용하여 상태 버전을 관리하고 복원 시 마이그레이션을 수행한다.

**레거시 V1 (버전 키 없음):**
```python
class UserV1Legacy:
    def __init__(self, name: str):
        self.name = name
```

**레거시 V2 (버전 키 포함):**
```python
class UserV2Legacy:
    def __init__(self, name: str, email: str = ""):
        self.name = name
        self.email = email
        self._state_version = 2
    
    def __getstate__(self):
        return {
            '_state_version': 2,
            'name': self.name,
            'email': self.email
        }
```

**진화된 최신 클래스 (항상 버전 3):**
```python
class UserVersioned:
    def __init__(self, full_name: str, email: str = ""):
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

레거시 V1으로 pickle한 바이트를 모듈의 V1 클래스를 UserVersioned로 교체한 후 복원하면, 버전 키가 없으므로 기본값 1로 처리되어 마이그레이션된다.

### 3. pickle 불가 속성 처리

`threading.Lock` 같은 pickle 불가 속성을 그대로 두면 `TypeError: cannot pickle '_thread.lock' object`가 발생한다.

`__getstate__`에서 pickle 불가 속성을 제외하고, `__setstate__`에서 새로 생성하여 처리한다. 복원된 객체의 Lock은 원본과 다른 새 객체이며, 원본이 잡혀 있어도 복원본은 풀려 있다.

```python
class ResourceWithLockFixed:
    def __init__(self, name: str):
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

## 변이 검사 결과

### 변이 (a): 모듈 속성 교체 제거

`test_v1_to_v2_missing_attribute`에서 `replace_class_in_module` 호출을 주석 처리했을 때:

```
ERROR: 테스트 실패 (모듈 로드 오류)
```

**결과:** 모듈 속성 교체 없이는 클래스 진화가 pickle에 반영되지 않음을 입증

### 변이 (b): __setstate__ 마이그레이션 로직 제거

`UserVersioned.__setstate__`의 마이그레이션 로직을 `self.__dict__.update(state)`로 단순화했을 때:

```
3개 FAIL/ERROR
```

**결과:** 마이그레이션 로직이 제거되면 버전별 상태 처리가 실패

### 변이 (c): find_class 허용 목록 검사 우회

`RestrictedUnpickler.find_class`의 허용 목록 검사를 제거하고 직접 `super().find_class()`를 호출했을 때:

```
3개 FAIL/ERROR
```

**결과:** find_class 제한이 없으면 허용되지 않은 전역 객체가 통과

### 변이 (d): ResourceWithLockFixed.__setstate__에서 Lock 재생성 제거

`__setstate__`에서 `self.lock = threading.Lock()` 라인을 제거했을 때:

```
1개 ERROR
```

**결과:** Lock 재생성이 없으면 복원 시 lock 속성이 없어 실패

### 결론

모든 변이에서 테스트가 실패하므로, 테스트가 실제 구현 결함을 잡는다는 것을 확인했다.

## 핵심 함정 정리

1. **pickle.loads는 __init__을 호출하지 않는다**: 클래스 정의가 변경되면 새 필드가 없어 AttributeError가 발생한다. 모듈 속성을 교체하여 클래스 진화를 pickle에 반영해야 한다.

2. **상태 버전 관리가 필수다**: 레거시 클래스와 진화된 클래스를 분리하고, `__getstate__`/`__setstate__`로 버전별 마이그레이션을 처리해야 한다. 버전 키가 없는 옛 상태는 기본값 1로 처리한다.

3. **pickle 불가 속성은 제외하고 복원 시 재생성한다**: threading.Lock 같은 속성은 `__getstate__`에서 제외하고 `__setstate__`에서 새로 만든다. 복원된 Lock은 원본과 다른 새 객체이며, 원본이 잡혀 있어도 복원본은 풀려 있다.

4. **신뢰할 수 없는 데이터는 pickle을 사용하지 않는다**: `find_class` 제한은 위험을 줄이지만 완전한 보안 경계가 아니다. 허용된 클래스라도 속성값에 허용되지 않은 전역이 섞여 있으면 거부된다. 신뢰할 수 없는 데이터에는 JSON 등 안전한 형식을 사용해야 한다.

5. **copy.deepcopy/copy.copy도 __getstate__/__setstate__를 거친다**: pickle 불가 속성이 복사 시에도 새로 생성되며, 원본이 잡혀 있어도 복사본은 풀려 있다.

6. **모든 pickle 프로토콜에서 마이그레이션이 동작한다**: 프로토콜 버전과 무관하게 상태 마이그레이션이 작동한다.
