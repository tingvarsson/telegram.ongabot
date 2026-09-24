import inspect
import io
import logging
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


FAKE_TOKEN = "123456789:" + "A" * 35


class TokenRedactionTest(unittest.TestCase):
    def setUp(self):
        # A private logger tree: the handler sits on the parent, records come from a child,
        # the same shape as python-telegram-bot's loggers propagating to the root handler.
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        self.handler.addFilter(log.TokenRedactingFilter())
        self.parent = logging.getLogger("redaction-test")
        self.parent.addHandler(self.handler)
        self.parent.setLevel(logging.DEBUG)
        self.parent.propagate = False
        self.child = logging.getLogger("redaction-test.telegram.ext.ExtBot")

    def tearDown(self):
        self.parent.removeHandler(self.handler)

    def test_token_in_a_formatted_argument_is_masked(self):
        self.child.debug("Set Bot API URL: %s", f"https://api.telegram.org/bot{FAKE_TOKEN}")
        output = self.stream.getvalue()
        self.assertNotIn(FAKE_TOKEN, output)
        self.assertIn(f"https://api.telegram.org/bot{log.TOKEN_PLACEHOLDER}", output)

    def test_token_in_a_traceback_is_masked(self):
        try:
            raise RuntimeError(f"404 for url 'https://api.telegram.org/bot{FAKE_TOKEN}/getMe'")
        except RuntimeError:
            self.child.exception("request failed")
        output = self.stream.getvalue()
        self.assertNotIn(FAKE_TOKEN, output)
        self.assertIn("RuntimeError", output)

    def test_messages_without_a_token_are_left_alone(self):
        self.child.info("chat_id=%s joined at %s", -1001345767319, "18:30:00")
        self.assertEqual(
            self.stream.getvalue(), "redaction-test.telegram.ext.ExtBot chat_id=-1001345767319 joined at 18:30:00\n"
        )

    def test_install_adds_the_filter_to_every_root_handler(self):
        root = logging.getLogger()
        handler = logging.NullHandler()
        root.addHandler(handler)
        try:
            log.redact_tokens_in_logs()
            self.assertTrue(any(isinstance(f, log.TokenRedactingFilter) for f in handler.filters))
        finally:
            root.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
