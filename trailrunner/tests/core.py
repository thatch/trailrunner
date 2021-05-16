# Copyright 2021 John Reese
# Licensed under the MIT license

import multiprocessing
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from unittest import TestCase
from unittest.mock import Mock

from pathspec import PathSpec
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

import trailrunner
from trailrunner import core


@contextmanager
def cd(path: Path) -> Iterator[None]:
    try:
        cwd = Path.cwd()
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


class CoreTest(TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.trailrunner = trailrunner.TrailRunner(core.thread_executor)
        self.temp_dir = TemporaryDirectory()
        self.td = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_set_context(self) -> None:
        orig_context = trailrunner.context

        new_context = multiprocessing.get_context("fork")
        core.set_context(new_context)
        self.assertEqual(trailrunner.context, new_context)

        core.set_context(orig_context)
        self.assertEqual(trailrunner.context, orig_context)

    def test_set_executor(self) -> None:
        mock_factory = Mock(return_value=core.thread_executor())

        core.set_executor(mock_factory)
        self.assertEqual(mock_factory, core.EXECUTOR)

        def foo(path: Path) -> Path:
            return path

        expected = {Path(): Path(), Path("foo"): Path("foo")}
        results = core.run([Path(), Path("foo")], foo)

        mock_factory.assert_called_once_with()
        self.assertEqual(expected, results)

    def test_default_executor(self) -> None:
        def foo(path: Path) -> Path:
            return path / "foo"

        expected = {
            Path(): Path("foo"),
            Path("/"): Path("/foo"),
        }
        result = core.run([Path(), Path("/")], foo)
        self.assertEqual(expected, result)

        core.set_executor(core.default_executor)
        self.assertEqual(core.default_executor, core.EXECUTOR)
        with self.assertRaisesRegex(AttributeError, "Can't pickle local object"):
            core.run([Path(), Path("/")], foo)

    def test_project_root_empty(self) -> None:
        result = core.project_root(self.td)
        self.assertTrue(self.td.relative_to(result))

    def test_project_root_basic(self) -> None:
        (self.td / ".git").mkdir()
        (self.td / "foo.py").write_text("\n")
        (self.td / "frob").mkdir()
        (self.td / "frob" / "berry.py").write_text("\n")

        with self.subTest("root"):
            result = self.trailrunner.project_root(self.td)
            self.assertEqual(self.td, result)

        with self.subTest("root file"):
            result = self.trailrunner.project_root(self.td / "foo.py")
            self.assertEqual(self.td, result)

        with self.subTest("subdir"):
            result = self.trailrunner.project_root(self.td / "frob")
            self.assertEqual(self.td, result)

        with self.subTest("subdir file"):
            result = self.trailrunner.project_root(self.td / "frob/berry.py")
            self.assertEqual(self.td, result)

        with self.subTest("local root"):
            with cd(self.td):
                result = self.trailrunner.project_root(Path("frob"))
                self.assertEqual(self.td, result)

        with self.subTest("local subdir"):
            with cd(self.td / "frob"):
                result = self.trailrunner.project_root(Path("berry.py"))
                self.assertEqual(self.td, result)

    def test_project_root_multilevel(self) -> None:
        (self.td / ".hg").mkdir()
        inner = self.td / "foo" / "bar"
        inner.mkdir(parents=True)
        (inner / "pyproject.toml").write_text("\n")
        (inner / "fuzz").mkdir()
        (inner / "fuzz" / "ball.py").write_text("\n")

        with self.subTest("root"):
            result = self.trailrunner.project_root(self.td)
            self.assertEqual(self.td, result)

        with self.subTest("subdir"):
            result = self.trailrunner.project_root(self.td / "foo")
            self.assertEqual(self.td, result)

        with self.subTest("inner root"):
            result = self.trailrunner.project_root(inner)
            self.assertEqual(inner, result)

        with self.subTest("inner file"):
            result = self.trailrunner.project_root(inner / "fuzz" / "ball.py")
            self.assertEqual(inner, result)

    def test_gitignore(self) -> None:
        with self.subTest("no .gitignore"):
            result = self.trailrunner.gitignore(self.td)
            self.assertIsInstance(result, PathSpec)
            self.assertListEqual([], result.patterns)

        (self.td / "foo.py").write_text("\n")

        with self.subTest("path is file"):
            with self.assertRaisesRegex(ValueError, "path .+ not a directory"):
                self.trailrunner.gitignore(self.td / "foo.py")

        (self.td / ".gitignore").write_text("foo/\n*.c\n")

        with self.subTest("valid file"):
            result = self.trailrunner.gitignore(self.td)
            self.assertIsInstance(result, PathSpec)
            self.assertTrue(result.patterns)
            for pattern in result.patterns:
                self.assertIsInstance(pattern, GitWildMatchPattern)

    def test_walk(self) -> None:
        (self.td / ".git").mkdir()
        inner = self.td / "inner" / "subproject"
        inner.mkdir(parents=True)
        (inner / "pyproject.toml").write_text("\n")
        (inner / "requirements.txt").write_text("\n")
        (inner / "fuzz").mkdir()
        (inner / "fuzz" / "ball.py").write_text("\n")
        (inner / "fuzz" / "data.txt").write_text("\n")
        (self.td / "foo" / "bar").mkdir(parents=True)
        (self.td / "foo" / "a.py").write_text("\n")
        (self.td / "foo" / "bar" / "b.py").write_text("\n")
        (self.td / "foo" / "bar" / "c.pyi").write_text("\n")
        (self.td / "foo" / "d.cpp").write_text("\n")
        (self.td / "vendor" / "useful").mkdir(parents=True)
        (self.td / "vendor" / "useful" / "old.py").write_text("\n")

        with self.subTest("absolute root no gitignore"):
            result = sorted(self.trailrunner.walk(self.td))
            expected = [
                self.td / "foo" / "a.py",
                self.td / "foo" / "bar" / "b.py",
                self.td / "foo" / "bar" / "c.pyi",
                self.td / "inner" / "subproject" / "fuzz" / "ball.py",
                self.td / "vendor" / "useful" / "old.py",
            ]
            self.assertListEqual(expected, result)

        with self.subTest("absolute subdir no gitignore"):
            result = sorted(self.trailrunner.walk(self.td / "foo"))
            expected = [
                self.td / "foo" / "a.py",
                self.td / "foo" / "bar" / "b.py",
                self.td / "foo" / "bar" / "c.pyi",
            ]
            self.assertListEqual(expected, result)

        with self.subTest("local root no gitignore"):
            with cd(self.td):
                result = sorted(self.trailrunner.walk(Path(".")))
                expected = [
                    Path("foo") / "a.py",
                    Path("foo") / "bar" / "b.py",
                    Path("foo") / "bar" / "c.pyi",
                    Path("inner") / "subproject" / "fuzz" / "ball.py",
                    Path("vendor") / "useful" / "old.py",
                ]
                self.assertListEqual(expected, result)

        with self.subTest("local subdir no gitignore"):
            with cd(self.td):
                result = sorted(self.trailrunner.walk(Path("foo")))
                expected = [
                    Path("foo") / "a.py",
                    Path("foo") / "bar" / "b.py",
                    Path("foo") / "bar" / "c.pyi",
                ]
                self.assertListEqual(expected, result)

        (self.td / ".gitignore").write_text("vendor/\n*.pyi")

        with self.subTest("absolute root with gitignore"):
            result = sorted(self.trailrunner.walk(self.td))
            expected = [
                self.td / "foo" / "a.py",
                self.td / "foo" / "bar" / "b.py",
                self.td / "inner" / "subproject" / "fuzz" / "ball.py",
            ]
            self.assertListEqual(expected, result)

        with self.subTest("absolute subdir with gitignore"):
            result = sorted(self.trailrunner.walk(self.td / "foo"))
            expected = [
                self.td / "foo" / "a.py",
                self.td / "foo" / "bar" / "b.py",
            ]
            self.assertListEqual(expected, result)

        with self.subTest("local root with gitignore"):
            with cd(self.td):
                result = sorted(self.trailrunner.walk(Path(".")))
                expected = [
                    Path("foo") / "a.py",
                    Path("foo") / "bar" / "b.py",
                    Path("inner") / "subproject" / "fuzz" / "ball.py",
                ]
                self.assertListEqual(expected, result)

        with self.subTest("local subdir with gitignore"):
            with cd(self.td):
                result = sorted(self.trailrunner.walk(Path("foo")))
                expected = [
                    Path("foo") / "a.py",
                    Path("foo") / "bar" / "b.py",
                ]
                self.assertListEqual(expected, result)

        with self.subTest("inner project snubs gitignore"):
            with cd(inner):
                result = sorted(self.trailrunner.walk(Path(".")))
                expected = [
                    Path("fuzz") / "ball.py",
                ]
                self.assertListEqual(expected, result)

    def test_run(self) -> None:
        def get_posix(path: Path) -> str:
            return path.as_posix()

        paths = [
            Path("foo") / "bar" / "baz.py",
            Path("bingo.py"),
            Path("/frob/glob.pyi"),
        ]
        expected = {p: p.as_posix() for p in paths}
        result = self.trailrunner.run(paths, get_posix)
        self.assertDictEqual(expected, result)

    def test_walk_then_run(self) -> None:
        (self.td / "pyproject.toml").write_text("\n")
        (self.td / "foo").mkdir()
        (self.td / "foo" / "foo.py").write_text("\n")
        (self.td / "foo" / "bar.py").write_text("\n")
        (self.td / "foo" / "car.py").write_text("\n")
        (self.td / "foo" / "car.pyi").write_text("\n")
        (self.td / "foo" / "data.dat").write_text("\n")
        (self.td / "vendor").mkdir()
        (self.td / "vendor" / "something.py").write_text("\n")
        (self.td / "vendor" / "everything.py").write_text("\n")

        def say_hello(path: Path) -> str:
            return f"hello {path}"

        with self.subTest("local root no gitignore"):
            with cd(self.td):
                result = sorted(
                    self.trailrunner.walk_and_run([Path(".")], say_hello).keys()
                )
                expected = [
                    Path("foo") / "bar.py",
                    Path("foo") / "car.py",
                    Path("foo") / "car.pyi",
                    Path("foo") / "foo.py",
                    Path("vendor") / "everything.py",
                    Path("vendor") / "something.py",
                ]
                self.assertListEqual(expected, result)

        with self.subTest("local subdir no gitignore"):
            with cd(self.td):
                result = sorted(
                    self.trailrunner.walk_and_run([Path("foo")], say_hello).keys()
                )
                expected = [
                    Path("foo") / "bar.py",
                    Path("foo") / "car.py",
                    Path("foo") / "car.pyi",
                    Path("foo") / "foo.py",
                ]
                self.assertListEqual(expected, result)

        (self.td / ".gitignore").write_text("**/foo.py\nvendor/\n")

        with self.subTest("local root with gitignore"):
            with cd(self.td):
                result = sorted(
                    self.trailrunner.walk_and_run([Path(".")], say_hello).keys()
                )
                expected = [
                    Path("foo") / "bar.py",
                    Path("foo") / "car.py",
                    Path("foo") / "car.pyi",
                ]
                self.assertListEqual(expected, result)

        with self.subTest("local subdir with gitignore"):
            with cd(self.td):
                result = sorted(
                    self.trailrunner.walk_and_run([Path("foo")], say_hello).keys()
                )
                expected = [
                    Path("foo") / "bar.py",
                    Path("foo") / "car.py",
                    Path("foo") / "car.pyi",
                ]
                self.assertListEqual(expected, result)
