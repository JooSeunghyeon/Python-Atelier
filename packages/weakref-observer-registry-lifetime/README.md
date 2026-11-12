# weakref 구독자 레지스트리에서 객체 수명과 WeakMethod·finalize 함정 확인

약한 참조(weakref)로 구독자(옵저버) 레지스트리를 만들 때 객체 수명이 어떻게 결정되는지 테스트로 고정한다. 강한 참조 리스트 레지스트리는 구독자를 계속 살려 두는 누수가 생기고, 약한 참조 레지스트리는 구독자가 사라지면 자동으로 빠진다. 바운드 메서드에 `weakref.ref`를 걸면 임시 메서드 객체가 즉시 죽는 함정과 `weakref.WeakMethod`의 차이, `weakref.finalize` 콜백이 한 번만 실행되는 점(alive, 두 번째 호출 None, detach), finalize의 func/args가 대상 객체를 참조하면 객체가 영원히 수거되지 않는 함정, 참조 순환에 있는 객체는 `gc.collect()` 전까지 약한 참조가 살아 있는 점, 약한 참조를 걸 수 없는 대상(list/int, `__weakref__` 없는 `__slots__` 클래스)에서 TypeError가 나는 경계를 다룬다.

## 실행 방법

**데모 실행:**
```bash
python3 src/weakref_observer_registry.py
```

**테스트 실행:**
```bash
python3 -m unittest discover -s tests -v
```

## 시나리오별 기대 결과

### StrongRegistry (강한 참조)
- 구독자를 등록하면 레지스트리가 강한 참조를 유지하여 구독자가 삭제되지 않는다
- 원래 구독자 변수를 `del`로 제거해도 레지스트리가 살려 두어 publish 시 여전히 호출된다 (메모리 누수 위험)

### WeakRegistry (약한 참조)
- 함수는 `weakref.ref`로 저장하고, 바운드 메서드는 `weakref.WeakMethod`로 저장한다
- `publish()` 시 죽은 구독자는 자동으로 정리하고 실제 전달 개수를 반환한다
- `live_count()` 메서드로 현재 살아 있는 구독자 수를 조회할 수 있다
- 구독자 객체가 삭제되면 약한 참조가 자동으로 끊어져 다음 publish 시 전달되지 않는다

### 바운드 메서드 함정
- 바운드 메서드(`obj.method`)에 `weakref.ref`를 직접 걸면 임시 메서드 객체가 즉시 수거되어 약한 참조가 즉시 None이 된다
- `weakref.WeakMethod`는 인스턴스와 함수를 분리하여 저장하므로 인스턴스가 살아 있는 동안 메서드 호출이 가능하다

### weakref.finalize 동작
- `finalize` 객체는 대상이 수거될 때 콜백을 한 번만 실행한다
- `alive` 프로퍼티로 콜백이 아직 실행 안 됐는지 확인할 수 있다 (True/False)
- 두 번째로 직접 호출하면 None을 반환하고 아무 동작도 하지 않는다
- `detach()` 후에는 대상이 수거되어도 콜백이 실행되지 않는다
- **함정:** finalize의 func나 args가 대상 객체를 참조하면 순환 참조가 생겨 객체가 영원히 수거되지 않는다 (반드시 약한 참조로 전달해야 함)

### 참조 순환과 gc.collect()
- 참조 순환에 있는 객체는 `del` 직후에는 수거되지 않는다
- `gc.collect()`를 명시 호출하면 순환 참조가 해결되고 약한 참조가 None이 된다

### 약한 참조 불가 대상 (TypeError 경계)
- `list`, `int`, `str` 등 기본 타입은 약한 참조를 걸 수 없다 (TypeError: cannot create weak reference)
- `__slots__`만 정의하고 `__weakref__`를 포함하지 않은 클래스 인스턴스도 약한 참조를 걸 수 없다
- 호출 불가능한 객체를 `subscribe()`에 전달하면 TypeError가 발생한다

## CPython 참조 카운트와 gc.collect() 구분

- **CPython 참조 카운트 의존:** 객체에 대한 마지막 참조를 `del`하면 참조 카운트가 0이 되어 즉시 수거된다 (순환 참조가 없는 경우). 이는 CPython 구현에 의존하며 PyPy나 Jython 등에서는 다를 수 있다.
- **결정적 동작 (gc.collect()):** 참조 순환이 있는 객체는 `del` 직후 즉시 수거되지 않는다. `gc.collect()`를 명시 호출하여 순환 참조를 해결하고 수거를 강제하면 인터프리터 구현과 무관하게 결정적으로 테스트할 수 있다.

데모와 테스트는 CPython 참조 카운트 동작을 활용하여 간단한 케이스를 보여주지만, 순환 참조 시나리오에서는 `gc.collect()`를 명시 호출하여 결정적 동작을 보장한다.
