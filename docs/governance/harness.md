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

The machine-readable `execution_plan_policy` requires exactly one top-level
Active Plan throughout pending establishment, rejects additional or nested
plans, and forbids ordinary product work until an active baseline exists. A
Harness control-plane plan survives the Harness merge and is archived only by
the exact receipt cleanup PR. Once a future authority release makes ordinary
product work possible, task complexity remains a semantic judgment: standard
and critical work uses a PR-scoped plan, while a trivial task may omit one.

A delegated plan records concrete delegated and forbidden scopes plus the
subagent result, while its no-subagent fallback reason is `not_applicable`.
Its handoff starts with main-agent review, rework, and final acceptance all
`pending`; an accepted diff requires an accepted main-agent review and either
no rework or completed rework. A standard or critical `single_agent` plan must
instead record a concrete no-subagent fallback reason. Every plan also closes
documentation impact with an `updated` or `not_applicable` result plus concrete
evidence.

Before parsing any candidate contract, template, plan, or evaluation manifest,
the verifier traverses repository-relative components without following
symlinks, requires bounded regular files, and reads through no-follow file
descriptors. Any nested plan, oversized file, path race, placeholder-only
required section, or ambiguous candidate surface fails closed.
