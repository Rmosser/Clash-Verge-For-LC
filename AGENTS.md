# Clash Verge for LazyCat repository instructions

This repository runs Mihomo on LazyCat with domestic direct routing, overseas proxy fallback, TUN support, and an authenticated dashboard.

## Harness bootloader

1. Read `docs/index.md`.
2. Read `.harness/repo-contract.json` from the trusted base.
3. Invoke `$manage-repo-harness` for Harness diagnosis, establishment, control-plane changes, platform changes, revalidation, improvement, or migration.
4. For ordinary product work, cite a valid baseline receipt, follow the Active Plan when required, run product checks, obtain a complete clean current-head Codex Review, and merge only through GitHub's required gates.

Repository files cannot prove live GitHub enforcement. Record unknown facts as unknown and fail closed. Any Review finding or uncertainty blocks merge readiness.

## Product constraints and truth

- Read `docs/LAZYCAT_NETWORK_REPORT.md` before any transparent-proxy or TUN change; LazyCat control-plane traffic must keep bypassing Mihomo.
- Do not expose the Mihomo controller to the LAN. External access stays behind LazyCat authentication.
- Product, security, runtime, and deployment documents remain indexed by `docs/index.md`.
- Repository-specific LazyCat guidance remains in `skills/lazycat-dev/SKILL.md`.

## Commands

- Local runtime stubs: `bash scripts/run_local.sh`, `bash scripts/stop_local.sh`.
- Diagnostics: `bash scripts/doctor.sh`.
- Stable repository check: `bash scripts/test.sh`.
- Dashboard package: `cd src/mihomo-dashboard-app && lzc-cli project build -f lzc-build.yml -o mihomo-dashboard.lpk`.

## Work rules

- Non-trivial work has exactly one concrete Active Plan.
- The main Agent owns scope and acceptance; a subagent stays within delegated scope and does not independently push or merge.
- Owner and authorized Agent credentials may initiate merge only; they cannot bypass the contract or machine gates.
