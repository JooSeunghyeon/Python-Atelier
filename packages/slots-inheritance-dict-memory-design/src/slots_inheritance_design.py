"""__slots__ 상속에서 __dict__가 되살아나는 지점과 막는 설계, 메모리 비용을 비교한다.

실행: python3 src/slots_inheritance_design.py
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 1. 기준 클래스: 일반 클래스와 __slots__ 클래스
# ---------------------------------------------------------------------------


class PlainPoint:
    """__slots__가 없는 일반 클래스. 인스턴스마다 __dict__를 쓸 수 있다."""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class SlotPoint:
    """x, y만 슬롯으로 두는 클래스. __dict__와 __weakref__가 없다."""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


# ---------------------------------------------------------------------------
# 2. 상속에서 __dict__가 되살아나는 경우
# ---------------------------------------------------------------------------


class LeakyPoint(SlotPoint):
    """함정: __slots__를 다시 선언하지 않은 서브클래스.

    부모가 __slots__를 가져도 이 클래스에서 __dict__와 __weakref__가 다시 생긴다.
    오타 속성 대입이 오류 없이 저장된다.
    """

    def norm2(self) -> float:
        return self.x * self.x + self.y * self.y


class SealedPoint(SlotPoint):
    """해결: 새 필드가 없으면 빈 __slots__를 선언한다."""

    __slots__ = ()

    def norm2(self) -> float:
        return self.x * self.x + self.y * self.y


class Point3D(SlotPoint):
    """해결: 새 필드만 __slots__에 적는다. 부모 슬롯을 다시 적지 않는다."""

    __slots__ = ("z",)

    def __init__(self, x: float, y: float, z: float) -> None:
        super().__init__(x, y)
        self.z = z


class LeakyMiddle(SlotPoint):
    """중간 계층에서 __slots__를 빠뜨린 클래스."""


class SealedLeaf(LeakyMiddle):
    """함정: 맨 아래에서 빈 __slots__를 선언해도 중간 계층이 연 __dict__는 닫히지 않는다."""

    __slots__ = ()


class ExplicitDictPoint(SlotPoint):
    """'__dict__'를 슬롯에 직접 적은 클래스. 의도적으로 __dict__를 연다."""

    __slots__ = ("__dict__",)


class WeakrefSlotPoint:
    """약한 참조가 필요하면 '__weakref__'를 슬롯에 넣는다."""

    __slots__ = ("x", "y", "__weakref__")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


@dataclass(slots=True)
class DataclassPoint:
    """dataclass(slots=True)는 필드 목록으로 __slots__를 만든다."""

    x: float
    y: float


@dataclass(slots=True)
class DataclassPoint3D(DataclassPoint):
    """slots=True 서브클래스도 새 필드만 슬롯으로 추가한다."""

    z: float = 0.0


# ---------------------------------------------------------------------------
# 3. 검사 도구
# ---------------------------------------------------------------------------


def has_instance_dict(cls: type) -> bool:
    """cls의 인스턴스가 __dict__를 가질 수 있으면 True다.

    CPython은 __dict__ 위치를 __dictoffset__에 둔다. 0이면 __dict__가 없다.
    '__slots__' in cls.__dict__ 만 보면 중간 계층에서 열린 __dict__를 놓친다.
    """
    return cls.__dictoffset__ != 0


def dict_sources(cls: type) -> list[str]:
    """MRO에서 __dict__ 디스크립터를 직접 만든 클래스, 즉 __dict__를 처음 연 클래스 이름을 반환한다.

    __slots__를 빠뜨린 클래스와 '__dict__'를 슬롯에 적은 클래스가 여기에 잡힌다.
    이미 __dict__가 열린 부모 아래의 서브클래스는 디스크립터를 새로 만들지 않으므로
    원인 목록에는 처음 연 클래스만 남는다.
    __slots__가 없는 C 내장 타입(tuple 등)은 __dict__가 없으므로 잡히지 않는다.
    """
    return [base.__name__ for base in cls.__mro__ if "__dict__" in vars(base)]


def slot_names(cls: type) -> tuple[str, ...]:
    """cls가 직접 선언한 슬롯 이름. __slots__ = "x" 처럼 문자열 하나도 처리한다."""
    declared = vars(cls).get("__slots__", ())
    if isinstance(declared, str):
        return (declared,)
    return tuple(declared)


class SlotsDesignError(TypeError):
    """__slots__ 설계가 __dict__를 다시 연 경우의 오류."""


def assert_no_instance_dict(cls: type) -> None:
    """cls 인스턴스에 __dict__가 생기면 원인 클래스를 담아 SlotsDesignError를 낸다."""
    if has_instance_dict(cls):
        sources = ", ".join(dict_sources(cls)) or "(알 수 없음)"
        raise SlotsDesignError(
            f"{cls.__name__} 인스턴스에 __dict__가 생긴다. 원인: {sources}"
        )


class StrictSlots:
    """서브클래스를 정의하는 순간 __dict__가 열렸는지 검사하는 기반 클래스.

    __init_subclass__는 클래스 객체가 만들어진 뒤 호출되므로 __dictoffset__을
    볼 수 있다. 테스트가 아닌 import 시점에 실수를 드러낸다.
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        assert_no_instance_dict(cls)


class StrictPoint(StrictSlots):
    """StrictSlots를 상속한 좌표 클래스."""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


# ---------------------------------------------------------------------------
# 4. 정의 시점 오류 재현
# ---------------------------------------------------------------------------


