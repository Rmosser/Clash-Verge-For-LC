# Harness governance

The repository uses `repo-harness-v3`.

When `platform_gate.state=active`, GitHub atomically enforces PR-only changes, the source-isolated `harness/evidence` check, strict base freshness, protected force-push/deletion behavior, and no bypass for in-scope actors. The Owner or an explicitly authorized Agent may initiate merge only after those gates are satisfied. In v3.1, `pending` is an establishment interval only; a future authority release may define recovery, but neither state is readiness.

Codex Review is supervised with `trusted_agent_interpreted`: the Agent reads the complete Review from an allowed official App, verifies that it covers the live PR head, and blocks on any finding or ambiguity. Review prose is not translated into a required status.

The required check is published by a dedicated GitHub App, never by the shared GitHub Actions App. Its worker runs a bundled verifier outside the candidate checkout, reads `.harness/repo-contract.json` from the trusted base, and treats the candidate checkout only as data. The repository verifier copy must match the release and SHA-256 recorded in the contract. To update that copy, deploy the new verifier release to the publisher first; only that source-isolated release can authorize its matching repository transition.

Repository-owned product checks may instead be classified as
`external_commit_status` when an external system writes a GitHub Commit Status
without an App identity or Check Run. Its lowercase `system` slug is an audit
label only. It is invalid for `harness/evidence` and proves neither source
isolation nor readiness.

A baseline receipt records a completed validation at one commit. Readiness is recomputed from that receipt, Git drift, current required files, and live platform facts. Changes matching `control_plane_paths` revalidate affected groups; audit-state changes are governed separately.

`repo-harness-verifier-v3.1` ships only the pending-establishment diagnostic.
It does not ship the dedicated App, platform attestor, sandbox profile,
pending-recovery authority, active verifier, or receipt accepter. Therefore a
v3.1 repository remains not ready after establishment, and no local flag or
repository change may activate it. Contract command strings are operator
instructions only and must run, if needed, in an explicitly selected
disposable environment.

## Execution-plan boundary

The generic machine checker requires exactly one Active Plan for a Harness control-plane change and at most one valid Active Plan otherwise. Task complexity is a semantic judgment: the trusted Agent requires a PR-scoped plan for standard and critical product work, while a trivial task may omit one. An ordinary product plan is closed within the same product PR and never changes the Harness receipt. A Harness control-plane plan survives the Harness merge and is archived only by the exact receipt cleanup PR.

A delegated plan records a concrete delegated scope and subagent result. Its
handoff starts with main-agent review, rework, and final acceptance all
`pending`; an accepted diff requires an accepted main-agent review and either
no rework or completed rework. Every plan also closes documentation impact with
an `updated` or `not_applicable` result plus concrete evidence.
