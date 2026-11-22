"""__slots__ 상속의 __dict__ 누수, 검사 도구, 정의 시점 오류, 메모리 상대 비교를 검증한다."""

import copy
import pickle
import sys
import tracemalloc
import unittest
import weakref
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from slots_inheritance_design import (
    DataclassPoint,
    DataclassPoint3D,
    ExplicitDictPoint,
    LeakyMiddle,
    LeakyPoint,
    PlainPoint,
    Point3D,
    ReprPoint,
    SealedLeaf,
    SealedPoint,
    SlotPoint,
    SlotsDesignError,
    StrictPoint,
    StrictSlots,
    WeakrefSlotPoint,
    assert_no_instance_dict,
    bytes_per_instance,
    compare_memory,
    dict_sources,
    has_instance_dict,
    make_class_var_conflict,
    make_layout_conflict,
    slot_names,
)


class TypoAttributeTest(unittest.TestCase):
    """오타 속성 대입이 막히는지, 조용히 저장되는지 확인한다."""

    def test_slot_point_rejects_typo(self):
        p = SlotPoint(1.0, 2.0)
        with self.assertRaises(AttributeError):
            p.xx = 3.0
        self.assertFalse(hasattr(p, "__dict__"))

    def test_leaky_subclass_stores_typo_silently(self):
        p = LeakyPoint(1.0, 2.0)
        p.xx = 3.0  # 오류 없이 저장된다
        self.assertEqual(vars(p), {"xx": 3.0})
        self.assertEqual(p.x, 1.0)  # 진짜 x는 그대로다
        self.assertEqual(p.norm2(), 5.0)

    def test_leaky_subclass_keeps_slot_values_out_of_dict(self):
        p = LeakyPoint(1.0, 2.0)
        # 부모 슬롯 값은 __dict__가 아니라 슬롯에 있다
        self.assertNotIn("x", vars(p))
        self.assertNotIn("y", vars(p))

    def test_sealed_subclass_rejects_typo(self):
        p = SealedPoint(1.0, 2.0)
        with self.assertRaises(AttributeError):
            p.xx = 3.0
        self.assertEqual(p.norm2(), 5.0)

    def test_point3d_adds_only_new_slot(self):
        p = Point3D(1.0, 2.0, 3.0)
        self.assertEqual((p.x, p.y, p.z), (1.0, 2.0, 3.0))
        self.assertEqual(Point3D.__slots__, ("z",))
        with self.assertRaises(AttributeError):
            p.w = 4.0

    def test_leaky_subclass_also_regains_weakref(self):
        with self.assertRaises(TypeError):
            weakref.ref(SlotPoint(0.0, 0.0))
        p = LeakyPoint(0.0, 0.0)
        self.assertIs(weakref.ref(p)(), p)
        with self.assertRaises(TypeError):
            weakref.ref(SealedPoint(0.0, 0.0))

    def test_weakref_slot_enables_weak_reference_without_dict(self):
        p = WeakrefSlotPoint(1.0, 2.0)
        ref = weakref.ref(p)
        self.assertIs(ref(), p)
        self.assertFalse(has_instance_dict(WeakrefSlotPoint))
        del p
        self.assertIsNone(ref())


class InheritanceChainTest(unittest.TestCase):
    """중간 계층과 다중 상속에서 __dict__가 어떻게 되는지 확인한다."""

    def test_sealed_leaf_under_leaky_middle_still_has_dict(self):
        self.assertIn("__slots__", vars(SealedLeaf))
        self.assertTrue(has_instance_dict(SealedLeaf))
        leaf = SealedLeaf(1.0, 2.0)
        leaf.xx = 3.0
        self.assertEqual(vars(leaf), {"xx": 3.0})
        self.assertEqual(dict_sources(SealedLeaf), ["LeakyMiddle"])

    def test_explicit_dict_slot_is_reported(self):
        self.assertTrue(has_instance_dict(ExplicitDictPoint))
        self.assertEqual(dict_sources(ExplicitDictPoint), ["ExplicitDictPoint"])

    def test_empty_slot_mixin_keeps_layout_and_no_dict(self):
        p = ReprPoint(1.0, 2.0)
        self.assertFalse(has_instance_dict(ReprPoint))
        self.assertEqual(repr(p), "ReprPoint(x=1.0, y=2.0)")
        with self.assertRaises(AttributeError):
            p.xx = 3.0

    def test_two_nonempty_slot_bases_conflict(self):
        with self.assertRaisesRegex(TypeError, "lay-out conflict"):
            make_layout_conflict()

    def test_slot_name_conflicts_with_class_variable(self):
        with self.assertRaisesRegex(ValueError, "conflicts with class variable"):
            make_class_var_conflict()

    def test_dataclass_slots_subclass_adds_only_new_field(self):
        p = DataclassPoint3D(1.0, 2.0, 3.0)
        self.assertEqual(DataclassPoint3D.__slots__, ("z",))
        self.assertFalse(has_instance_dict(DataclassPoint3D))
        with self.assertRaises(AttributeError):
            p.xx = 1.0


