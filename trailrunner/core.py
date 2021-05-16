# Copyright 2021 John Reese
# Licensed under the MIT license

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Executor
from pathlib import Path
from typing import Iterable, Iterator, Callable, TypeVar, List, Dict

from pathspec import PathSpec, RegexPattern
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

T = TypeVar("T")


INCLUDE_PATTERN = r".+\.pyi?$"
ROOT_MARKERS = [Path("pyproject.toml"), Path(".git"), Path(".hg")]


def default_executor() -> ProcessPoolExecutor:
    """
    Default executor for trailrunner.

    Uses the active multiprocessing context (see :func:`set_context`) to run tasks
    on a pool of child processes.
    """
    import trailrunner

    return ProcessPoolExecutor(mp_context=trailrunner.context)


def thread_executor() -> ThreadPoolExecutor:
    """
    Thread pool executor, for testing trailrunner without multiprocessing.
    """
    return ThreadPoolExecutor()


class TrailRunner:
    def __init__(
        self, executor_factory: Callable[[], Executor] = default_executor
    ) -> None:
        self.executor_factory = executor_factory

    @staticmethod
    def project_root(path: Path) -> Path:
        """
        Find the project root, looking upward from the given path.

        Looks through all parent paths until either the root is reached, or a directory
        is found that contains any of :attr:`trailrunner.core.ROOT_MARKERS`.
        """
        real_path = path.resolve()

        parents = list(real_path.parents)
        if real_path.is_dir():
            parents.insert(0, real_path)

        for parent in parents:
            if any((parent / marker).exists() for marker in ROOT_MARKERS):
                return parent

        return parent

    @staticmethod
    def gitignore(path: Path) -> PathSpec:
        """
        Generate a `PathSpec` object for a .gitignore file in the given directory.

        If none is found, an empty PathSpec is returned. If the path is not a directory,
        `ValueError` is raised.
        """
        if not path.is_dir():
            raise ValueError(f"path {path} not a directory")

        gi_path = path / ".gitignore"

        if gi_path.is_file():
            lines = gi_path.read_text().splitlines()
            return PathSpec.from_lines(GitWildMatchPattern, lines)

        return PathSpec([])

    def walk(self, path: Path) -> Iterator[Path]:
        """
        Generate all significant file paths, starting from the given path.

        Finds the project root and any associated gitignore. Filters any paths that match
        a gitignore pattern. Recurses into subdirectories, and otherwise only includes
        files that match the :attr:`trailrunner.core.INCLUDE_PATTERN` regex.

        Returns a generator that yields each significant file as the tree is walked.
        """
        root = self.project_root(path)
        ignore = self.gitignore(root)
        include = PathSpec([RegexPattern(INCLUDE_PATTERN)])

        def gen(children: Iterable[Path]) -> Iterator[Path]:
            for child in children:

                if ignore.match_file(child):
                    continue

                if child.is_file() and include.match_file(child):
                    yield child

                elif child.is_dir():
                    yield from gen(child.iterdir())

        return gen([path])

    def run(self, paths: Iterable[Path], func: Callable[[Path], T]) -> Dict[Path, T]:
        """
        Run a given function once for each path, using a process pool for concurrency.

        For each path given, `func` will be called with `path` as the only argument.
        To pass any other positional or keyword arguments, use `functools.partial`.

        Results from each path will be returned as a dictionary mapping path to result.

        Uses a process pool with "spawned" processes that share no state with the parent
        process, to enforce consistent behavior on Linux, macOS, and Windows, where forked
        processes are not possible.
        """
        paths = list(paths)

        with self.executor_factory() as exe:
            results = list(exe.map(func, paths))

        return dict(zip(paths, results))

    def walk_and_run(
        self, paths: Iterable[Path], func: Callable[[Path], T]
    ) -> Dict[Path, T]:
        """
        Walks each path given, and runs the given function on all gathered paths.

        See :func:`walk` for details on how paths are gathered, and :func:`run` for how
        functions are run for each gathered path.
        """
        all_paths: List[Path] = []
        for path in paths:
            all_paths.extend(self.walk(path))

        return self.run(all_paths, func)


DEFAULT_RUNNER: TrailRunner = TrailRunner()


def project_root(path: Path) -> Path:
    return DEFAULT_RUNNER.project_root(path)


def gitignore(path: Path) -> PathSpec:
    return DEFAULT_RUNNER.gitignore(path)


def walk(path: Path) -> Iterator[Path]:
    return DEFAULT_RUNNER.walk(path)


def run(paths: Iterable[Path], func: Callable[[Path], T]) -> Dict[Path, T]:
    return DEFAULT_RUNNER.run(paths, func)


def walk_and_run(paths: Iterable[Path], func: Callable[[Path], T]) -> Dict[Path, T]:
    return DEFAULT_RUNNER.walk_and_run(paths, func)
