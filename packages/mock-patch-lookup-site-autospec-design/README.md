# unittest.mock.patch lookup site와 autospec 설계 비교

`unittest.mock.patch`는 **이름을 찾는 위치(lookup site)** 의 속성을 바꾼다. 의존 함수가 정의된 모듈(`rate_source.fetch_rate`)을 패치해도, 사용하는 모듈이 `from rate_source import fetch_rate`로 이름을 이미 자기 네임스페이스에 복사해 뒀다면 사용 모듈의 호출은 바뀌지 않아 테스트가 진짜 함수를 부른다(조용한 실패). 모듈 속성으로 접근하는 코드(`rate_source.fetch_rate(...)`)에서는 정의 모듈을 패치해야 효과가 있다. 또 기본 `Mock`/`MagicMock`은 어떤 인자 조합·어떤 속성 이름도 받아들여 호출 규약이 바뀌어도 테스트가 통과한다. `autospec=True`(또는 `create_autospec`)는 시그니처를 강제해 `TypeError`로 드러낸다. 이 폴더는 패치 대상 위치 차이, `autospec`의 방어 효과, 주입 설계 기본값 함정, 실패와 경계를 함께 다룬다.

## 실행 방법

이 폴더에서 실행한다. 외부 패키지는 쓰지 않는다.

**데모 실행:**
```bash
python3 src/patch_probe.py
```

**테스트 실행:**
```bash
python3 -W error -m unittest discover -s tests -v
```

CPython 3.12.3에서 테스트 39개가 모두 통과했다.

## 파일

- `src/rate_source.py`: 환율 조회 의존 함수 (`fetch_rate(currency, *, timeout=1.0)`)와 `UnknownCurrency` 예외
- `src/invoice_from_import.py`: `from rate_source import fetch_rate` 방식의 `convert` 함수
- `src/invoice_qualified.py`: `import rate_source` 뒤 `rate_source.fetch_rate(...)` 방식의 `convert` 함수
- `src/invoice_injected.py`: `convert(amount, currency, *, fetch_rate=None)` 주입 설계와 기본값 함정 비교 함수 (`convert_default_bound`, `convert`)
- `src/patch_probe.py`: 패치 대상 위치·시그니처 드리프트·속성 접근·오타·spec vs autospec·주입 함정 시나리오 실행 함수와 데모
- `tests/test_mock_patch_lookup_site.py`: 정상·조용한 실패·방어·경계·복원·데코레이터 순서·시그니처 드리프트 테스트 (39개)

## 시나리오별 기대 결과

### 1. 패치 대상 위치에 따른 효과

| 시나리오 | 패치 대상 | 사용 방식 | 결과 | 설명 |
|---|---|---|---|---|
| 진짜 함수 | - | from-import | 10.0 | 기준 |
| 진짜 함수 | - | 모듈 속성 접근 | 10.0 | 기준 |
| 정의 모듈 패치 | `rate_source.fetch_rate` | from-import | 10.0 | 효과 없음(조용한 실패) |
| 정의 모듈 패치 | `rate_source.fetch_rate` | 모듈 속성 접근 | 20.0 | 효과 있음 |
| 사용 위치 패치 | `invoice_from_import.fetch_rate` | from-import | 20.0 | 효과 있음 |
| 사용 위치 패치 | `invoice_from_import.fetch_rate` | 모듈 속성 접근 | 10.0 | 효과 없음 |

- `from rate_source import fetch_rate`를 쓴 모듈에서는 **사용 위치**(`invoice_from_import.fetch_rate`)를 패치해야 한다.
- `rate_source.fetch_rate(...)`로 접근하는 모듈에서는 **정의 모듈**(`rate_source.fetch_rate`)을 패치해야 한다.
- 잘못된 위치를 패치하면 오류 없이 진짜 함수가 불린다.

### 2. 시그니처 드리프트 탐지

| Mock 종류 | 시나리오 | 결과 |
|---|---|---|
| 기본 Mock | 정의 함수에 필수 인자(region) 추가, 호출 코드는 낡은 규약 | pass (통과) |
| autospec | 정의 함수에 필수 인자(region) 추가, 호출 코드는 낡은 규약 | TypeError |

- 기본 `Mock`/`MagicMock`은 시그니처가 바뀌어도 테스트를 통과시킨다. 정의 함수에 새 필수 인자(`region`)가 추가되어도 호출 코드가 낡은 규약(`currency`만)으로 부르는 테스트는 계속 통과한다.
- `autospec=True`는 시그니처를 강제해 `TypeError`를 낸다. 호출 규약이 바뀌면 테스트가 실패해 드리프트를 드러낸다.

### 3. 속성 접근 차이

| Mock 종류 | 존재하지 않는 속성 읽기 | 결과 |
|---|---|---|
| 기본 Mock | `mock_fetch.nonexistent` | pass (새 Mock 생성) |
| autospec | `mock_fetch.nonexistent` | AttributeError |

- 기본 Mock은 임의 속성 읽기를 허용하고 새 Mock을 돌려준다.
- autospec Mock은 존재하지 않는 속성을 `AttributeError`로 거절한다.

### 4. 패치 대상 오타 탐지

| 패치 | 대상 이름 | 결과 |
|---|---|---|
| `patch("invoice_from_import.fetch_rat")` | 오타 | AttributeError |
| `patch("invoice_from_import.fetch_rat", create=True)` | 오타 + create | pass (통과) |

- 존재하지 않는 속성을 패치하면 `AttributeError: <module 'invoice_from_import'> does not have the attribute 'fetch_rat'`.
- `create=True`를 주면 오타를 조용히 통과시킨다.

