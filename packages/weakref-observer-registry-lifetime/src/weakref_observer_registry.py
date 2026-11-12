"""약한 참조로 구독자 레지스트리를 만들 때 객체 수명과 WeakMethod·finalize 함정을 확인한다."""

import gc
import weakref
from typing import Callable, Any


class StrongRegistry:
    """강한 참조로 구독자를 저장하는 레지스트리다.
    
    구독자를 등록하면 이 레지스트리가 강한 참조를 유지하여 
    원본 변수를 del해도 구독자가 살아 있다 (메모리 누수 위험).
    """
    
    def __init__(self):
        self._subscribers: list[Callable[[str], None]] = []
    
    def subscribe(self, callback: Callable[[str], None]) -> None:
        """구독자를 등록한다. 강한 참조를 저장한다."""
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback).__name__}")
        self._subscribers.append(callback)
    
    def publish(self, event: str) -> int:
        """모든 구독자에게 이벤트를 전달하고 전달 개수를 반환한다."""
        for subscriber in self._subscribers:
            subscriber(event)
        return len(self._subscribers)
    
    def live_count(self) -> int:
        """살아 있는 구독자 수를 반환한다 (강한 참조이므로 모두 살아 있다)."""
        return len(self._subscribers)


class WeakRegistry:
    """약한 참조로 구독자를 저장하는 레지스트리다.
    
    함수는 weakref.ref로, 바운드 메서드는 weakref.WeakMethod로 저장한다.
    구독자가 삭제되면 약한 참조가 끊어져 다음 publish 시 자동으로 정리된다.
    """
    
    def __init__(self):
        self._subscribers: list[weakref.ref | weakref.WeakMethod] = []
    
    def subscribe(self, callback: Callable[[str], None]) -> None:
        """구독자를 등록한다. 약한 참조로 저장한다."""
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback).__name__}")
        
        if hasattr(callback, '__self__'):
            weak_ref = weakref.WeakMethod(callback)
        else:
            weak_ref = weakref.ref(callback)
        
        self._subscribers.append(weak_ref)
    
    def publish(self, event: str) -> int:
        """살아 있는 구독자에게만 이벤트를 전달하고 전달 개수를 반환한다.
        
        죽은 구독자는 자동으로 제거한다.
        """
        alive_subscribers = []
        delivered_count = 0
        
        for weak_ref in self._subscribers:
            callback = weak_ref()
            if callback is not None:
                callback(event)
                alive_subscribers.append(weak_ref)
                delivered_count += 1
        
        self._subscribers = alive_subscribers
        return delivered_count
    
    def live_count(self) -> int:
        """현재 살아 있는 구독자 수를 반환한다."""
        count = 0
        for weak_ref in self._subscribers:
            if weak_ref() is not None:
                count += 1
        return count


class Subscriber:
    """구독자 역할을 하는 클래스다."""
    
    def __init__(self, name: str, log: list[str]):
        self.name: str = name
        self.log: list[str] = log
    
    def on_event(self, event: str) -> None:
        """이벤트를 받아서 로그에 기록한다."""
        self.log.append(f"{self.name}: {event}")


class SlottedWithoutWeakref:
    """__slots__만 있고 __weakref__가 없는 클래스다.
    
    이 클래스의 인스턴스는 weakref를 걸 수 없다.
    """
    __slots__ = ('value',)
    
    def __init__(self, value: int):
        self.value = value


def demo_strong_registry_keeps_alive():
    """강한 참조 레지스트리는 구독자를 계속 살려 둔다 (메모리 누수 위험)."""
    print("=== 강한 참조 레지스트리: 구독자를 계속 살려 둔다 ===")
    
    log: list[str] = []
    registry = StrongRegistry()
    
    subscriber = Subscriber("구독자A", log)
    registry.subscribe(subscriber.on_event)
    
    print(f"등록 후 live_count: {registry.live_count()}")
    
    registry.publish("이벤트1")
    print(f"로그: {log}")
    
    del subscriber
    
    print(f"del 후 live_count: {registry.live_count()}")
    
    registry.publish("이벤트2")
    print(f"del 후에도 이벤트 전달됨: {log}")
    print()