class DetectionToolTest(unittest.TestCase):
    """has_instance_dict, dict_sources, assert_no_instance_dict를 확인한다."""

    def test_has_instance_dict_matches_real_instances(self):
        for cls, args in [
            (PlainPoint, (1.0, 2.0)),
            (SlotPoint, (1.0, 2.0)),
            (LeakyPoint, (1.0, 2.0)),
            (SealedPoint, (1.0, 2.0)),
            (Point3D, (1.0, 2.0, 3.0)),
            (SealedLeaf, (1.0, 2.0)),
            (ExplicitDictPoint, (1.0, 2.0)),
            (DataclassPoint, (1.0, 2.0)),
        ]:
            with self.subTest(cls=cls.__name__):
                self.assertEqual(
                    has_instance_dict(cls), hasattr(cls(*args), "__dict__")
                )

    def test_slots_in_own_namespace_is_not_enough(self):
        # '__slots__' in vars(cls) 만 보는 검사는 SealedLeaf를 놓친다
        self.assertIn("__slots__", vars(SealedLeaf))
        self.assertTrue(has_instance_dict(SealedLeaf))

    def test_builtin_base_without_slots_is_not_a_leak(self):
        class Pair(tuple):
            __slots__ = ()

        # tuple에는 '__slots__' 속성이 없지만 __dict__도 없다
        self.assertNotIn("__slots__", vars(tuple))
        self.assertFalse(has_instance_dict(Pair))
        self.assertEqual(dict_sources(Pair), [])
        assert_no_instance_dict(Pair)

    def test_builtin_base_with_dict_is_reported(self):
        class SlotError(Exception):
            __slots__ = ()

        self.assertTrue(has_instance_dict(SlotError))
        self.assertEqual(dict_sources(SlotError), ["BaseException"])

    def test_source_is_the_class_that_first_opened_dict(self):
        class Deeper(LeakyMiddle):
            pass

        # 이미 __dict__가 열린 부모 아래에서는 디스크립터를 새로 만들지 않는다
        self.assertNotIn("__dict__", vars(Deeper))
        self.assertTrue(has_instance_dict(Deeper))
        self.assertEqual(dict_sources(Deeper), ["LeakyMiddle"])

    def test_slot_names_handles_single_string(self):
        class One:
            __slots__ = "value"  # noqa: PLC0205 - 문자열 하나짜리 선언을 일부러 쓴다

        self.assertEqual(slot_names(One), ("value",))
        self.assertEqual(slot_names(Point3D), ("z",))
        self.assertEqual(slot_names(LeakyPoint), ())

    def test_assert_no_instance_dict_names_cause(self):
        for cls in (SlotPoint, SealedPoint, Point3D, ReprPoint, DataclassPoint3D):
            with self.subTest(cls=cls.__name__):
                assert_no_instance_dict(cls)
        with self.assertRaises(SlotsDesignError) as cm:
            assert_no_instance_dict(SealedLeaf)
        self.assertIn("LeakyMiddle", str(cm.exception))
        self.assertIsInstance(cm.exception, TypeError)


