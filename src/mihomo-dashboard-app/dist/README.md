This directory is the LPK "contentdir".

The actual dashboard is **metacubexd** and is downloaded at deploy/build time.

Common workflows:

- Update + deploy to LazyCat box:
  - `scripts/deploy_dashboard.sh`

- Update assets only (pin via `METACUBEXD_VERSION=vX.Y.Z`):
  - `scripts/update_metacubexd.sh`

