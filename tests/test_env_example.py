"""`.env.example` lists exactly the environment variables the bot reads.

It is the only place a deployer learns a setting exists: a variable read in code but missing
here (YOUTUBE_API_KEY once was) is a feature that silently never turns on, and one listed here
but no longer read is a knob that does nothing.
"""

import ast
import re
import unittest
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
SOURCE_ROOT = REPO_ROOT / "ongabot"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

_EXAMPLE_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _is_env_read(node: ast.AST) -> bool:
    """os.getenv(...) or os.environ.get(...)."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
        return False
    func = node.func
    if func.attr == "getenv":
        return isinstance(func.value, ast.Name) and func.value.id == "os"
    return (
        func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _module_env_reads(tree: ast.Module) -> Tuple[Set[str], List[str]]:
    """Variable names one module reads, and a description of every read it could not resolve.

    A name passed straight to os.getenv is read directly. One that arrives through a parameter
    of a helper (like _parse_window_time(env_var, ...)) is resolved from the string literals
    every call of that helper in the same module passes in that position.
    """
    names: Set[str] = set()
    unresolved: List[str] = []
    helpers: Dict[str, int] = {}  # helper function name -> index of its env-var-name parameter
    via_helper: Set[int] = set()  # id() of the env reads inside those helpers

    for func in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        params = [arg.arg for arg in func.args.args]
        for call in (node for node in ast.walk(func) if _is_env_read(node)):
            arg = call.args[0]
            if isinstance(arg, ast.Name) and arg.id in params:
                helpers[func.name] = params.index(arg.id)
                via_helper.add(id(call))

    for node in ast.walk(tree):
        if _is_env_read(node):
            name = _string(node.args[0])
            if name is not None:
                names.add(name)
            elif id(node) not in via_helper:
                unresolved.append(f"line {node.lineno}: {ast.unparse(node)}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in helpers:
            index = helpers[node.func.id]
            name = _string(node.args[index]) if len(node.args) > index else None
            if name is None:
                unresolved.append(f"line {node.lineno}: {ast.unparse(node)}")
            else:
                names.add(name)
    return names, unresolved


def env_vars_read_by_bot() -> Tuple[Set[str], List[str]]:
    """Every environment variable read anywhere under ongabot/, plus unresolvable reads."""
    names: Set[str] = set()
    unresolved: List[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        module_names, module_unresolved = _module_env_reads(ast.parse(path.read_text(encoding="utf-8")))
        names |= module_names
        unresolved += [f"{path.relative_to(REPO_ROOT)} {read}" for read in module_unresolved]
    return names, unresolved


def env_example_keys() -> Set[str]:
    return set(_EXAMPLE_KEY_RE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


class EnvExampleTest(unittest.TestCase):
    def setUp(self):
        self.read, self.unresolved = env_vars_read_by_bot()

    def test_every_env_read_names_its_variable(self):
        self.assertEqual(self.unresolved, [], "env var name not a string literal - this test can't see it")

    def test_every_variable_the_bot_reads_is_in_env_example(self):
        self.assertEqual(self.read - env_example_keys(), set())

    def test_every_variable_in_env_example_is_read_by_the_bot(self):
        self.assertEqual(env_example_keys() - self.read, set())

    def test_finds_reads_made_through_a_helper_parameter(self):
        self.assertTrue({"YOUTUBE_SHORTS_WINDOW_START", "YOUTUBE_SHORTS_WINDOW_END"} <= self.read)


class ModuleEnvReadsTest(unittest.TestCase):
    """The scanner on small sources, so a blind spot shows up as a failure here."""

    def _reads(self, source: str) -> Tuple[Set[str], List[str]]:
        return _module_env_reads(ast.parse(source))

    def test_direct_reads(self):
        source = 'import os\nA = os.getenv("A")\nB = os.environ.get("B", "x")\n'
        self.assertEqual(self._reads(source), ({"A", "B"}, []))

    def test_read_through_helper_parameter(self):
        source = 'import os\ndef get(name, default):\n    return os.getenv(name) or default\nX = get("X", 1)\n'
        self.assertEqual(self._reads(source), ({"X"}, []))

    def test_unresolvable_reads_are_reported(self):
        for source in (
            'import os\nNAME = "A"\nA = os.getenv(NAME)\n',
            "import os\ndef get(n):\n    return os.getenv(n)\nget(f())\n",
        ):
            with self.subTest(source=source):
                _, unresolved = self._reads(source)
                self.assertEqual(len(unresolved), 1)


if __name__ == "__main__":
    unittest.main()