### 5. spec vs autospec

| Mock 종류 | 잘못된 인자 조합 | 결과 |
|---|---|---|
| spec=True | `fetch_rate("USD", "extra", 1, 2)` | pass (통과) |
| autospec=True | `fetch_rate("USD", "extra", 1, 2)` | TypeError |

- `spec=True`는 속성 이름만 검사하고 호출 인자는 검사하지 않는다.
- `autospec=True`는 속성 이름과 호출 인자를 모두 검사한다.

### 6. 주입 설계 기본값 함정

| 함수 | 패치 후 호출 | 결과 | 설명 |
|---|---|---|---|
| `convert_default_bound` | 기본값으로 호출 | 10.0 | 효과 없음(함정) |
| `convert` | 기본값으로 호출 | 20.0 | 효과 있음 |

**기본값 함정:**
```python
def convert_default_bound(amount, currency, *, fetch_rate=rate_source.fetch_rate):
    # 함정: 기본값이 정의 시점에 묶임
```

- 기본값 `fetch_rate=rate_source.fetch_rate`는 함수 정의 시점에 평가된다.
- 이후 `rate_source.fetch_rate`를 패치해도 기본값은 바뀌지 않는다.

**권장 설계:**
```python
def convert(amount, currency, *, fetch_rate=None):
    if fetch_rate is None:
        fetch_rate = rate_source.fetch_rate  # 호출 시점에 조회
```

- 기본값을 `None`으로 두고 호출 시점에 조회하면 패치가 효과를 낸다.
- 또는 패치 없이 테스트용 함수를 직접 주입할 수 있다.

## 실패와 경계

### 조용한 실패

1. **정의 모듈 패치 + from-import 사용:** 효과 없음. 사용 위치를 패치해야 한다.
2. **기본 Mock의 잘못된 인자:** `mock_fetch("USD", "extra", 1, 2)`가 통과한다.
3. **create=True:** 오타 이름 `"fetch_rat"`를 통과시킨다.
4. **spec=True:** 인자 수를 검사하지 않는다.
5. **기본값으로 묶인 주입:** 패치 후에도 진짜 함수를 부른다.

### autospec 방어

1. **잘못된 인자 조합:** `TypeError: too many positional arguments` (버전별 문구 다를 수 있음)
2. **존재하지 않는 속성:** `AttributeError: 'function' object has no attribute 'nonexistent'`
3. **패치 대상 오타:** `AttributeError: <module> does not have the attribute 'fetch_rat'`
4. **시그니처 드리프트:** 정의 함수에 필수 인자가 추가되면 `TypeError`

### 복원

- `with` 블록을 벗어나면 원래 함수로 복원된다.
- 예외가 나도 복원된다.
- 중첩 패치는 역순으로 복원된다(안쪽 먼저, 바깥쪽 나중).

### 데코레이터 순서

```python
@mock.patch("rate_source.fetch_rate", return_value=2.0)
@mock.patch("invoice_from_import.fetch_rate", return_value=3.0)
def test_func(mock_invoice, mock_rate):
    # 아래 데코레이터(invoice_from_import)가 첫 인자, 위 데코레이터(rate_source)가 둘째 인자
```

- 여러 `@mock.patch` 데코레이터를 쌓으면 아래 데코레이터부터 순서대로 인자가 들어온다.

### 경계 조건

- **amount:** 입력 검증 없이 float 곱셈 결과를 그대로 돌려준다. 0이면 결과도 0, 음수면 결과도 음수. `bool`은 `int`의 하위 클래스이므로 `True`는 1.0, `False`는 0.0으로 계산된다.
- **알 수 없는 통화:** `UnknownCurrency`(ValueError의 하위 클래스) 전파
- **timeout 인자:** `convert`는 `timeout`을 넘기지 않고 `currency`만 넘긴다. `fetch_rate`의 `timeout`은 키워드 전용 인자다.

## 정리

1. **lookup site가 중요하다.** `from X import Y`를 쓴 모듈에서는 사용 위치(`module.Y`)를 패치하고, `X.Y(...)`로 접근하는 모듈에서는 정의 모듈(`X.Y`)을 패치한다. 잘못된 위치를 패치하면 오류 없이 진짜 함수가 불린다.
2. **autospec은 시그니처를 강제한다.** 기본 Mock은 어떤 인자 조합도 통과시키지만, `autospec=True`는 잘못된 인자·존재하지 않는 속성을 `TypeError`/`AttributeError`로 거절한다. 호출 규약이 바뀌면 테스트가 실패해 드리프트를 드러낸다.
3. **spec=True는 인자를 검사하지 않는다.** 속성 이름만 검사한다. 시그니처 검사가 필요하면 `autospec=True`를 쓴다.
4. **create=True는 오타를 숨긴다.** 존재하지 않는 속성을 조용히 통과시킨다. 오타를 드러내려면 `create=True` 없이 패치한다.
5. **주입 설계에서 기본값 함정을 피한다.** 기본값 `fetch_rate=rate_source.fetch_rate`는 정의 시점에 묶여 패치가 안 먹는다. `fetch_rate=None`으로 두고 호출 시점에 조회하거나, 패치 없이 테스트용 함수를 직접 주입한다.
6. **패치는 항상 복원된다.** `with` 블록을 벗어나거나 예외가 나도 원래 함수로 복원된다. 중첩 패치는 역순으로 복원된다.
7. **데코레이터는 아래부터 순서대로 인자가 들어온다.** 여러 `@mock.patch`를 쌓으면 아래 데코레이터(적용 순서는 먼저)가 첫 인자, 위 데코레이터(적용 순서는 나중)가 둘째 인자다.
