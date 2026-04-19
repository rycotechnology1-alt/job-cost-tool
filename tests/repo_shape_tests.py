from pathlib import Path
import unittest


class RepoShapeTests(unittest.TestCase):
    def test_repository_no_longer_contains_desktop_surface(self) -> None:
        self.assertFalse(Path("app").exists())
        self.assertFalse(Path("services/settings_workflow_service.py").exists())
        self.assertNotIn(
            "PySide6",
            {line.strip() for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()},
        )
