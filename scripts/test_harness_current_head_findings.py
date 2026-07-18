#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_review():
    path = ROOT / "scripts/check_codex_review.py"
    spec = importlib.util.spec_from_file_location("clash_verge_check_codex_review", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CurrentHeadFindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.review = load_review()

    def test_deleted_ordinary_maintainer_comment_is_not_review_evidence(self) -> None:
        head = "a" * 40
        contract = {"codex_review": {"accepted_authors": ["chatgpt-codex-connector"]}}
        ordinary = {
            "action": "deleted",
            "comment": {
                "user": {"login": "Rmosser", "type": "User"},
                "author_association": "OWNER",
                "body": "ordinary project discussion",
                "created_at": "2026-07-19T00:00:00Z",
            },
        }
        trigger = json.loads(json.dumps(ordinary))
        trigger["comment"]["body"] = f"@codex review\nHead SHA: {head}"

        self.assertFalse(
            self.review.evidence_event_requires_pending(
                contract, head, event_name="issue_comment", event_payload=ordinary
            )
        )
        self.assertTrue(
            self.review.evidence_event_requires_pending(
                contract, head, event_name="issue_comment", event_payload=trigger
            )
        )


if __name__ == "__main__":
    unittest.main()
