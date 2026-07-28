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

Install `repo-harness-v3`, preserve the repository's network/runtime constraints, and make the existing deterministic repository check an explicit product machine gate.

## Scope

- In scope: Harness contract and checker, workflows, PR template, governance entrypoints, documentation inventory, plan lifecycle, and local full validation.
- Out of scope: runtime/product behavior, GitHub platform mutation, push or merge, fabricated Actions evidence, baseline receipt, and cleanup while GitHub Actions is unavailable.

## Baseline

- Receipt: absent
- Validated commit: none
- Migration base: `0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`
- Revalidation required: true
- Revalidation groups: entrypoint, evidence, review_protocol, platform

## Implementation

1. Archive the already-delivered runtime-hardening plan unchanged and keep exactly this migration plan active.
2. Install the v3 contract and immutable trusted verifier/workflow; replace obsolete checkpoint governance text while retaining LazyCat/TUN/security truth sources.
3. Add `product/validation` using the existing `bash scripts/test.sh` entrypoint.
4. Run the checker, JSON/YAML parsing, doc inventory, repository test, negative Harness fixtures, and diff check.
5. During the authorized Actions outage, leave this plan active and the receipt absent. A later delivery task may merge only through a PR with local evidence, clean exact-head Review, live base/head rechecks, and expected-head merge.
6. After Actions returns, smoke both real check publishers, configure and negatively test the platform gate, then use the exact cleanup PR to archive this plan and write the full receipt.

## Validation

- Required files: all files declared by `.harness/repo-contract.json`.
- Required checks: `harness/evidence`, `product/validation` (declared but not live-smoked during the outage).
- Positive tests: local checker; JSON/YAML parse; doc inventory; `bash scripts/test.sh`; diff check.
- Negative tests: missing required file and multiple Active Plans must fail closed; candidate trust-root changes are covered by the immutable v3 checker tests.
- Current-head Review: pending PR; any finding or ambiguity blocks.

## Closeout

- Final evidence: local checker, JSON/YAML parsing, doc inventory, missing-file and duplicate-plan negatives, shared 51-test v3 checker suite, `bash scripts/test.sh`, and diff check passed on 2026-07-28; live Actions/platform evidence remains deferred.
- Merge receipt: absent
- Archive destination: `docs/exec-plans/completed/2026-07-28-repo-harness-v3-migration.md`