class StrictSlotsTest(unittest.TestCase):
    """__init_subclass__로 정의 시점에 막는 설계를 확인한다."""

    def test_strict_point_is_allowed(self):
        p = StrictPoint(1.0, 2.0)
        self.assertFalse(has_instance_dict(StrictPoint))
        with self.assertRaises(AttributeError):
            p.xx = 3.0

    def test_subclass_without_slots_fails_at_definition(self):
        with self.assertRaises(SlotsDesignError) as cm:

            class Careless(StrictPoint):
                pass

        self.assertIn("Careless", str(cm.exception))

    def test_subclass_with_dict_slot_fails_at_definition(self):
        with self.assertRaises(SlotsDesignError):

            class WantsDict(StrictPoint):
                __slots__ = ("__dict__",)

    def test_grandchild_with_empty_slots_is_allowed(self):
        class Labeled(StrictPoint):
            __slots__ = ("label",)

        class Final(Labeled):
            __slots__ = ()

        f = Final(1.0, 2.0)
        f.label = "a"
        self.assertEqual(f.label, "a")
        self.assertFalse(has_instance_dict(Final))

    def test_dataclass_slots_true_conflicts_with_strict_slots(self):
        # dataclass(slots=True)는 먼저 __slots__ 없는 클래스를 만든 뒤 새 클래스로 바꾼다.
        # 그 첫 클래스에서 __init_subclass__가 불려 정의가 실패한다.
        with self.assertRaises(SlotsDesignError):

            @dataclass(slots=True)
            class Record(StrictSlots):
                a: int


class CopyPickleTest(unittest.TestCase):
    """슬롯 값과 누수된 __dict__ 값이 복사·pickle에서 함께 보존되는지 확인한다."""

    def test_sealed_point_roundtrip(self):
        p = SealedPoint(1.0, 2.0)
        for q in (copy.copy(p), copy.deepcopy(p), pickle.loads(pickle.dumps(p))):
            with self.subTest(kind=type(q).__name__):
                self.assertEqual((q.x, q.y), (1.0, 2.0))
                self.assertFalse(hasattr(q, "__dict__"))

    def test_leaky_point_roundtrip_keeps_typo(self):
        p = LeakyPoint(1.0, 2.0)
        p.xx = 9.0
        q = pickle.loads(pickle.dumps(p))
        self.assertEqual((q.x, q.y, q.xx), (1.0, 2.0, 9.0))
        self.assertEqual(vars(q), {"xx": 9.0})


class MemoryComparisonTest(unittest.TestCase):
    """버전마다 절대값은 다르므로 같은 실행 안의 상대 크기만 검증한다."""

    @classmethod
    def setUpClass(cls):
        cls.sizes = compare_memory(n=20_000)

    def test_all_designs_measured_positive(self):
        self.assertEqual(
            set(self.sizes),
            {
                "PlainPoint",
                "SlotPoint",
                "SealedPoint",
                "DataclassPoint",
                "LeakyPoint",
                "LeakyPoint+vars()",
                "PlainPoint+vars()",
            },
        )
        for name, size in self.sizes.items():
            with self.subTest(name=name):
                self.assertGreater(size, 8.0)  # 리스트 칸(8바이트)보다 커야 한다

    def test_slots_smaller_than_plain(self):
        self.assertLess(self.sizes["SlotPoint"], self.sizes["PlainPoint"])

    def test_sealed_and_dataclass_cost_same_as_slot(self):
        slot = self.sizes["SlotPoint"]
        self.assertAlmostEqual(self.sizes["SealedPoint"], slot, delta=2.0)
        self.assertAlmostEqual(self.sizes["DataclassPoint"], slot, delta=2.0)

    def test_leaky_costs_more_than_slot_even_without_extra_attribute(self):
        self.assertGreater(self.sizes["LeakyPoint"], self.sizes["SlotPoint"] + 8.0)

    def test_materialized_dict_costs_more(self):
        self.assertGreater(
            self.sizes["LeakyPoint+vars()"], self.sizes["LeakyPoint"] + 32.0
        )

    def test_does_not_stop_callers_tracemalloc(self):
        tracemalloc.start()
        try:
            bytes_per_instance(lambda: SlotPoint(1.0, 2.0), n=100)
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()
        bytes_per_instance(lambda: SlotPoint(1.0, 2.0), n=100)
        self.assertFalse(tracemalloc.is_tracing())

    def test_touch_dict_on_slot_class_raises(self):
        with self.assertRaises(TypeError):
            bytes_per_instance(lambda: SlotPoint(1.0, 2.0), n=10, touch_dict=True)


if __name__ == "__main__":
    unittest.main()
