"""약한 참조 구독자 레지스트리의 객체 수명과 함정을 검증하는 테스트다."""

import gc
import unittest
import weakref
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(project_root))

from weakref_observer_registry import (
    StrongRegistry,
    WeakRegistry,
    Subscriber,
    SlottedWithoutWeakref,
)


class TestStrongRegistry(unittest.TestCase):
    """강한 참조 레지스트리 테스트다."""
    
    def test_keeps_subscriber_alive_after_del(self):
        """원본 변수를 del해도 강한 참조가 구독자를 살려 둔다."""
        log: list[str] = []
        registry = StrongRegistry()
        
        subscriber = Subscriber("A", log)
        registry.subscribe(subscriber.on_event)
        
        self.assertEqual(registry.live_count(), 1)
        
        registry.publish("event1")
        self.assertEqual(log, ["A: event1"])
        
        del subscriber
        
        self.assertEqual(registry.live_count(), 1)
        
        registry.publish("event2")
        self.assertEqual(log, ["A: event1", "A: event2"])
    
    def test_subscribe_non_callable_raises_type_error(self):
        """호출 불가능한 객체를 subscribe하면 TypeError가 발생한다."""
        registry = StrongRegistry()
        
        with self.assertRaises(TypeError) as cm:
            registry.subscribe("not callable")
        
        self.assertIn("callable", str(cm.exception))
        
        with self.assertRaises(TypeError) as cm:
            registry.subscribe(42)
        
        self.assertIn("callable", str(cm.exception))


class TestWeakRegistry(unittest.TestCase):
    """약한 참조 레지스트리 테스트다."""
    
    def test_auto_cleanup_when_subscriber_deleted(self):
        """구독자가 삭제되면 약한 참조가 끊어져 publish가 전달하지 않는다."""
        log: list[str] = []
        registry = WeakRegistry()
        
        subscriber = Subscriber("B", log)
        registry.subscribe(subscriber.on_event)
        
        self.assertEqual(registry.live_count(), 1)
        
        delivered = registry.publish("event1")
        self.assertEqual(delivered, 1)
        self.assertEqual(log, ["B: event1"])
        
        del subscriber
        
        self.assertEqual(registry.live_count(), 0)
        
        delivered = registry.publish("event2")
        self.assertEqual(delivered, 0)
        self.assertEqual(log, ["B: event1"])
    
    def test_function_weakref(self):
        """일반 함수는 weakref.ref로 저장하고 정상 작동한다."""
        log: list[str] = []
        
        def callback(event: str):
            log.append(f"func: {event}")
        
        registry = WeakRegistry()
        registry.subscribe(callback)
        
        self.assertEqual(registry.live_count(), 1)
        
        delivered = registry.publish("event1")
        self.assertEqual(delivered, 1)
        self.assertEqual(log, ["func: event1"])
    
    def test_bound_method_with_weak_method(self):
        """바운드 메서드는 WeakMethod로 저장하여 인스턴스가 살아 있는 동안 작동한다."""
        log: list[str] = []
        registry = WeakRegistry()
        
        subscriber = Subscriber("C", log)
        registry.subscribe(subscriber.on_event)
        
        self.assertEqual(registry.live_count(), 1)
        
        delivered = registry.publish("event1")
        self.assertEqual(delivered, 1)
        self.assertEqual(log, ["C: event1"])
        
        del subscriber
        
        self.assertEqual(registry.live_count(), 0)
    
    def test_subscribe_non_callable_raises_type_error(self):
        """호출 불가능한 객체를 subscribe하면 TypeError가 발생한다."""
        registry = WeakRegistry()
        
        with self.assertRaises(TypeError) as cm:
            registry.subscribe([1, 2, 3])
        
        self.assertIn("callable", str(cm.exception))


class TestBoundMethodWeakrefPitfall(unittest.TestCase):
    """바운드 메서드에 weakref.ref를 직접 걸면 즉시 None이 되는 함정을 확인한다."""
    
    def test_weakref_ref_on_bound_method_immediately_none(self):
        """바운드 메서드에 weakref.ref를 걸면 임시 메서드 객체가 즉시 수거된다."""
        log: list[str] = []
        subscriber = Subscriber("D", log)
        
        weak_ref = weakref.ref(subscriber.on_event)
        
        self.assertIsNone(weak_ref())
    
    def test_weak_method_keeps_bound_method_alive(self):
        """WeakMethod는 인스턴스가 살아 있는 동안 메서드 호출이 가능하다."""
        log: list[str] = []
        subscriber = Subscriber("E", log)
        
        weak_method = weakref.WeakMethod(subscriber.on_event)
        
        callback = weak_method()
        self.assertIsNotNone(callback)
        
        callback("event1")
        self.assertEqual(log, ["E: event1"])
        
        del callback
        del subscriber
        
        callback_after_del = weak_method()
        self.assertIsNone(callback_after_del)


