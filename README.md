# Python Atelier

실행해 본 코드를 폴더로 나눠 두었다. 다시 볼 때는 그 폴더 README를 먼저 연다.

## 목록

- [small-example](packages/small-example/README.md): Python 함수 정의와 리스트 순회를 보여주는 짧은 예제
- [generator-skip-blank-lines](packages/generator-skip-blank-lines/README.md): 제너레이터 표현식으로 파일 줄을 지연 평가하면서 빈 줄과 주석 줄을 건너뛰는 흐름을 확인한다.
- [contextmanager-finally-on-exception](packages/contextmanager-finally-on-exception/README.md): contextlib.contextmanager에서 yield 앞뒤로 리소스를 획득하고 해제하며, 본문에서 예외가 나도 finally 구간이 실행되는지 확인한다.
- [stable-sort-key-order](packages/stable-sort-key-order/README.md): sorted()와 list.sort()에서 key 함수가 같은 값을 돌려줄 때 원래 삽입 순서가 유지되는지 여러 key 함수로 확인한다.
- [decorator-stacking-order](packages/decorator-stacking-order/README.md): 두 데코레이터를 겹쳤을 때 아래쪽이 먼저 감싸고 위쪽이 바깥에서 감싸는 적용 순서를 호출 로그로 확인한다.
- [generator-close-finally](packages/generator-close-finally/README.md): 제너레이터를 close()로 명시 종료할 때 finally 블록이 실행되는지, GeneratorExit를 잡으면 어떻게 되는지 여러 상황별로 확인한다.
- [exitstack-partial-acquire-rollback](packages/exitstack-partial-acquire-rollback/README.md): ExitStack으로 동적 개수의 리소스를 획득할 때 중간 실패 시 역순 롤백, pop_all() 소유권 이전, 정리 콜백 예외 체이닝을 확인한다.
- [weakref-observer-registry-lifetime](packages/weakref-observer-registry-lifetime/README.md): 약한 참조(weakref)로 구독자 레지스트리를 만들 때 객체 수명, WeakMethod와 weakref.ref의 차이(MethodType 판별·내장 함수), finalize 함정(레지스트리가 args를 강하게 붙잡음·detach), 참조 순환과 gc.collect(), 약한 참조 불가 대상, 임시 객체 바운드 메서드·lambda 즉시 소멸 함정을 확인한다.
- [pickle-versioned-state-migration](packages/pickle-versioned-state-migration/README.md): pickle 복원 시 __init__ 생략·버전 상태 마이그레이션·find_class 제한을 확인한다. pickle.loads는 __init__을 호출하지 않아 배포 사이에 클래스 정의가 변경되면 새 필드가 없고, 레거시 클래스에서 진화된 클래스로 __getstate__/__setstate__를 통한 상태 버전 관리와 마이그레이션을 처리하며, threading.Lock은 제외 후 재생성(원본 잡혀 있어도 복원본 풀림)하고, RestrictedUnpickler로 find_class를 허용 목록으로 제한한다(허용된 클래스라도 속성에 허용되지 않은 전역 섞이면 거부).
- [slots-inheritance-dict-memory-design](packages/slots-inheritance-dict-memory-design/README.md): __slots__ 상속에서 __slots__를 빠뜨린 서브클래스에 __dict__·__weakref__가 되살아나 오타 속성이 조용히 저장되는 지점을 확인한다. 빈 __slots__·새 필드만 선언·dataclass(slots=True)·__init_subclass__ 검사(StrictSlots) 설계를 비교하고, __dictoffset__ 기반 검사와 원인 클래스 탐지(중간 계층 누수, tuple·BaseException 경계), 클래스 변수 충돌·lay-out conflict, 개당 바이트 상대 비교(3.12~3.14)를 다룬다.
- [struct-binary-layout-padding-byteorder-design](packages/struct-binary-layout-padding-byteorder-design/README.md): struct 모듈로 바이너리 레코드를 만들 때 네이티브 형식(@, 접두사 없음)이 C 정렬 규칙에 따라 패딩을 몰래 넣어 레코드 크기와 바이트 배치가 바뀌는 지점을 테스트로 고정하고, 명시 바이트 순서 형식(<, >, =, !)으로 고정 레이아웃을 쓰는 설계, 검증 헤더 설계(magic·version·payload_length 불일치 거절), 미리 컴파일한 struct.Struct 사용을 비교한다. 범위 밖 값·버퍼 길이 불일치·float 오버플로·s 형식 오류, 조용한 변형 경계(바이트 순서 혼동 1→16777216, ? 형식에 문자열, s 잘림/NUL 채움, f 정밀도 손실), 레코드 배열 나머지 바이트 거절, 패딩 계산을 다룬다.
- [mock-patch-lookup-site-autospec-design](packages/mock-patch-lookup-site-autospec-design/README.md): unittest.mock.patch가 정의 모듈이 아니라 사용 위치(lookup site)를 바꿔야 하는 지점과 autospec=True가 시그니처 변경을 드러내는 설계를 비교한다. from-import 방식은 사용 위치 패치가 필요하고 모듈 속성 접근은 정의 모듈 패치가 필요하며, 잘못된 위치를 패치하면 조용히 실패한다. 기본 Mock은 잘못된 인자·존재하지 않는 속성을 통과시키지만 autospec은 TypeError·AttributeError로 거절하고, 주입 설계의 기본값 함정(정의 시점 묶임)과 권장 설계(None 기본값 + 호출 시점 조회), create=True 오타 숨김, spec vs autospec 차이, 복원·데코레이터 순서·경계를 다룬다.
