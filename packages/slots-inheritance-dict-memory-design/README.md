# __slots__ 상속에서 __dict__가 되살아나는 지점과 막는 설계, 메모리 비용 비교

`__slots__`를 둔 클래스를 상속할 때 서브클래스가 `__slots__`를 다시 선언하지 않으면 인스턴스에 `__dict__`와 `__weakref__`가 다시 생긴다. 오류는 나지 않는다. 오타 속성(`p.xx = 3.0`)이 조용히 저장되고, 메모리 절약도 사라진다. 이 폴더는 그 지점을 테스트로 고정하고, 막는 방법 네 가지(빈 `__slots__`, 새 필드만 선언, `dataclass(slots=True)`, `__init_subclass__` 검사)를 비교한다. 개당 바이트도 같은 실행 안에서 비교한다.

## 실행 방법

이 폴더에서 실행한다. 외부 패키지는 쓰지 않는다.

**데모 실행:**
```bash
python3 src/slots_inheritance_design.py
```

**테스트 실행:**
```bash
python3 -W error -m unittest discover -s tests -v
```

CPython 3.12.16, 3.13.5, 3.14.10에서 테스트 34개가 모두 통과했다.

## 파일

- `src/slots_inheritance_design.py`: 비교용 클래스, 검사 함수(`has_instance_dict`, `dict_sources`, `assert_no_instance_dict`), `StrictSlots` 기반 클래스, 메모리 측정 함수와 데모
- `tests/test_slots_inheritance_design.py`: 동작, 검사 도구, 정의 시점 오류, 복사·pickle, 메모리 상대 비교 테스트

## 시나리오별 기대 결과

### 오타 속성과 __dict__

| 클래스 | 선언 | `__dict__` | `p.xx = 3.0` |
|---|---|---|---|
| `SlotPoint` | `__slots__ = ("x", "y")` | 없음 | AttributeError |
| `LeakyPoint(SlotPoint)` | `__slots__` 없음 | 생김 | 조용히 저장 |
| `SealedPoint(SlotPoint)` | `__slots__ = ()` | 없음 | AttributeError |
| `Point3D(SlotPoint)` | `__slots__ = ("z",)` | 없음 | AttributeError |
| `SealedLeaf(LeakyMiddle)` | 맨 아래만 `__slots__ = ()` | 생김 | 조용히 저장 |

- `LeakyPoint`에서 `x`, `y`는 여전히 슬롯에 있고 `__dict__`에는 오타 속성만 들어간다.
- `LeakyPoint`는 `__weakref__`도 다시 얻어 `weakref.ref`가 된다. `SlotPoint`, `SealedPoint`는 TypeError가 난다. 약한 참조가 필요하면 `WeakrefSlotPoint`처럼 `"__weakref__"`를 슬롯에 넣는다.
- 중간 계층에서 한 번 열린 `__dict__`는 아래에서 빈 `__slots__`를 선언해도 닫히지 않는다.

### 검사 도구

- `has_instance_dict(cls)`: `cls.__dictoffset__ != 0`이면 True다. `"__slots__" in vars(cls)`만 보면 `SealedLeaf`를 놓친다.
- `dict_sources(cls)`: MRO에서 `__dict__` 디스크립터를 직접 만든 클래스, 즉 처음 연 클래스 이름을 돌려준다. `SealedLeaf`는 `["LeakyMiddle"]`, `__slots__ = ()`인 `Exception` 서브클래스는 `["BaseException"]`이다. `__slots__ = ()`인 `tuple` 서브클래스는 `tuple`에 `__slots__` 속성이 없어도 `__dict__`가 없으므로 빈 목록이다.
- `assert_no_instance_dict(cls)`: `__dict__`가 생기면 원인 클래스 이름을 담은 `SlotsDesignError`(TypeError 하위)를 낸다.

### 정의 시점에 막기: StrictSlots

- `StrictSlots.__init_subclass__`가 서브클래스가 만들어질 때 `assert_no_instance_dict`를 부른다. `__slots__`를 빠뜨리거나 `"__dict__"`를 슬롯에 적으면 import 시점에 `SlotsDesignError`가 난다.
- 함정: `@dataclass(slots=True)`는 먼저 `__slots__` 없는 클래스를 만든 뒤 슬롯 클래스로 바꾼다. 그 첫 클래스에서 `__init_subclass__`가 불리므로 `StrictSlots`와 함께 쓰면 정의가 실패한다. 둘 중 하나만 쓴다.

### 정의 시점 오류

- 슬롯 이름과 같은 클래스 변수(기본값)를 두면 `ValueError: 'x' in __slots__ conflicts with class variable`.
- 비어 있지 않은 `__slots__` 부모 둘을 다중 상속하면 `TypeError: multiple bases have instance lay-out conflict`. 믹스인은 `ReprMixin`처럼 `__slots__ = ()`로 두면 슬롯 클래스와 섞을 수 있다.

### 복사와 pickle

- `SealedPoint`는 `copy.copy`, `copy.deepcopy`, `pickle` 왕복 뒤에도 값이 같고 `__dict__`가 없다.
- `LeakyPoint`는 슬롯 값과 `__dict__`의 오타 속성이 함께 복원된다.

## 메모리 비교

`bytes_per_instance`는 인스턴스 n개를 리스트에 담는 동안 tracemalloc이 잡은 바이트를 n으로 나눈다. 리스트 칸 8바이트가 포함된다. `+vars()`는 각 인스턴스에서 `vars(obj)`를 한 번 불러 `__dict__`를 실제로 만든 경우다. 직렬화, 디버거, `copy`처럼 `__dict__`를 읽는 코드가 이런 상황을 만든다.

n=20000, 개당 바이트(소수점 아래 버림):

| 설계 | 3.12.16 | 3.13.5 | 3.14.10 |
|---|---|---|---|
| PlainPoint | 88 | 96 | 96 |
| SlotPoint | 56 | 56 | 56 |
| SealedPoint | 56 | 56 | 56 |
| DataclassPoint | 56 | 56 | 56 |
| LeakyPoint | 96 | 72 | 104 |
| LeakyPoint+vars() | 160 | 416 | 168 |
| PlainPoint+vars() | 152 | 160 | 160 |

- 절대값은 버전마다 다르다. 3.13.5에서는 `LeakyPoint`의 `__dict__`를 한 번 읽으면 개당 416바이트까지 커졌다. 그래서 테스트는 절대값이 아니라 같은 실행 안의 상대 크기만 검사한다.
- 세 버전 모두에서 `SlotPoint < PlainPoint`, `SealedPoint`와 `DataclassPoint`는 `SlotPoint`와 같고, `LeakyPoint`는 `SlotPoint`보다 크며, `__dict__`를 만들면 더 커졌다.
- `bytes_per_instance`는 호출 전부터 tracemalloc이 켜져 있으면 끝나도 끄지 않는다.

## 정리

1. `__slots__` 클래스를 상속하면 서브클래스마다 `__slots__`를 선언한다. 새 필드가 없으면 `()`, 있으면 새 필드만 적는다.
2. 한 계층이라도 빠뜨리면 그 아래 전부에 `__dict__`가 생긴다. 검사는 `__dictoffset__`으로 하고, 원인은 `__dict__` 디스크립터를 만든 클래스로 찾는다.
3. 실수를 import 시점에 드러내려면 `__init_subclass__` 검사를 둔다. 단, `dataclass(slots=True)`와는 같이 쓰지 않는다.
4. 메모리 비용은 버전마다 다르므로 숫자는 직접 재고, 테스트는 상대 비교로 둔다.
