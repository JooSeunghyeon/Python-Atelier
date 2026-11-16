"""pickle 상태 마이그레이션과 보안 경계를 검증하는 테스트다."""

import pickle
import io
import copy
import unittest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(project_root))

from pickle_state_migration import (
    UserV1,
    UserV2,
    UserV1Legacy,
    UserV2Legacy,
    UserVersioned,
    UserFutureVersion,
    ResourceWithLock,
    ResourceWithLockFixed,
    ObjectWithForbiddenGlobal,
    RestrictedUnpickler,
    safe_loads,
    replace_class_in_module,
)


class TestV1ToV2AttributeError(unittest.TestCase):
    """V1→V2 복원 시 AttributeError 함정을 확인한다."""
    
    def test_v1_to_v2_missing_attribute(self):
        """V1으로 저장된 객체를 V2 클래스로 복원하면 email이 없어 AttributeError가 발생한다."""
        module_name = 'pickle_state_migration'
        
        user_v1 = UserV1("Alice")
        pickled = pickle.dumps(user_v1)
        
        self.assertEqual(user_v1.name, "Alice")
        
        original_class = replace_class_in_module(module_name, 'UserV1', UserV2)
        
        try:
            UserV2._init_call_count = 0
            restored = pickle.loads(pickled)
            
            self.assertIs(type(restored), UserV2)
            self.assertEqual(restored.name, "Alice")
            self.assertEqual(UserV2._init_call_count, 0)
            self.assertNotIn('email', vars(restored))
            
            with self.assertRaises(AttributeError) as cm:
                _ = restored.email
            
            self.assertIn("email", str(cm.exception))
        finally:
            replace_class_in_module(module_name, 'UserV1', original_class)


class TestVersionedMigration(unittest.TestCase):
    """상태 버전 관리와 마이그레이션을 확인한다."""
    
    def test_v1_legacy_to_versioned_migration(self):
        """레거시 V1(버전 키 없음)을 최신 클래스로 복원하면 기본 버전 1로 마이그레이션된다."""
        module_name = 'pickle_state_migration'
        
        user_v1 = UserV1Legacy("Bob")
        pickled = pickle.dumps(user_v1)
        
        original_class = replace_class_in_module(module_name, 'UserV1Legacy', UserVersioned)
        
        try:
            restored = pickle.loads(pickled)
            
            self.assertEqual(restored.full_name, "Bob")
            self.assertEqual(restored.email, "")
            self.assertEqual(restored._state_version, 3)
        finally:
            replace_class_in_module(module_name, 'UserV1Legacy', original_class)
    
    def test_v2_legacy_to_versioned_migration(self):
        """레거시 V2를 최신 클래스로 복원하면 버전 2로 마이그레이션된다."""
        module_name = 'pickle_state_migration'
        
        user_v2 = UserV2Legacy("Charlie", "charlie@example.com")
        pickled = pickle.dumps(user_v2)
        
        original_class = replace_class_in_module(module_name, 'UserV2Legacy', UserVersioned)
        
        try:
            restored = pickle.loads(pickled)
            
            self.assertEqual(restored.full_name, "Charlie")
            self.assertEqual(restored.email, "charlie@example.com")
            self.assertEqual(restored._state_version, 3)
        finally:
            replace_class_in_module(module_name, 'UserV2Legacy', original_class)
    
    def test_future_version_via_pickle_loads(self):
        """미래 버전 상태를 pickle.loads로 복원하면 ValueError가 발생한다."""
        module_name = 'pickle_state_migration'
        
        future = UserFutureVersion("test_data")
        pickled = pickle.dumps(future)
        
        original_class = replace_class_in_module(module_name, 'UserFutureVersion', UserVersioned)
        
        try:
            with self.assertRaises(ValueError) as cm:
                pickle.loads(pickled)
            
            self.assertIn("알 수 없는 상태 버전", str(cm.exception))
            self.assertIn("99", str(cm.exception))
        finally:
            replace_class_in_module(module_name, 'UserFutureVersion', original_class)
    
    def test_future_version_via_setstate(self):
        """미래 버전 상태를 __setstate__ 직접 호출로 복원하면 ValueError가 발생한다."""
        state = {
            '_state_version': 99,
            'unknown_field': 'value'
        }
        
        user = UserVersioned("dummy", "dummy@example.com")
        
        with self.assertRaises(ValueError) as cm:
            user.__setstate__(state)
        
        self.assertIn("알 수 없는 상태 버전", str(cm.exception))
        self.assertIn("99", str(cm.exception))
    
    def test_already_latest_version_unchanged(self):
        """이미 최신 버전인 상태를 재복원해도 변경되지 않는다."""
        user_v3 = UserVersioned("Eve", "eve@example.com")
        pickled = pickle.dumps(user_v3)
        
        restored = pickle.loads(pickled)
        
        self.assertEqual(restored.full_name, "Eve")
        self.assertEqual(restored.email, "eve@example.com")
        self.assertEqual(restored._state_version, 3)


