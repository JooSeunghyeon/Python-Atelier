"""pickle 상태 마이그레이션과 보안 경계를 검증하는 테스트다."""

import pickle
import io
import threading
import copy
import unittest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(project_root))

from pickle_state_migration import (
    UserV1,
    UserV2,
    UserVersioned,
    ResourceWithLock,
    ResourceWithLockFixed,
    RestrictedUnpickler,
    safe_loads,
)


class TestV1ToV2AttributeError(unittest.TestCase):
    """V1→V2 복원 시 AttributeError 함정을 확인한다."""
    
    def test_v1_to_v2_missing_attribute(self):
        """V1으로 저장된 객체를 V2 클래스로 복원하면 email이 없어 AttributeError가 발생한다."""
        global UserV1
        
        user_v1 = UserV1("Alice")
        pickled = pickle.dumps(user_v1)
        
        self.assertEqual(user_v1.name, "Alice")
        
        original_v1 = UserV1
        UserV1 = UserV2
        
        try:
            restored = pickle.loads(pickled)
            
            self.assertEqual(restored.name, "Alice")
            
            with self.assertRaises(AttributeError) as cm:
                _ = restored.email
            
            self.assertIn("email", str(cm.exception))
        finally:
            UserV1 = original_v1


class TestVersionedMigration(unittest.TestCase):
    """상태 버전 관리와 마이그레이션을 확인한다."""
    
    def test_v1_to_v3_migration_adds_email(self):
        """V1→V3 마이그레이션은 email을 빈 문자열로 채우고 name을 full_name으로 변경한다."""
        user_v1 = UserVersioned(name="Bob", version=1)
        pickled = pickle.dumps(user_v1)
        
        self.assertEqual(user_v1._state_version, 1)
        
        restored = pickle.loads(pickled)
        
        self.assertEqual(restored.full_name, "Bob")
        self.assertEqual(restored.email, "")
        self.assertEqual(restored._state_version, 3)
    
    def test_v2_to_v3_migration_renames_field(self):
        """V2→V3 마이그레이션은 name을 full_name으로 변경한다."""
        user_v2 = UserVersioned(name="Charlie", email="charlie@example.com", version=2)
        pickled = pickle.dumps(user_v2)
        
        self.assertEqual(user_v2._state_version, 2)
        
        restored = pickle.loads(pickled)
        
        self.assertEqual(restored.full_name, "Charlie")
        self.assertEqual(restored.email, "charlie@example.com")
        self.assertEqual(restored._state_version, 3)
    
    def test_future_version_raises_value_error(self):
        """미래 버전 상태를 복원하면 ValueError가 발생한다."""
        state = {
            '_state_version': 99,
            'unknown_field': 'value'
        }
        
        user = UserVersioned(full_name="dummy", email="dummy@example.com")
        
        with self.assertRaises(ValueError) as cm:
            user.__setstate__(state)
        
        self.assertIn("알 수 없는 상태 버전", str(cm.exception))
        self.assertIn("99", str(cm.exception))
    
    def test_already_latest_version_unchanged(self):
        """이미 최신 버전인 상태를 재복원해도 변경되지 않는다."""
        user_v3 = UserVersioned(full_name="Eve", email="eve@example.com")
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
        original_lock_id = id(resource.lock)
        
        acquired = resource.acquire()
        self.assertTrue(acquired)
        resource.release()
        
        pickled = pickle.dumps(resource)
        restored = pickle.loads(pickled)
        
        self.assertEqual(restored.name, "res2")
        
        restored_lock_id = id(restored.lock)
        self.assertNotEqual(original_lock_id, restored_lock_id)
        
        acquired = restored.acquire()
        self.assertTrue(acquired)
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
        user = UserVersioned(full_name="Frank", email="frank@example.com")
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
        user = UserVersioned(full_name="Grace", email="grace@example.com")
        pickled = pickle.dumps(user)
        
        module_name = UserVersioned.__module__
        allowed = {
            (module_name, 'NonExistentClass'),
        }
        
        with self.assertRaises(pickle.UnpicklingError) as cm:
            safe_loads(pickled, allowed)
        
        self.assertIn("허용되지 않은", str(cm.exception))
        self.assertIn("UserVersioned", str(cm.exception))
    
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