def make_class_var_conflict() -> type:
    """슬롯 이름과 같은 클래스 변수(기본값)를 두면 ValueError가 난다."""
    return type("Conflict", (), {"__slots__": ("x",), "x": 0})


def make_layout_conflict() -> type:
    """비어 있지 않은 __slots__ 부모 둘을 다중 상속하면 TypeError가 난다."""

    class HasA:
        __slots__ = ("a",)

    class HasB:
        __slots__ = ("b",)

    return type("Both", (HasA, HasB), {})


class ReprMixin:
    """믹스인은 빈 __slots__로 두어야 슬롯 클래스와 함께 쓸 수 있다."""

    __slots__ = ()

    def __repr__(self) -> str:
        fields = ", ".join(
            f"{name}={getattr(self, name)!r}"
            for klass in reversed(type(self).__mro__)
            for name in slot_names(klass)
            if name not in ("__dict__", "__weakref__") and hasattr(self, name)
        )
        return f"{type(self).__name__}({fields})"


class ReprPoint(ReprMixin, SlotPoint):
    """빈 슬롯 믹스인 + 슬롯 부모 조합. __dict__가 생기지 않는다."""

    __slots__ = ()


# ---------------------------------------------------------------------------
# 5. 메모리 비교
# ---------------------------------------------------------------------------


def bytes_per_instance(
    factory: Callable[[], object], n: int = 20_000, touch_dict: bool = False
) -> float:
    """factory로 n개를 만들어 리스트에 담았을 때 tracemalloc 기준 개당 바이트.

    touch_dict=True면 각 인스턴스에서 vars(obj)를 한 번 불러 __dict__를 만든다.
    (직렬화, 디버거, copy 등이 __dict__를 읽는 상황을 흉내 낸다.)
    값은 CPython 버전마다 다르므로 절대값이 아니라 같은 실행 안의 상대 비교로 쓴다.
    """
    gc.collect()
    started_here = not tracemalloc.is_tracing()
    if started_here:
        tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        items: list[object] = []
        append = items.append
        for _ in range(n):
            obj = factory()
            if touch_dict:
                vars(obj)
            append(obj)
        after, _ = tracemalloc.get_traced_memory()
    finally:
        # 호출 전부터 추적 중이었다면 남의 추적을 끄지 않는다
        if started_here:
            tracemalloc.stop()
    del items
    return (after - before) / n


def compare_memory(n: int = 20_000) -> dict[str, float]:
    """설계별 개당 바이트를 같은 조건에서 측정한다."""
    return {
        "PlainPoint": bytes_per_instance(lambda: PlainPoint(1.0, 2.0), n),
        "SlotPoint": bytes_per_instance(lambda: SlotPoint(1.0, 2.0), n),
        "SealedPoint": bytes_per_instance(lambda: SealedPoint(1.0, 2.0), n),
        "DataclassPoint": bytes_per_instance(lambda: DataclassPoint(1.0, 2.0), n),
        "LeakyPoint": bytes_per_instance(lambda: LeakyPoint(1.0, 2.0), n),
        "LeakyPoint+vars()": bytes_per_instance(
            lambda: LeakyPoint(1.0, 2.0), n, touch_dict=True
        ),
        "PlainPoint+vars()": bytes_per_instance(
            lambda: PlainPoint(1.0, 2.0), n, touch_dict=True
        ),
    }


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Python {sys.version.split()[0]}")

    print("\n[1] 오타 속성 대입")
    point_classes: tuple[type[SlotPoint], ...] = (SlotPoint, LeakyPoint, SealedPoint)
    for cls in point_classes:
        p = cls(1.0, 2.0)
        try:
            p.xx = 3.0  # type: ignore[attr-defined]  # x를 고치려다 낸 오타
            print(f"  {cls.__name__:12s} 저장됨 -> {vars(p)}")
        except AttributeError as exc:
            print(f"  {cls.__name__:12s} AttributeError: {exc}")

    print("\n[2] __dict__ 여부와 원인 클래스")
    checked: tuple[type, ...] = (
        SlotPoint,
        LeakyPoint,
        SealedPoint,
        Point3D,
        SealedLeaf,
        ExplicitDictPoint,
        ReprPoint,
        DataclassPoint3D,
    )
    for klass in checked:
        print(
            f"  {klass.__name__:18s} dict={has_instance_dict(klass)!s:5s} "
            f"원인={dict_sources(klass)}"
        )

    print("\n[3] StrictSlots가 정의 시점에 막는다")
    try:

        class Careless(StrictPoint):  # 일부러 __slots__를 빠뜨린다
            pass
    except SlotsDesignError as exc:
        print(f"  SlotsDesignError: {exc}")

    print("\n[4] 정의 시점 오류")
    for maker in (make_class_var_conflict, make_layout_conflict):
        try:
            maker()
        except (ValueError, TypeError) as exc:
            print(f"  {maker.__name__}: {type(exc).__name__}: {exc}")
    try:
        weakref.ref(SlotPoint(0.0, 0.0))
    except TypeError as exc:
        print(f"  weakref.ref(SlotPoint): TypeError: {exc}")
    print(
        f"  weakref.ref(WeakrefSlotPoint) 성공: "
        f"{weakref.ref(WeakrefSlotPoint(0.0, 0.0)) is not None}"
    )
    print(f"  repr: {ReprPoint(1.0, 2.0)!r}")

    print("\n[5] 개당 바이트 (n=20000, tracemalloc, 리스트 칸 8바이트 포함)")
    for name, size in compare_memory().items():
        print(f"  {name:18s} {size:7.1f}")


if __name__ == "__main__":
    main()