class TestUnpicklableLock(unittest.TestCase):
    """pickle 불가 속성(threading.Lock) 처리를 확인한다."""
    
    def test_lock_without_getstate_raises_type_error(self):
        """threading.Lock을 그대로 pickle하면 TypeError가 발생한다."""
        resource = ResourceWithLock("res1")
        
        with self.assertRaises(TypeError) as cm:
            pickle.dumps(resource)
        
        error_msg = str(cm.exception).lower()
        self.assertTrue(
            "lock" in error_msg or "_thread" in error_msg,
            f"예상치 못한 에러 메시지: {cm.exception}"
        )
    
    def test_lock_with_getstate_picklable(self):
        """__getstate__/__setstate__로 Lock을 처리하면 pickle이 가능하다."""
        resource = ResourceWithLockFixed("res2")
        
        acquired = resource.acquire()
        self.assertTrue(acquired)
        
        pickled = pickle.dumps(resource)
        restored = pickle.loads(pickled)
        
        self.assertEqual(restored.name, "res2")
        self.assertIsNot(restored.lock, resource.lock)
        
        acquired_restored = restored.acquire()
        self.assertTrue(acquired_restored)
        
        resource.release()
        restored.release()
    
    def test_lock_is_new_object_after_restore(self):
        """복원된 객체의 락은 원본과 다른 새 객체다."""
        resource = ResourceWithLockFixed("res3")
        
        acquired_original = resource.acquire()
        self.assertTrue(acquired_original)
        
        pickled = pickle.dumps(resource)
        restored = pickle.loads(pickled)
        
        acquired_restored = restored.acquire()
        self.assertTrue(acquired_restored)
        
        self.assertIsNot(resource.lock, restored.lock)
        
        resource.release()
        restored.release()


class TestRestrictedUnpickler(unittest.TestCase):
    """RestrictedUnpickler와 find_class 허용 목록을 확인한다."""
    
    def test_allowed_class_loads_successfully(self):
        """허용 목록에 있는 클래스는 safe_loads로 복원할 수 있다."""
        user = UserVersioned("Frank", "frank@example.com")
        pickled = pickle.dumps(user)
        
        module_name = UserVersioned.__module__
        allowed = {
            (module_name, 'UserVersioned'),
        }
        
        restored = safe_loads(pickled, allowed)
        
        self.assertEqual(restored.full_name, "Frank")
        self.assertEqual(restored.email, "frank@example.com")
    
    def test_disallowed_class_raises_unpickling_error(self):
        """허용 목록에 없는 클래스는 UnpicklingError를 발생시킨다."""
        user = UserVersioned("Grace", "grace@example.com")
        pickled = pickle.dumps(user)
        
        module_name = UserVersioned.__module__
        allowed = {
            (module_name, 'NonExistentClass'),
        }
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
        self.assertIn("UserVersioned", str(cm.exception))
    
    def test_different_module_same_class_name_rejected(self):
        """같은 클래스 이름이라도 다른 모듈이면 거부된다."""
        user = UserVersioned("Henry", "henry@example.com")
        pickled = pickle.dumps(user)
        
        allowed = {
            ('other_module', 'UserVersioned'),
        }
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
    
    def test_builtin_function_rejected(self):
        """builtins.print 같은 전역 함수는 허용 목록 없이 거부된다."""
        pickled = pickle.dumps(print)
        
        allowed = set()
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
        self.assertIn("builtins", str(cm.exception))
    
    def test_eval_function_rejected(self):
        """builtins.eval은 허용 목록 없이 거부된다."""
        pickled = pickle.dumps(eval)
        
        allowed = set()
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
        self.assertIn("builtins", str(cm.exception))
    
    def test_allowed_class_with_forbidden_attribute(self):
        """허용된 클래스라도 속성에 허용되지 않은 전역이 있으면 거부된다."""
        obj = ObjectWithForbiddenGlobal("test", eval)
        pickled = pickle.dumps(obj)
        
        module_name = ObjectWithForbiddenGlobal.__module__
        allowed = {
            (module_name, 'ObjectWithForbiddenGlobal'),
        }
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
        self.assertIn("builtins", str(cm.exception))


