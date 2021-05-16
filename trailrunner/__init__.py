# Copyright 2021 John Reese
# Licensed under the MIT license

"""
Run things on paths
"""

import multiprocessing

context: multiprocessing.context.BaseContext = multiprocessing.get_context("spawn")

__author__ = "John Reese"
from .__version__ import __version__
from .core import (
    run,
    walk,
    walk_and_run,
    default_executor,
    thread_executor,
    TrailRunner,
)
