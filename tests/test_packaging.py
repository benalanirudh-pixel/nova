"""
Manifest consistency test: pyproject.toml must mirror requirements.txt.

Offline and dependency-free (stdlib `tomllib` only). Keeps the two dependency
manifests in lock-step so tooling that reads pyproject.toml sees exactly the
venv's pinned set.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8-sig")
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _pyproject():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


class TestPackaging(unittest.TestCase):

    def test_pyproject_metadata_present(self):
        project = _pyproject()["project"]
        self.assertEqual(project["name"], "nova")
        self.assertTrue(project.get("description"))
        self.assertIn("requires-python", project)

    def test_dependencies_match_requirements_exactly(self):
        deps = set(_pyproject()["project"]["dependencies"])
        self.assertEqual(deps, _requirements())

    def test_requires_python_covers_runtime(self):
        rp = _pyproject()["project"]["requires-python"]
        # Nova's venv is Python 3.14; the floor must not exclude it.
        self.assertIn(">=", rp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