class TestFinalizeLifecycle(unittest.TestCase):
    """weakref.finalize의 수명과 동작을 확인한다."""
    
    def test_finalize_executes_once(self):
        """finalize 콜백은 한 번만 실행된다."""
        log: list[str] = []
        
        class Target:
            pass
        
        target = Target()
        finalizer = weakref.finalize(target, log.append, "executed")
        
        self.assertTrue(finalizer.alive)
        
        result1 = finalizer()
        self.assertIsNone(result1)
        self.assertFalse(finalizer.alive)
        self.assertEqual(log, ["executed"])
        
        result2 = finalizer()
        self.assertIsNone(result2)
        self.assertFalse(finalizer.alive)
        self.assertEqual(log, ["executed"])
    
    def test_finalize_detach_prevents_execution(self):
        """detach 후에는 대상이 수거되어도 콜백이 실행되지 않는다."""
        log: list[str] = []
        
        class Target:
            pass
        
        target = Target()
        finalizer = weakref.finalize(target, log.append, "should not execute")
        
        self.assertTrue(finalizer.alive)
        
        finalizer.detach()
        self.assertFalse(finalizer.alive)
        
        del target
        
        self.assertEqual(log, [])


class TestFinalizeReferenceTrap(unittest.TestCase):
    """finalize가 대상을 참조하면 순환 참조로 수거되지 않는 함정을 확인한다."""
    
    def test_finalize_referencing_target_creates_cycle(self):
        """finalize의 func/args가 대상을 참조하면 영원히 수거되지 않는다."""
        log: list[str] = []
        
        class Target:
            def __init__(self, name: str):
                self.name = name
        
        def cleanup_wrong(obj: Target):
            log.append(f"{obj.name} cleaned")
        
        target = Target("cycle")
        
        finalizer = weakref.finalize(target, cleanup_wrong, target)
        
        weak_ref = weakref.ref(target)
        self.assertIsNotNone(weak_ref())
        
        del target
        
        self.assertIsNotNone(weak_ref())
        
        gc.collect()
        
        self.assertIsNotNone(weak_ref())
        self.assertEqual(log, [])
    
    def test_finalize_correct_usage(self):
        """대상을 참조하지 않으면 정상적으로 수거된다."""
        log: list[str] = []
        
        class Target:
            def __init__(self, name: str):
                self.name = name
        
        def cleanup_correct(name: str):
            log.append(f"{name} cleaned")
        
        target = Target("correct")
        
        finalizer = weakref.finalize(target, cleanup_correct, target.name)
        
        weak_ref = weakref.ref(target)
        self.assertIsNotNone(weak_ref())
        
        del target
        
        self.assertIsNone(weak_ref())
        self.assertEqual(log, ["correct cleaned"])


class TestCircularReferenceGC(unittest.TestCase):
    """참조 순환에 있는 객체는 gc.collect() 전까지 살아 있다."""
    
    def test_circular_reference_survives_del(self):
        """참조 순환이 있으면 del 직후에는 수거되지 않는다."""
        log: list[str] = []
        
        class Node:
            def __init__(self, name: str):
                self.name = name
                self.other: Node | None = None
        
        node1 = Node("node1")
        node2 = Node("node2")
        
        node1.other = node2
        node2.other = node1
        
        weak1 = weakref.ref(node1, lambda ref: log.append("node1 collected"))
        weak2 = weakref.ref(node2, lambda ref: log.append("node2 collected"))
        
        self.assertIsNotNone(weak1())
        self.assertIsNotNone(weak2())
        
        del node1, node2
        
        self.assertIsNotNone(weak1())
        self.assertIsNotNone(weak2())
        self.assertEqual(log, [])
    
    def test_circular_reference_collected_after_gc(self):
        """gc.collect()를 호출하면 순환 참조가 해결되고 수거된다."""
        log: list[str] = []
        
        class Node:
            def __init__(self, name: str):
                self.name = name
                self.other: Node | None = None
        
        node1 = Node("node1")
        node2 = Node("node2")
        
        node1.other = node2
        node2.other = node1
        
        weak1 = weakref.ref(node1, lambda ref: log.append("node1 collected"))
        weak2 = weakref.ref(node2, lambda ref: log.append("node2 collected"))
        
        del node1, node2
        
        gc.collect()
        
        self.assertIsNone(weak1())
        self.assertIsNone(weak2())
        self.assertIn("node1 collected", log)
        self.assertIn("node2 collected", log)


class TestWeakrefUnsupported(unittest.TestCase):
    """약한 참조를 걸 수 없는 대상을 확인한다."""
    
    def test_weakref_on_list_raises_type_error(self):
        """list는 약한 참조를 걸 수 없다."""
        with self.assertRaises(TypeError) as cm:
            weakref.ref([1, 2, 3])
        
        self.assertIn("weak reference", str(cm.exception).lower())
    
    def test_weakref_on_int_raises_type_error(self):
        """int는 약한 참조를 걸 수 없다."""
        with self.assertRaises(TypeError) as cm:
            weakref.ref(42)
        
        self.assertIn("weak reference", str(cm.exception).lower())
    
    def test_weakref_on_slotted_without_weakref_raises_type_error(self):
        """__slots__만 있고 __weakref__가 없는 클래스는 약한 참조를 걸 수 없다."""
        obj = SlottedWithoutWeakref(100)
        
        with self.assertRaises(TypeError) as cm:
            weakref.ref(obj)
        
        self.assertIn("weak reference", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