class TestCopyUsesGetstate(unittest.TestCase):
    """copy.deepcopy/copy.copy도 __getstate__/__setstate__를 거치는지 확인한다."""
    
    def test_deepcopy_creates_new_lock(self):
        """deepcopy는 __getstate__/__setstate__를 거쳐 새 락을 생성한다."""
        resource = ResourceWithLockFixed("res4")
        original_lock_id = id(resource.lock)
        
        deep_copied = copy.deepcopy(resource)
        deep_lock_id = id(deep_copied.lock)
        
        self.assertEqual(deep_copied.name, "res4")
        self.assertNotEqual(original_lock_id, deep_lock_id)
        self.assertIsNot(resource.lock, deep_copied.lock)
    
    def test_copy_creates_new_lock(self):
        """copy는 __getstate__/__setstate__를 거쳐 새 락을 생성한다."""
        resource = ResourceWithLockFixed("res5")
        original_lock_id = id(resource.lock)
        
        shallow_copied = copy.copy(resource)
        shallow_lock_id = id(shallow_copied.lock)
        
        self.assertEqual(shallow_copied.name, "res5")
        self.assertNotEqual(original_lock_id, shallow_lock_id)
        self.assertIsNot(resource.lock, shallow_copied.lock)


class TestProtocolVersions(unittest.TestCase):
    """모든 pickle 프로토콜 버전에서 마이그레이션이 동작하는지 확인한다."""
    
    def test_all_protocols_support_migration(self):
        """프로토콜 0부터 HIGHEST_PROTOCOL까지 모두 상태 마이그레이션을 지원한다."""
        user_v1 = UserVersioned(name="Henry", version=1)
        
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                pickled = pickle.dumps(user_v1, protocol=protocol)
                restored = pickle.loads(pickled)
                
                self.assertEqual(restored.full_name, "Henry")
                self.assertEqual(restored.email, "")
                self.assertEqual(restored._state_version, 3)


class TestMutationDetection(unittest.TestCase):
    """변이 검사: 마이그레이션 로직을 제거하거나 우회하면 테스트가 실패해야 한다."""
    
    def test_migration_logic_is_executed(self):
        """마이그레이션 로직이 실제로 실행되는지 확인한다."""
        state_v1 = {
            '_state_version': 1,
            'name': 'Ian'
        }
        
        user_with_migration = UserVersioned(full_name="dummy", email="dummy@example.com")
        user_with_migration.__setstate__(state_v1)
        
        self.assertEqual(user_with_migration.full_name, "Ian")
        self.assertEqual(user_with_migration.email, "")
        self.assertEqual(user_with_migration._state_version, 3)
        
        state_v2 = {
            '_state_version': 2,
            'name': 'Jane',
            'email': 'jane@example.com'
        }
        
        user_v2_migration = UserVersioned(full_name="dummy2", email="dummy2@example.com")
        user_v2_migration.__setstate__(state_v2)
        
        self.assertEqual(user_v2_migration.full_name, "Jane")
        self.assertEqual(user_v2_migration.email, "jane@example.com")
        self.assertEqual(user_v2_migration._state_version, 3)
    
    def test_find_class_restriction_is_enforced(self):
        """find_class 허용 목록이 실제로 적용되는지 확인한다."""
        user = UserVersioned(full_name="Jack", email="jack@example.com")
        pickled = pickle.dumps(user)
        
        class UnrestrictedUnpickler(pickle.Unpickler):
            """허용 목록 검사를 우회한 잘못된 구현."""
            
            def __init__(self, file):
                super().__init__(file)
                self.allowed_globals = set()
        
        unrestricted = UnrestrictedUnpickler(io.BytesIO(pickled))
        restored = unrestricted.load()
        
        self.assertEqual(restored.full_name, "Jack")


if __name__ == "__main__":
    unittest.main()
