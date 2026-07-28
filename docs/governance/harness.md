# Harness governance

Current rollout status: repository-side migration is in progress during an authorized GitHub Actions outage. The baseline receipt is intentionally absent, live checks and platform negative tests are deferred, and `repo_harness_ready`, `platform_machine_gate_ready`, and `atomic_platform_freshness_ready` are false. The policy below is the target contract, not a claim that the live platform is ready.

The repository uses `repo-harness-v3`.

GitHub atomically enforces PR-only changes, required machine checks, strict base freshness, protected force-push/deletion behavior, and no bypass for in-scope actors. The Owner or an explicitly authorized Agent may initiate merge only after those gates are satisfied.

Codex Review is supervised with `trusted_agent_interpreted`: the Agent reads the complete Review from an allowed official App, verifies that it covers the live PR head, and blocks on any finding or ambiguity. Review prose is not translated into a required status.

The trusted-base verifier reads `.harness/repo-contract.json` from the base commit and treats the candidate checkout only as data. A candidate cannot weaken the policy that judges itself.

A baseline receipt records a completed validation at one commit. Readiness is recomputed from that receipt, Git drift, current required files, and live platform facts. Changes matching `control_plane_paths` revalidate affected groups; audit-state changes are governed separately.
