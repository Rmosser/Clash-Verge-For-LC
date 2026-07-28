# Clash Verge for LazyCat documentation index

## Product and operations

- [README.md](../README.md): project entrypoint and quick start.
- [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md): current runtime contract and source of truth.
- [USER_GUIDE.md](USER_GUIDE.md): subscription import, Docker proxy, and user operations.
- [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md): TUN and control-plane bypass risks.
- [SECURITY.md](SECURITY.md): controller isolation and secret handling.
- [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md): host-native recovery and bootstrap.

## Harness governance

- [AGENTS.md](../AGENTS.md): repository bootloader and product constraints.
- [.harness/repo-contract.json](../.harness/repo-contract.json): machine-readable `repo-harness-v3` contract.
- [governance/harness.md](governance/harness.md): current governance model.
- [exec-plans/template.md](exec-plans/template.md): Active Plan template.
- [exec-plans/active/](exec-plans/active/): current plan.
- [exec-plans/completed/](exec-plans/completed/): historical plans.
- [doc-sync-rules.json](doc-sync-rules.json): documentation entrypoint inventory.

The baseline receipt is `.harness/baseline-receipt.json`. Its absence means repository Harness readiness is false.
