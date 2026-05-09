import inspect
import unittest

from ongabot.utils import log


class LogSyncTest(unittest.TestCase):
    def test_sync_function_returns_result(self):
        @log.log
        def add(a, b):
            return a + b

        self.assertEqual(add(1, 2), 3)

    def test_sync_function_preserves_name(self):
        @log.log
        def my_func():
            pass

        self.assertEqual(my_func.__name__, "my_func")

    def test_sync_decorated_is_not_coroutine_function(self):
        @log.log
        def my_func():
            return 1

        self.assertFalse(inspect.iscoroutinefunction(my_func))


class LogMethodSyncTest(unittest.TestCase):
    def test_sync_method_returns_result(self):
        class MyClass:
            @log.method
            def add(self, a, b):
                return a + b

        self.assertEqual(MyClass().add(1, 2), 3)

    def test_sync_method_preserves_name(self):
        class MyClass:
            @log.method
            def my_method(self):
                pass

        self.assertEqual(MyClass.my_method.__name__, "my_method")

    def test_sync_method_decorated_is_not_coroutine_function(self):
        class MyClass:
            @log.method
            def my_method(self):
                return 1

        self.assertFalse(inspect.iscoroutinefunction(MyClass.my_method))


class LogAsyncTest(unittest.TestCase):
    def test_async_decorated_is_coroutine_function(self):
        @log.log
        async def my_func():
            return 42

        self.assertTrue(inspect.iscoroutinefunction(my_func))

    def test_async_function_preserves_name(self):
        @log.log
        async def my_func():
            pass

        self.assertEqual(my_func.__name__, "my_func")


class LogAsyncExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_function_executes_body(self):
        side_effects = []

        @log.log
        async def my_func():
            side_effects.append("ran")
            return 99

        result = await my_func()
        self.assertEqual(result, 99)
        self.assertEqual(side_effects, ["ran"])


class LogMethodAsyncTest(unittest.TestCase):
    def test_async_method_decorated_is_coroutine_function(self):
        class MyClass:
            @log.method
            async def my_method(self):
                return 42

        self.assertTrue(inspect.iscoroutinefunction(MyClass.my_method))

    def test_async_method_preserves_name(self):
        class MyClass:
            @log.method
            async def my_method(self):
                pass

        self.assertEqual(MyClass.my_method.__name__, "my_method")


class LogMethodAsyncExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_method_executes_body(self):
        side_effects = []

        class MyClass:
            @log.method
            async def my_method(self):
                side_effects.append("ran")
                return 99

        result = await MyClass().my_method()
        self.assertEqual(result, 99)
        self.assertEqual(side_effects, ["ran"])


if __name__ == "__main__":
    unittest.main()
