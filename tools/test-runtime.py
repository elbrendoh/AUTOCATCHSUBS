"""Synthetic regression tests; never opens a real Resolve project or consumes a key."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'AUTOCATCHSUBS-backend-source/jr'))
suite=unittest.defaultTestLoader.discover(str(ROOT/'tools/tests'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
