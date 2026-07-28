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
- Out of scope: runtime/product behavior, fabricated Actions or
  `harness/evidence`, activation, baseline receipt, cleanup, and any readiness
  claim.

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
4. Keep merge authority external to this repository contract; local evidence and Review do not create platform readiness or authorize a merge.
5. Leave this plan active, leave the receipt absent, and report all Harness and
   platform readiness fields false.
6. Treat publisher, attestor, sandbox, activation, platform negative tests,
   baseline validation, and receipt cleanup as a separately versioned future
   delivery.

## Delegation Audit

- Delegated scope: repository inventory, bounded v3.1 migration, platform read-only audit, and independent diff review
- Forbidden scope: product behavior, credentials, platform mutations, merge initiation, and work outside the delegated repository scope
- No-subagent fallback reason: not_applicable
- Subagent result: completed within scope and returned with local validation
  evidence; current-head Review exposed unsafe candidate read ordering, and
  the shared authoritative checker plus this parity copy were hardened
- Main agent review: accepted
- Rework requested: completed
- Final accepted diff: accepted

## Validation

- Required files: every path in `.harness/repo-contract.json`
- Required checks: harness/evidence, product/validation (declared inventory; unavailable Actions results
  are not synthesized or treated as green)
- Positive tests: rerun after final checker/hash parity is installed
- Negative tests: shared v3.1 pending-only, path, symlink, inventory, and
  authority-stub regression suite
- Review rework: candidate required files are preflighted before plan/eval
  parsing; contract, template, plans, and manifests are opened without
  following symlinks, bounded by size, and rejected on identity drift
- Evidence rework: shared tests now cover required/template symlinks,
  oversized plans, recursively discovered nested/additional plans, placeholder
  sections/fields, and the explicit one-plan pending policy
- Review rework round 2: the shared checker rejects dangling evaluation symlinks and off-layout manifests, Markdown-wrapped or comment-only placeholders, empty multiline fields, unchanged template sections, and delegation records without an explicit forbidden scope.
- Review rework round 3: the shared checker validates only rendered plan prose, rejects placeholder-valued required fields, constrains active eval fixtures to distinct regular files inside their rule directory, and requires an explicit no-subagent fallback record.
- Review rework round 4: upheld exact-head findings now require valid CommonMark closing fences, fail closed on raw HTML blocks, normalize inline HTML before placeholder detection, bind candidate verification to the exact git graph and complete base/head source trees including gitlink OIDs, enforce declared Active Plan sections, fields and tables, and allow receipt cleanup only when the receipt is newly added.
- Current-head Review: pending; any finding, stale head, partial output,
  timeout, or author ambiguity blocks merge

## Documentation Impact

- Result: updated
- Evidence: entrypoint, contract, governance, plan, and PR documentation were
  synchronized with the pending v3.1 boundary and repository-specific checks

## Closeout

- Final evidence: pending final local rerun and clean current-head Review
- Merge receipt: absent until an expected-head establishment merge occurs
- Archive destination: `docs/exec-plans/completed/2026-07-28-repo-harness-v3-migration.md`
- Readiness: `platform_machine_gate_ready=false`,
  `atomic_platform_freshness_ready=false`, `repo_harness_ready=false`, and
  `platform_gate_ready=false`
