import re
from pathlib import Path
import unittest


class RepoShapeTests(unittest.TestCase):
    def test_repository_no_longer_contains_desktop_surface(self) -> None:
        self.assertFalse(Path("app").exists())
        self.assertFalse(Path("services/settings_workflow_service.py").exists())
        self._assert_requirements_do_not_reference_pyside6()
        self._assert_runtime_python_sources_do_not_reference_desktop_surface()

    def test_active_guidance_no_longer_describes_desktop_fallback(self) -> None:
        disallowed_phrases = (
            "desktop fallback",
            "desktop sync",
            "desktop reference",
            "correctness reference",
            "reference implementation",
            "pyside6",
        )
        for path in [Path("README.md"), Path("AGENTS.md")]:
            text = path.read_text(encoding="utf-8").casefold()
            for phrase in disallowed_phrases:
                self.assertNotIn(phrase, text)

    def _assert_requirements_do_not_reference_pyside6(self) -> None:
        requirements_text = Path("requirements.txt").read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(
                r"(?im)^\s*pyside6(?:\[[^\]]+\])?(?:\s*[<>=!~].*)?(?:\s+#.*)?$",
                requirements_text,
            ),
            "requirements.txt should not reference PySide6 in any casing or version form.",
        )

    def _assert_runtime_python_sources_do_not_reference_desktop_surface(self) -> None:
        runtime_roots = [
            Path("api"),
            Path("core"),
            Path("infrastructure"),
            Path("services"),
            Path("web"),
        ]
        disallowed_markers = (
            "from app.",
            "import app.",
            "from services.settings_workflow_service import",
            "import services.settings_workflow_service",
            "pyside6",
        )

        for root in runtime_roots:
            if not root.exists():
                continue
            for file_path in root.rglob("*.py"):
                file_text = file_path.read_text(encoding="utf-8").casefold()
                for marker in disallowed_markers:
                    self.assertNotIn(
                        marker,
                        file_text,
                        f"{file_path} should not reference desktop-only surface '{marker}'.",
                    )
