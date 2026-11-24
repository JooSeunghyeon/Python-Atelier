# struct 모듈 바이너리 레이아웃, 패딩, 바이트 순서, 검증 헤더 설계

`struct` 모듈로 바이너리 레코드를 만들 때 네이티브 형식(`@`, 접두사 없음)이 C 정렬 규칙에 따라 패딩을 몰래 넣어 레코드 크기와 바이트 배치가 바뀌는 지점을 테스트로 고정하고, 명시 바이트 순서 형식(`<`, `>`, `=`, `!`)으로 고정 레이아웃을 쓰는 설계, 검증 헤더 설계, 미리 컴파일한 `struct.Struct` 사용을 비교한다. 실패와 경계(범위 밖 값, 버퍼 길이 불일치, 조용히 값이 바뀌는 경우)를 함께 다룬다.

## 실행 방법

이 폴더에서 실행한다. 외부 패키지는 쓰지 않는다.

**데모 실행:**
```bash
python3 src/struct_binary_layout.py
```

**테스트 실행:**
```bash
python3 -W error -m unittest discover -s tests -v
```

CPython 3.12.3(x86_64, little-endian)에서 테스트 58개가 모두 통과했다.

## 파일

- `src/struct_binary_layout.py`: 형식 비교, 패딩 분석, 바이트 순서 혼동 시연, 검증 헤더 설계(`encode_frame`/`decode_frame`), 레코드 배열 읽기, 성능 비교 함수와 데모
- `tests/test_struct_binary_layout.py`: 표준 형식 절대 크기, 네이티브 형식 플랫폼 불변 관계, 왕복, 범위·타입·인자 수·버퍼 길이·float 오버플로·s 형식 오류, 조용한 변형 경계(바이트 순서 혼동, `?`에 문자열, `s` 잘림/NUL 채움, `<f` 정밀도 손실), 헤더 경계, 레코드 배열 나머지 바이트 거절, 패딩 계산, 성능 비교 테스트

## 시나리오별 기대 결과

### 형식별 레코드 크기

같은 레코드(kind: int8, count: int32, ratio: float64)를 세 형식으로 패킹했을 때:

| 형식 | 크기 | 설명 |
|---|---|---|
| native(@) | 16 | C 정렬 규칙에 따라 패딩 추가(x86_64) |
| standard(=) | 13 | 표준 크기, 패딩 없음 |
| little(<) | 13 | 리틀엔디언, 패딩 없음(권장) |

- 네이티브 형식은 플랫폼마다 다르다. x86_64에서 `@bid`는 16바이트(b 1바이트 + 3바이트 패딩 + i 4바이트 + d 8바이트)다.
- 표준·리틀·빅 형식은 플랫폼 무관 고정 크기다.

### 패딩 분석

`@bi` 형식(x86_64):

| 필드 | 크기 | 오프셋 | 패딩 |
|---|---|---|---|
| b | 1 | 0 | 3 |
| i | 4 | 4 | 0 |

- `b`(1바이트) 뒤에 3바이트 패딩이 들어가 `i`(4바이트)가 4바이트 정렬된 오프셋 4에서 시작한다.
- 합계: 1 + 3 + 4 + 0 = 8바이트 (= `calcsize("@bi")`)

`<bi` 형식:

| 필드 | 크기 | 오프셋 | 패딩 |
|---|---|---|---|
| b | 1 | 0 | 0 |
| i | 4 | 1 | 0 |

- 고정 형식은 패딩을 넣지 않는다. 합계 5바이트.

### 바이트 순서 혼동

같은 바이트를 다른 바이트 순서로 읽으면 값이 바뀐다. 오류는 나지 않는다.

```python
struct.pack("<I", 1)  # b"\x01\x00\x00\x00"
struct.unpack(">I", b"\x01\x00\x00\x00")  # (16777216,)
```

- 1을 리틀엔디언으로 패킹한 뒤 빅엔디언으로 읽으면 16777216이 된다.
- 고정 레이아웃이 필요할 때는 `<` 또는 `>`를 명시한다. `@`는 플랫폼에 따라 바뀐다.

### 검증 헤더 설계

고정 헤더(magic 4바이트, version, flags, payload_length) + payload 구조:

```
struct.Struct("<4sBBH")  # 8바이트 헤더
magic = b"FRME"
version = 1 (1~255)
flags = 0~255
payload_length = 0~65535
```

**정상 경로:**
- 빈 payload(0바이트)도 허용한다. 헤더만 8바이트.
- 최대 payload 65535바이트.

**거절 사례:**
- magic 불일치: `FrameError: magic 불일치`
- 알 수 없는 version: `FrameError: 알 수 없는 version: 99`
- 헤더보다 짧은 버퍼(< 8바이트): `FrameError: 프레임이 헤더보다 짧다`
- payload 길이 불일치:
  - 짧음: `FrameError: payload가 짧다: 선언=5, 실제=4`
  - 김: `FrameError: payload가 길다: 선언=5, 실제=6`
- version 범위 밖(0, 256): `FrameError: version은 1~255 범위여야 한다`
- flags 범위 밖(-1, 256): `FrameError: flags는 0~255 범위여야 한다`
- payload 길이 초과(> 65535): `FrameError: payload 길이가 최대값을 초과`

### 실패 경계