def demo_weak_registry_auto_cleanup():
    """약한 참조 레지스트리는 구독자가 삭제되면 자동으로 끊어진다."""
    print("=== 약한 참조 레지스트리: 구독자 삭제 시 자동 정리 ===")
    
    log: list[str] = []
    registry = WeakRegistry()
    
    subscriber = Subscriber("구독자B", log)
    registry.subscribe(subscriber.on_event)
    
    print(f"등록 후 live_count: {registry.live_count()}")
    
    delivered = registry.publish("이벤트1")
    print(f"이벤트1 전달 개수: {delivered}, 로그: {log}")
    
    del subscriber
    
    print(f"del 후 live_count: {registry.live_count()}")
    
    delivered = registry.publish("이벤트2")
    print(f"del 후 전달 개수: {delivered}, 로그: {log}")
    print()


def demo_bound_method_weakref_pitfall():
    """바운드 메서드에 weakref.ref를 직접 걸면 즉시 None이 된다."""
    print("=== 바운드 메서드 weakref.ref 함정: 즉시 None ===")
    
    log: list[str] = []
    subscriber = Subscriber("구독자C", log)
    
    weak_ref_direct = weakref.ref(subscriber.on_event)
    print(f"weakref.ref(바운드메서드) 생성 직후: {weak_ref_direct()}")
    
    weak_method = weakref.WeakMethod(subscriber.on_event)
    callback = weak_method()
    if callback is not None:
        callback("이벤트1")
        print(f"weakref.WeakMethod는 작동함: {log}")
    else:
        print("weakref.WeakMethod도 None")
    
    print()


def demo_finalize_lifecycle():
    """weakref.finalize는 한 번만 실행되고, detach 후에는 실행되지 않는다."""
    print("=== weakref.finalize 수명: 한 번만 실행, detach 후 미실행 ===")
    
    log: list[str] = []
    
    class Target:
        def __init__(self, name: str):
            self.name = name
    
    target = Target("대상1")
    
    finalizer = weakref.finalize(target, log.append, "finalize 실행됨")
    
    print(f"finalize alive: {finalizer.alive}")
    
    result1 = finalizer()
    print(f"첫 번째 직접 호출 결과: {result1}, alive: {finalizer.alive}, 로그: {log}")
    
    result2 = finalizer()
    print(f"두 번째 직접 호출 결과: {result2}, alive: {finalizer.alive}, 로그: {log}")
    
    target2 = Target("대상2")
    finalizer2 = weakref.finalize(target2, log.append, "finalize2 실행됨")
    
    print(f"finalize2 alive: {finalizer2.alive}")
    
    finalizer2.detach()
    print(f"detach 후 alive: {finalizer2.alive}")
    
    del target2
    print(f"del 후 로그 (detach했으므로 실행 안 됨): {log}")
    print()


def demo_finalize_reference_trap():
    """finalize의 func/args가 대상을 참조하면 순환 참조로 수거되지 않는다."""
    print("=== weakref.finalize 함정: 대상 참조 시 순환 참조 ===")
    
    log: list[str] = []
    
    class Target:
        def __init__(self, name: str):
            self.name = name
    
    def cleanup_wrong(obj: Target):
        """대상 객체를 직접 받으면 순환 참조가 생긴다."""
        log.append(f"{obj.name} 정리")
    
    target = Target("순환참조대상")
    
    finalizer = weakref.finalize(target, cleanup_wrong, target)
    
    weak_ref = weakref.ref(target)
    print(f"finalize 등록 후 약한 참조: {weak_ref() is not None}")
    
    del target
    
    print(f"del 직후 약한 참조 (순환 참조로 살아 있음): {weak_ref() is not None}")
    
    gc.collect()
    
    print(f"gc.collect() 후 약한 참조 (여전히 살아 있음): {weak_ref() is not None}")
    print(f"로그: {log}")
    print("주의: finalize가 대상을 참조하면 영원히 수거되지 않는다!")
    print()


