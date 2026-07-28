# Active Plan: migrate Clash Verge for LazyCat to repo-harness-v3

## Metadata

- Status: active
- Task class: critical
- Model: GPT-5.6 Sol
- Reasoning effort: unknown
- Speed: standard
- Delegation route: main_plus_subagent
- Owner: Rmosser

## Goal

Establish the repository-side `repo-harness-v3` contract in the explicit
`repo-harness-verifier-v3.1` pending-only state without changing product
behavior or claiming platform readiness.

## Scope

- In scope: contract, hash-bound diagnostic checker, governance entrypoints,
  PR template, Active Plan lifecycle, declared product-check inventory, and
  removal of the repository-owned `harness/evidence` workflow.
- Out of scope: runtime/product behavior, GitHub platform mutation, push or merge, fabricated Actions evidence, baseline receipt, and cleanup while GitHub Actions is unavailable.

## Baseline

- Receipt: absent and forbidden during pending establishment
- Migration base: `0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`
- Revalidation required: true
- Revalidation groups: entrypoint, evidence, review_protocol, platform

## Implementation

1. Preserve the repository's product truth, commands, and product-owned check
   definitions.
2. Install the v3.1 pending contract and exact hash-bound diagnostic checker;
   remove the same-repository `harness/evidence` workflow.
3. Run the Skill-bundled verifier, repository-owned checks, path/parity checks,
   and fail-closed negative fixtures against the final candidate.
4. During the authorized Actions outage, merge only this initial
   repository-side establishment after a clean exact-current-head official
   Codex Review, live base/head rechecks, and expected-head merge.
5. Leave this plan active, leave the receipt absent, and report all Harness and
   platform readiness fields false.
6. Treat publisher, attestor, sandbox, activation, platform negative tests,
   baseline validation, and receipt cleanup as a separately versioned future
   delivery.

## Validation

- Required files: every path in `.harness/repo-contract.json`
- Required checks: harness/evidence, product/validation (declared inventory; unavailable Actions results
  are not synthesized or treated as green)
- Positive tests: rerun after final checker/hash parity is installed
- Negative tests: shared v3.1 pending-only, path, symlink, inventory, and
  authority-stub regression suite
- Current-head Review: pending; any finding, stale head, partial output,
  timeout, or author ambiguity blocks merge

## Closeout

- Final evidence: pending final local rerun and clean current-head Review
- Merge receipt: absent until an expected-head establishment merge occurs
- Archive destination: `docs/exec-plans/completed/2026-07-28-repo-harness-v3-migration.md`
- Readiness: `platform_machine_gate_ready=false`,
  `atomic_platform_freshness_ready=false`, `repo_harness_ready=false`, and
  `platform_gate_ready=false`