**범위 밖 값:**
```python
struct.pack("<h", 40000)   # struct.error: 'h' format requires -32768 <= number <= 32767
struct.pack("<B", 256)     # struct.error: 'B' format requires 0 <= number <= 255
struct.pack("<i", 2**31)   # struct.error: 'i' format requires ...
```

**정수가 아닌 값:**
```python
struct.pack("<h", 1.5)  # struct.error: required argument is not an integer
```

**인자 수 불일치:**
```python
struct.pack("<HH", 1)  # struct.error: pack expected 2 items for packing (got 1)
```

**버퍼 길이 불일치:**
```python
struct.unpack("<I", b"\x01\x02\x03")  # struct.error: unpack requires a buffer of 4 bytes
struct.unpack("<I", b"\x01\x02\x03\x04\x05")  # struct.error: ... 4 bytes
list(struct.iter_unpack("<H", b"\x01\x00\x02"))  # struct.error: ... multiple of 2 bytes
```

**float 정밀도와 오버플로:**
```python
struct.pack("<f", 0.1)  # 0.10000000149011612 (정밀도 손실)
struct.pack("<d", 0.1)  # 0.1 (유지)
struct.pack("<e", 70000.0)  # OverflowError: float too large to pack with e format
struct.pack("<f", 1e39)     # OverflowError: float too large to pack with f format
```

**s 형식:**
```python
struct.pack("<4s", b"abcdef")  # b"abcd" (잘림)
struct.pack("<4s", b"ab")      # b"ab\x00\x00" (NUL 채움)
struct.pack("<4s", "ab")       # struct.error: argument for 's' must be a bytes object
```

### 조용한 변형 경계

표준 struct는 오류를 내지 않고 조용히 값을 바꾼다. 검증이 필요할 때는 명시 검사를 둔다.

**`?` 형식에 문자열:**
```python
struct.pack("<?", "x")  # b"\x01" (True로 변환, 오류 없음)
```

**바이트 순서 혼동:**
```python
struct.unpack(">I", struct.pack("<I", 1))  # (16777216,) (오류 없음)
```

**`4s` 잘림/NUL 채움:** 위 참조

**`<f` 정밀도 손실:** 위 참조

### 레코드 배열 읽기

`iter_unpack`으로 고정 크기 레코드 배열을 읽는다. 나머지 바이트가 있으면 거절한다.

```python
records = [(1, 10), (2, 20), (3, 30)]
packed = b"".join(struct.pack("<bH", k, v) for k, v in records)  # 9바이트
read_record_array(packed, "<bH")  # [(1, 10), (2, 20), (3, 30)]

read_record_array(packed + b"\x00", "<bH")
# ValueError: 데이터가 레코드 크기의 배수가 아니다: 10 % 3 != 0 (오프셋 9에서 1바이트 남음)
```

## 성능 비교

`<iHd` 형식, 100000회 패킹(x86_64, Python 3.12.3):

| 방법 | 시간 | 비율 |
|---|---|---|
| struct.pack | 0.0129초 | 1.68 |
| Struct.pack | 0.0077초 | 1.00 |

- 미리 컴파일한 `struct.Struct`가 `struct.pack`보다 약 1.7배 빠르다.
- 절대 시간과 비율은 실행마다·플랫폼마다 다르므로 테스트는 실행 가능성과 결과 바이트 동일성만 검사한다.

## 정리

1. **네이티브 형식(`@`)은 플랫폼 정렬 규칙에 따라 패딩을 넣는다.** 같은 형식도 x86_64·ARM64·32비트에서 크기가 다를 수 있다. `calcsize("@bi")`는 x86_64에서 8바이트지만 다른 플랫폼에서는 다를 수 있다.
2. **고정 레이아웃이 필요하면 `<`, `>`, `=`, `!`를 명시한다.** 플랫폼 무관 고정 크기·고정 바이트 순서가 보장된다. 네트워크 프로토콜·파일 형식은 `<`(리틀엔디언) 또는 `>`(빅엔디언)를 쓴다.
3. **바이트 순서 혼동은 오류 없이 값을 바꾼다.** 같은 바이트를 `<`로 패킹한 뒤 `>`로 읽으면 엉뚱한 값이 나온다. 형식을 고정하고 혼용하지 않는다.
4. **범위 밖 값·정수 아닌 값·인자 수 불일치·버퍼 길이 불일치는 `struct.error`를 낸다.** 검증 헤더 설계에서는 이를 `FrameError`로 체이닝하고 필드 이름을 메시지에 담는다.
5. **`?`·`s` 형식은 조용히 변환한다.** `?`는 truthy 값을 True로, `s`는 긴 바이트를 자르고 짧은 바이트를 NUL로 채운다. 검증이 필요하면 명시 검사를 둔다.
6. **미리 컴파일한 `struct.Struct`는 반복 패킹·언패킹을 빠르게 한다.** 형식 문자열 파싱을 한 번만 하므로 1.5~2배 빠르다. 성능이 중요할 때 쓴다.
7. **`iter_unpack`으로 레코드 배열을 읽을 때 나머지 바이트가 있으면 거절한다.** 어느 오프셋에서 잘렸는지 메시지에 담아 디버깅을 돕는다.
8. **검증 헤더는 magic·version·payload 길이 불일치를 명시 거절한다.** 헤더보다 짧은 버퍼, 선언 길이와 실제 길이 불일치, 범위 밖 version/flags를 `FrameError`로 거절한다. 빈 payload(0바이트)는 정상이다.