class TestCopyUsesGetstate(unittest.TestCase):
    """copy.deepcopy/copy.copy도 __getstate__/__setstate__를 거치는지 확인한다."""
    
    def test_deepcopy_creates_new_lock(self):
        """deepcopy는 __getstate__/__setstate__를 거쳐 새 락을 생성한다."""
        resource = ResourceWithLockFixed("res4")
        
        acquired = resource.acquire()
        self.assertTrue(acquired)
        
        deep_copied = copy.deepcopy(resource)
        
        self.assertEqual(deep_copied.name, "res4")
        self.assertIsNot(resource.lock, deep_copied.lock)
        
        acquired_deep = deep_copied.acquire()
        self.assertTrue(acquired_deep)
        
        resource.release()
        deep_copied.release()
    
    def test_copy_creates_new_lock(self):
        """copy는 __getstate__/__setstate__를 거쳐 새 락을 생성한다."""
        resource = ResourceWithLockFixed("res5")
        
        acquired = resource.acquire()
        self.assertTrue(acquired)
        
        shallow_copied = copy.copy(resource)
        
        self.assertEqual(shallow_copied.name, "res5")
        self.assertIsNot(resource.lock, shallow_copied.lock)
        
        acquired_shallow = shallow_copied.acquire()
        self.assertTrue(acquired_shallow)
        
        resource.release()
        shallow_copied.release()


class TestProtocolVersions(unittest.TestCase):
    """모든 pickle 프로토콜 버전에서 마이그레이션이 동작하는지 확인한다."""
    
    def test_all_protocols_support_migration(self):
        """프로토콜 0부터 HIGHEST_PROTOCOL까지 모두 상태 마이그레이션을 지원한다."""
        module_name = 'pickle_state_migration'
        
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                user_v1 = UserV1Legacy("Ian")
                pickled = pickle.dumps(user_v1, protocol=protocol)
                
                original_class = replace_class_in_module(module_name, 'UserV1Legacy', UserVersioned)
                
                try:
                    restored = pickle.loads(pickled)
                    
                    self.assertEqual(restored.full_name, "Ian")
                    self.assertEqual(restored.email, "")
                    self.assertEqual(restored._state_version, 3)
                finally:
                    replace_class_in_module(module_name, 'UserV1Legacy', original_class)


class TestMutationDetection(unittest.TestCase):
    """변이 검사: 마이그레이션 로직을 제거하거나 우회하면 테스트가 실패해야 한다."""
    
    def test_module_replacement_is_required(self):
        """모듈 속성 교체 없이는 클래스 진화가 pickle에 반영되지 않는다."""
        user_v1 = UserV1("Jack")
        pickled = pickle.dumps(user_v1)
        
        restored = pickle.loads(pickled)
        
        self.assertIs(type(restored), UserV1)
        self.assertNotIn('email', vars(restored))
    
    def test_migration_logic_is_executed(self):
        """마이그레이션 로직이 실제로 실행되는지 확인한다."""
        state_v1 = {
            'name': 'Jane'
        }
        
        user_with_migration = UserVersioned("dummy", "dummy@example.com")
        user_with_migration.__setstate__(state_v1)
        
        self.assertEqual(user_with_migration.full_name, "Jane")
        self.assertEqual(user_with_migration.email, "")
        self.assertEqual(user_with_migration._state_version, 3)
        
        state_v2 = {
            '_state_version': 2,
            'name': 'Kate',
            'email': 'kate@example.com'
        }
        
        user_v2_migration = UserVersioned("dummy2", "dummy2@example.com")
        user_v2_migration.__setstate__(state_v2)
        
        self.assertEqual(user_v2_migration.full_name, "Kate")
        self.assertEqual(user_v2_migration.email, "kate@example.com")
        self.assertEqual(user_v2_migration._state_version, 3)


if __name__ == "__main__":
    unittest.main()
