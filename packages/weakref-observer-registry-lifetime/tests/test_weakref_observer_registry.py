"""약한 참조 구독자 레지스트리의 객체 수명과 함정을 검증하는 테스트다."""

import gc
import types
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


# 테스트용 로그 전역 변수
builtin_test_log: list[str] = []


def builtin_callback(event: str) -> None:
    """모듈 수준 함수로 내장 함수 테스트에 사용한다."""
    builtin_test_log.append(f"builtin: {event}")


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
    
    def setUp(self):
        """테스트 전 잔여 객체 정리."""
        gc.collect()
        builtin_test_log.clear()
    
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
    
    def test_builtin_function_subscription(self):
        """모듈 수준 함수를 subscribe할 수 있다 (len/list.append 같은 builtin_function_or_method는 __self__가 있어도 MethodType이 아니므로 weakref.ref 사용, 즉시 None됨)."""
        registry = WeakRegistry()
        
        registry.subscribe(builtin_callback)
        self.assertEqual(registry.live_count(), 1)
        
        delivered = registry.publish("test_event")
        self.assertEqual(delivered, 1)
        self.assertEqual(builtin_test_log, ["builtin: test_event"])
    
    def test_temporary_bound_method_immediately_dead(self):
        """다른 참조 없이 생성된 임시 객체의 바운드 메서드는 등록 직후 live_count가 0이 된다 (CPython 참조 카운트 의존)."""
        registry = WeakRegistry()
        log: list[str] = []
        
        registry.subscribe(Subscriber("temp", log).on_event)
        
        self.assertEqual(registry.live_count(), 0)
    
    def test_lambda_without_reference_immediately_dead(self):
        """다른 참조 없는 lambda를 subscribe하면 등록 직후 live_count가 0이 된다 (CPython 참조 카운트 의존)."""
        registry = WeakRegistry()
        
        registry.subscribe(lambda event: None)
        
        self.assertEqual(registry.live_count(), 0)


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
    
    def test_finalize_executes_once_manual_call(self):
        """finalize 콜백을 수동으로 호출하면 한 번만 실행되고 반환값을 돌려준다."""
        log: list[str] = []
        
        class Target:
            pass
        
        def cleanup_with_return(msg: str) -> str:
            log.append(msg)
            return "cleanup_done"
        
        target = Target()
        finalizer = weakref.finalize(target, cleanup_with_return, "executed")
        
        self.assertTrue(finalizer.alive)
        
        result1 = finalizer()
        self.assertEqual(result1, "cleanup_done")
        self.assertFalse(finalizer.alive)
        self.assertEqual(log, ["executed"])
        
        result2 = finalizer()
        self.assertIsNone(result2)
        self.assertFalse(finalizer.alive)
        self.assertEqual(log, ["executed"])
        
        del target
        
        self.assertEqual(log, ["executed"])
    
    def test_finalize_auto_execution_on_del(self):
        """수동 호출 없이 del만으로 finalize가 자동 실행된다."""
        log: list[str] = []
        
        class Target:
            pass
        
        def cleanup_with_return(msg: str) -> str:
            log.append(msg)
            return "auto_cleanup"
        
        target = Target()
        finalizer = weakref.finalize(target, cleanup_with_return, "auto_executed")
        
        self.assertTrue(finalizer.alive)
        
        del target
        
        self.assertFalse(finalizer.alive)
        self.assertEqual(log, ["auto_executed"])
    
    def test_finalize_detach_prevents_execution(self):
        """detach 후에는 대상이 수거되어도 콜백이 실행되지 않는다."""
        log: list[str] = []
        
        class Target:
            pass
        
        target = Target()
        weak_ref = weakref.ref(target)
        finalizer = weakref.finalize(target, log.append, "should not execute")
        
        self.assertTrue(finalizer.alive)
        self.assertIsNotNone(weak_ref())
        
        finalizer.detach()
        self.assertFalse(finalizer.alive)
        
        del target
        
        self.assertIsNone(weak_ref())
        self.assertEqual(log, [])


class TestFinalizeReferenceTrap(unittest.TestCase):
    """finalize가 대상을 args로 받으면 레지스트리가 강하게 붙잡아 수거되지 않는 함정을 확인한다."""
    
    def test_finalize_referencing_target_held_by_registry(self):
        """finalize의 args가 대상을 참조하면 finalize 레지스트리가 강하게 붙잡아 수거되지 않는다."""
        log: list[str] = []
        
        class Target:
            def __init__(self, name: str):
                self.name = name
        
        def cleanup_wrong(obj: Target):
            log.append(f"{obj.name} cleaned")
        
        target = Target("held")
        
        finalizer = weakref.finalize(target, cleanup_wrong, target)
        
        weak_ref = weakref.ref(target)
        self.assertIsNotNone(weak_ref())
        
        del target
        
        self.assertIsNotNone(weak_ref())
        
        gc.collect()
        
        self.assertIsNotNone(weak_ref())
        self.assertEqual(log, [])
        
        detached = finalizer.detach()
        self.assertIsNotNone(detached)
        
        del detached
        gc.collect()
        
        self.assertIsNone(weak_ref())
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
    
    def setUp(self):
        """테스트 전 잔여 객체 정리."""
        gc.collect()
    
    def test_circular_reference_survives_del(self):
        """참조 순환이 있으면 del 직후에는 수거되지 않는다."""
        log: list[str] = []
        
        class Node:
            def __init__(self, name: str):
                self.name = name
                self.other: Node | None = None
        
        gc_was_enabled = gc.isenabled()
        gc.disable()
        
        try:
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
        finally:
            if gc_was_enabled:
                gc.enable()
    
    def test_circular_reference_collected_after_gc(self):
        """gc.collect()를 호출하면 순환 참조가 해결되고 수거된다."""
        log: list[str] = []
        
        class Node:
            def __init__(self, name: str):
                self.name = name
                self.other: Node | None = None
        
        gc_was_enabled = gc.isenabled()
        gc.disable()
        
        try:
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
        finally:
            if gc_was_enabled:
                gc.enable()


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
