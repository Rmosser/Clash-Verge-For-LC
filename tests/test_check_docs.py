#!/usr/bin/env python3
"""Regression tests for the repository-owned documentation checker."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def load_checker():
    path = REPOSITORY / "scripts" / "check_docs.py"
    spec = importlib.util.spec_from_file_location("repo_check_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


class DocumentationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "AGENTS.md").write_text(
            "[documentation](docs/index.md)\n",
            encoding="utf-8",
        )
        (self.root / "docs/index.md").write_text("# Documentation\n", encoding="utf-8")
        self.rules = {
            "contract_version": "repo-harness-doc-sync-v1",
            "required_paths": ["AGENTS.md", "docs/index.md"],
            "audit_state_path": ".harness/baseline-receipt.json",
            "entrypoint_links": [
                {
                    "source": "AGENTS.md",
                    "targets": ["docs/index.md"],
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_contract_passes(self) -> None:
        checker.validate(self.rules, self.root)

    def test_missing_required_path_fails(self) -> None:
        self.rules["required_paths"].append("docs/missing.md")
        with self.assertRaisesRegex(checker.DocsError, "is missing"):
            checker.validate(self.rules, self.root)

    def test_missing_entrypoint_link_fails(self) -> None:
        self.rules["entrypoint_links"][0]["targets"].append("docs/missing.md")
        with self.assertRaisesRegex(checker.DocsError, "does not link"):
            checker.validate(self.rules, self.root)

    def test_non_navigable_markdown_does_not_satisfy_entrypoint_link(self) -> None:
        source = self.root / "AGENTS.md"
        for text in (
            "`[documentation](docs/index.md)`\n",
            "    [documentation](docs/index.md)\n",
            "![documentation](docs/index.md)\n",
            "```\n[documentation](docs/index.md)\n```\n",
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(checker.DocsError, "does not link"):
                    checker.validate(self.rules, self.root)

    def test_unterminated_fence_fails_closed(self) -> None:
        (self.root / "AGENTS.md").write_text(
            "[documentation](docs/index.md)\n```\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(checker.DocsError, "unterminated"):
            checker.validate(self.rules, self.root)


if __name__ == "__main__":
    unittest.main()