def demo_finalize_correct():
    """finalize를 올바르게 사용: 대상을 참조하지 않거나 약한 참조로 전달."""
    print("=== weakref.finalize 올바른 사용: 대상 참조 안 함 ===")
    
    log: list[str] = []
    
    class Target:
        def __init__(self, name: str):
            self.name = name
    
    def cleanup_correct(name: str):
        """대상 객체 대신 필요한 값만 받는다."""
        log.append(f"{name} 정리")
    
    target = Target("정상대상")
    
    finalizer = weakref.finalize(target, cleanup_correct, target.name)
    
    weak_ref = weakref.ref(target)
    print(f"finalize 등록 후 약한 참조: {weak_ref() is not None}")
    
    del target
    
    print(f"del 직후 약한 참조: {weak_ref() is not None}")
    print(f"로그: {log}")
    print()


def demo_circular_reference_gc():
    """참조 순환에 있는 객체는 gc.collect() 전까지 살아 있다."""
    print("=== 참조 순환과 gc.collect(): 명시 호출 전까지 살아 있음 ===")
    
    log: list[str] = []
    
    class Node:
        def __init__(self, name: str):
            self.name = name
            self.other: Node | None = None
    
    node1 = Node("노드1")
    node2 = Node("노드2")
    
    node1.other = node2
    node2.other = node1
    
    weak1 = weakref.ref(node1, lambda ref: log.append("node1 수거됨"))
    weak2 = weakref.ref(node2, lambda ref: log.append("node2 수거됨"))
    
    print(f"순환 참조 생성 후 약한 참조: node1={weak1() is not None}, node2={weak2() is not None}")
    
    del node1, node2
    
    print(f"del 직후 약한 참조: node1={weak1() is not None}, node2={weak2() is not None}")
    print(f"로그: {log}")
    
    gc.collect()
    
    print(f"gc.collect() 후 약한 참조: node1={weak1() is not None}, node2={weak2() is not None}")
    print(f"로그: {log}")
    print()


def demo_weakref_unsupported():
    """list, int, __weakref__ 없는 __slots__ 클래스는 약한 참조를 걸 수 없다."""
    print("=== 약한 참조 불가 대상: TypeError 경계 ===")
    
    try:
        weakref.ref([1, 2, 3])
        print("ERROR: list에 약한 참조를 걸 수 있다?")
    except TypeError as e:
        print(f"list에 약한 참조 불가: {e}")
    
    try:
        weakref.ref(42)
        print("ERROR: int에 약한 참조를 걸 수 있다?")
    except TypeError as e:
        print(f"int에 약한 참조 불가: {e}")
    
    try:
        obj = SlottedWithoutWeakref(100)
        weakref.ref(obj)
        print("ERROR: __weakref__ 없는 __slots__ 클래스에 약한 참조를 걸 수 있다?")
    except TypeError as e:
        print(f"__weakref__ 없는 __slots__ 클래스에 약한 참조 불가: {e}")
    
    print()


def demo_subscribe_non_callable():
    """호출 불가능한 객체를 subscribe하면 TypeError가 발생한다."""
    print("=== 호출 불가능한 객체 subscribe: TypeError ===")
    
    registry = WeakRegistry()
    
    try:
        registry.subscribe("not callable")
        print("ERROR: 문자열을 subscribe할 수 있다?")
    except TypeError as e:
        print(f"문자열 subscribe 불가: {e}")
    
    try:
        registry.subscribe(42)
        print("ERROR: 숫자를 subscribe할 수 있다?")
    except TypeError as e:
        print(f"숫자 subscribe 불가: {e}")
    
    print()


if __name__ == "__main__":
    demo_strong_registry_keeps_alive()
    demo_weak_registry_auto_cleanup()
    demo_bound_method_weakref_pitfall()
    demo_finalize_lifecycle()
    demo_finalize_reference_trap()
    demo_finalize_correct()
    demo_circular_reference_gc()
    demo_weakref_unsupported()
    demo_subscribe_non_callable()
    
    print("=== 모든 데모 완료 ===")
