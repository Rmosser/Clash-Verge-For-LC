## Network Diagnostic Compatibility Edition

This app replaces the official `cloud.lazycat.networkdiagnostic` package with a
drop-in compatible package that keeps the original frontend bundle but swaps the
backend for a repository-owned implementation.

Why this exists:

- the official package on the box only ships a compiled backend binary and built
  frontend assets; there is no source tree we can patch and rebuild here
- the official backend mixes resolver behavior with service reachability, which
  makes `ByOrigin` and related checks go red under LazyCat + Mihomo host-native
  setups even when the actual service path is healthy
- this compatibility backend keeps the same package name and endpoint contract
  (`/api/list-api` plus the 8 `By*` endpoints) so the upstream frontend can
  continue working unchanged

Design notes:

- `upstream-dist/` is copied from the installed official package and treated as
  a vendored frontend snapshot
- `server.mjs` implements the diagnostic API using a split model:
  - default resolver checks
  - service reachability checks
- the app is packaged with an extra `api` service container instead of the
  original `exec://` backend binary, because the official backend source is not
  available in this repository

Build:

```bash
cd src/networkdiagnostic-app
lzc-cli project build -f lzc-build.yml -o networkdiagnostic-compat.lpk
```

Install:

```bash
lzc-cli app install src/networkdiagnostic-app/networkdiagnostic-compat.lpk
```
