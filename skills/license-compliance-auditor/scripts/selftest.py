#!/usr/bin/env python3
"""Run all license-compliance-auditor script tests (stdlib unittest)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.normpath(os.path.join(HERE, "..", "tests"))


def main():
    sys.path.insert(0, HERE)
    sys.path.insert(0, TESTS)
    suite = unittest.defaultTestLoader.discover(TESTS, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
