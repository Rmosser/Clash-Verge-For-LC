#!/usr/bin/env python3
"""Regression tests for the repository-owned documentation checker."""

from __future__ import annotations

import importlib.util
import json
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

    def test_regular_rules_file_loads(self) -> None:
        rules_path = self.root / "docs/doc-sync-rules.json"
        rules_path.write_text(json.dumps(self.rules), encoding="utf-8")
        self.assertEqual(checker.load_rules(self.root), self.rules)

    def test_symlinked_rules_file_fails_closed(self) -> None:
        target = self.root / "rules-target.json"
        target.write_text(json.dumps(self.rules), encoding="utf-8")
        (self.root / "docs/doc-sync-rules.json").symlink_to(
            "../rules-target.json"
        )
        with self.assertRaisesRegex(checker.DocsError, "cannot safely read"):
            checker.load_rules(self.root)

    def test_duplicate_rules_key_fails_closed(self) -> None:
        raw = json.dumps(self.rules).replace(
            '"required_paths":',
            '"required_paths": [], "required_paths":',
            1,
        )
        (self.root / "docs/doc-sync-rules.json").write_text(
            raw,
            encoding="utf-8",
        )
        with self.assertRaisesRegex(checker.DocsError, "duplicate JSON key"):
            checker.load_rules(self.root)

    def test_repository_inventory_includes_current_runtime_contract(self) -> None:
        rules = checker.load_rules(REPOSITORY)
        self.assertIn("docs/CURRENT_RUNTIME.md", rules["required_paths"])
        index_entry = next(
            entry
            for entry in rules["entrypoint_links"]
            if entry["source"] == "docs/index.md"
        )
        self.assertIn("CURRENT_RUNTIME.md", index_entry["targets"])
        checker.validate(rules, REPOSITORY)

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
            "\\[documentation](docs/index.md)\n",
            '[<span title="](docs/index.md)">x</span>\n',
            "```\n[documentation](docs/index.md)\n```\n",
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(checker.DocsError, "does not link"):
                    checker.validate(self.rules, self.root)

    def test_commonmark_escape_parity_and_inline_html_links_pass(self) -> None:
        source = self.root / "AGENTS.md"
        for text in (
            "\\\\[documentation](docs/index.md)\n",
            "\\![documentation](docs/index.md)\n",
            "<code>[documentation](docs/index.md)</code>\n",
            "[documentation \\] label](docs/index.md)\n",
            "[<span>documentation</span>](docs/index.md)\n",
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                checker.validate(self.rules, self.root)

    def test_full_collapsed_and_shortcut_references_pass(self) -> None:
        source = self.root / "AGENTS.md"
        for text in (
            "[documentation][index]\n[index]: docs/index.md\n",
            "[index][]\n[index]: docs/index.md\n",
            "[index]\n[index]: docs/index.md\n",
            "[documentation \\] label]\n"
            "[documentation \\] label]: docs/index.md\n",
            "\\\\[documentation][index]\n[index]: docs/index.md\n",
            "\\![documentation][index]\n[index]: docs/index.md\n",
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                checker.validate(self.rules, self.root)

    def test_escaped_full_reference_and_reference_image_do_not_link(self) -> None:
        source = self.root / "AGENTS.md"
        for text in (
            "\\[documentation][index]\n[index]: docs/index.md\n",
            "![documentation][index]\n[index]: docs/index.md\n",
            "[hidden\\]\n[hidden\\]: docs/index.md\n",
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(checker.DocsError, "does not link"):
                    checker.validate(self.rules, self.root)

    def test_every_extracted_local_target_must_exist(self) -> None:
        source = self.root / "AGENTS.md"
        for dangling in (
            "[missing](docs/missing.md)\n",
            "[missing][dangling]\n[dangling]: docs/missing.md\n",
            "[missing [nested]](docs/missing.md)\n",
        ):
            with self.subTest(dangling=dangling):
                source.write_text(
                    "[documentation](docs/index.md)\n" + dangling,
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(checker.DocsError, "is missing"):
                    checker.validate(self.rules, self.root)

    def test_nested_inline_link_safe_controls(self) -> None:
        source = self.root / "AGENTS.md"
        for text in (
            "[documentation [nested]](docs/index.md)\n",
            "[documentation \\[literal\\]](docs/index.md)\n",
            (
                "[documentation](docs/index.md)\n"
                "![nested [image]](docs/missing.md)\n"
            ),
        ):
            with self.subTest(text=text):
                source.write_text(text, encoding="utf-8")
                checker.validate(self.rules, self.root)

    def test_nested_link_does_not_turn_its_outer_label_into_a_link(self) -> None:
        source = self.root / "AGENTS.md"
        source.write_text(
            "[outer [documentation](docs/index.md)](docs/missing.md)\n",
            encoding="utf-8",
        )
        checker.validate(self.rules, self.root)

    def test_nested_image_preserves_its_outer_link(self) -> None:
        source = self.root / "AGENTS.md"
        source.write_text(
            "[documentation ![icon](docs/missing.png)](docs/index.md)\n",
            encoding="utf-8",
        )
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
