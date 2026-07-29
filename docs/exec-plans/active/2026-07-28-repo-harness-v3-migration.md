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

- Validated commit: unavailable until expected-head establishment merge and cleanup receipt
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

- Review rework round 17 shared-verifier: upheld exact-head schema and rendered-evidence findings. Contract path, verifier, revalidation-group, required-check publisher, and publisher-validation objects now reject undeclared fields; baseline labels are mandatory; CommonMark code-span closers do not treat backslashes as escapes.
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
- Review adjudication round 5: upheld the inert doc-sync finding. A
  self-contained repository-owned checker now validates the semantic
  `required_paths` inventory and declared entrypoint links, rejects symlinked
  or escaping paths, and ignores fenced, indented, inline-code, image, and
  otherwise non-navigable Markdown examples. The product
  workflow runs its negative self-test; the contract covers the checker and
  its missing-required-path and missing-entrypoint-link regressions as required
  control files and revalidation commands.
- Review rework round 5: upheld rollout findings now accept as Active Plan evidence only visible rendered Markdown, with container-aware CommonMark fence, indentation, list, task, heading, reference, HTML, autolink, and Unicode semantics; Markdown links and images are replaced by visible prose plus autolinks. Strict JSON rejects duplicate keys and non-standard constants. Initial migration recognizes only minimum legacy structural profiles and rejects malformed identity, contractless legacy runtime, partial v3 scaffolds, or legacy/v3 dual stacks. A rollout finding against the shared verifier concerning gitlinks was disputed: the exact commit-tree OID remains binding, while materialization permits only an absent or empty real directory.
- Review rework round 6: partially upheld the exact-head docs finding.
  Backslash-escaped Markdown links are now rejected with odd/even escape
  regression coverage. The inline HTML code-wrapper claim was disputed because
  GitHub Flavored Markdown still renders its nested anchor as a clickable link;
  the positive control remains covered by tests.
- Review rework round 6 shared-verifier: upheld exact-head findings now recognize customized partial-v3 entrypoints using exact repository path case, including supported uppercase index and PR-template variants. Required Active Plan values remain placeholders when a placeholder token is followed by Unicode punctuation; legitimate longer names remain valid.
- Review rework round 7 shared-verifier: upheld delegation-audit and rendered-evidence boundary findings. Single-agent audit fields are semantically not_applicable except for the task-class-aware fallback; delegated routes require concrete scopes and a result. Non-void self-closing HTML fails closed, while inline code remains visible literal evidence rather than being parsed as raw HTML.
- Review adjudication round 8: upheld the current-runtime inventory finding.
  `docs/CURRENT_RUNTIME.md`, which README declares as the current runtime
  contract and source of truth, is now both a required path and a navigable
  `docs/index.md` target, with a repository-policy regression test. The same
  parser audit excludes container code blocks and single- or multiline code
  spans from navigation evidence.
- Review rework round 9: upheld the reference-link follow-up. Entrypoint
  validation now recognizes full, collapsed, and shortcut references while
  preserving escape parity and reserving escaped-reference and reference-image
  spans against shortcut reinterpretation. Every extracted local inline or
  reference target is existence-checked; exact regressions cover all three
  reference forms, both pseudo-link forms, even escape parity, and dangling
  local targets.
- Review adjudication round 10: upheld all three findings against head
  `b5d526e1877082eca43d1d3e59a8487f8e1d5512`. The documentation contract is
  now opened component-by-component as a regular no-symlink file and parsed
  with duplicate-key rejection. Inline-link extraction uses balanced label
  brackets, so a nested-label link to a missing local target fails closed.
  Regressions retain regular-manifest loading, ordinary and escaped nested
  labels, and nested images as safe controls.
- Review adjudication round 11 rendered-entrypoint: upheld the overlapping
  inline-HTML attribute pseudo-link and reference escape findings. Inline
  candidates whose structural brackets belong to an angle span are excluded,
  while complete inline HTML inside a genuine link label remains navigable.
  Reference patterns consume escapes atomically, rejecting an odd-escaped
  apparent closing bracket while preserving escaped-`]` labels; regressions
  include each violation and its rendered safe control.
- Review rework round 8 shared-verifier: upheld three fail-open schema and migration-signature findings. Pending and active platform gates now use exact state-specific schemas; documentation-index partial-v3 signatures recognize canonical index-relative governance links; and task classes are fixed to trivial, standard, and critical so contract vocabulary cannot disable delegation fallback rules.
- Review rework round 10 shared-verifier: upheld three rendered-evidence findings. CommonMark block-tag openers ending at a line boundary now fail closed; punctuation-only plan values are placeholders; and table-only sections are evaluated by visible cells so empty, separator-only, or placeholder-only tables cannot satisfy required evidence.
- Review rework round 11 shared-verifier: upheld the independent table semantics finding, including optional-edge GFM tables. Table headers and separators are schema rather than evidence; a table-only generic section now requires at least one complete, non-placeholder data row.
- Review rework round 12 shared-verifier: upheld the final GFM table boundary findings. Active Plan table evidence now uses a conservative top-level, blank-boundary subset; short rows, container or open-paragraph layouts, duplicate schemas, hidden table-body headers, inline HTML placeholders, and non-ASCII structural whitespace all fail closed.
- Review rework round 13 shared-verifier: upheld the inline-code/comment ordering finding. Complete exact-delimiter backtick spans are protected before HTML-comment processing; unmatched delimiters or comments remain fail closed.
- Review rework round 14 shared-verifier: upheld exact-head findings now reject mixed diagnostic and candidate arguments, mask multiline code spans before plan-structure parsing, honor escaped backticks, strip placeholder punctuation symmetrically, and reject undeclared nested policy fields. HTML comments and inline code now follow rendered-order precedence.
- Review rework round 15 shared-verifier: upheld exact-head findings now reject identity flags in rendering self-test mode and normalize equivalent CommonMark level-two headings before section uniqueness and order checks.
- Repository review rework round 15: the canonical documentation inventory and index now include the three current product/deployment documents that were previously reachable only through `docs/README.md`.
- Repository review rework round 16: resolved full and shortcut reference links inside an inline-link label now deactivate the outer inline candidate before navigation targets are collected.
- Review rework round 24 shared-verifier: upheld establishment-scope, Unicode visual-blank, misnested inline-HTML, and quoted raw-HTML findings. The initial migration boundary is verifier-owned and independent of the candidate contract; invisible fillers and structurally ambiguous HTML now fail closed.
- Review rework round 25 shared-verifier: upheld pending-establishment scope findings. The fixed migration boundary now names only recognized validation workflows, direct-child checker patterns, and a content-bound Ruff exclusion; release workflows, nested executable scripts, and unrelated pyproject changes fail closed.
- Review rework round 25 documentation: angle masking is limited to syntactically valid CommonMark autolinks and inline HTML.
- Review rework round 26 shared-verifier: upheld exact-head scope, compatibility, and configuration findings. Pending establishment now uses an explicit transitional path inventory, rejects ordinary diffs even from a pending v3 base, binds the fixed Ruff exclusion to `[tool.ruff]`, and remains importable on Python 3.10.
- Review rework round 27 shared-verifier: upheld Python 3.10 and Ruff table findings. The checker no longer imports `tomllib`; it proves the sole fixed exclusion is inside an existing `[tool.ruff]` table or a canonical newly appended table, and rejects ambiguous multiline TOML.
- Current-head Review: pending; any finding, stale head, partial output,
  timeout, or author ambiguity blocks merge

- Review rework round 19 shared-verifier: upheld the remaining schema, mode-separation, and rendered-HTML findings. `task_record_policy.unknown_allowed` is now an exact boolean; empty verification arguments cannot enter rendering self-test mode; and multiline raw-HTML wrappers fail closed before hidden plan structure can be accepted.
- Review rework round 21 shared-verifier: upheld multiline and unmatched inline-HTML findings. Quote-aware tag scanning now rejects every tag opener that crosses a line even when quoted attributes contain angle brackets, and unclosed inline tags cannot conceal required Active Plan evidence.

- Review rework round 21 documentation: upheld balanced-destination and autolink findings. Inline destinations now parse balanced parentheses, while URI autolinks remain valid external links rather than raw HTML.

- Review rework round 23 documentation: upheld multiline inline-HTML handling. Quote-aware scanning rejects tags that cross line boundaries, so Markdown-looking attribute text cannot satisfy entrypoint coverage.

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
