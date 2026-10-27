# Server deployment — entrypoints, SSH deploy scripts, systemd units

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `surmap.survey.cm5_main` and `surmap.survey.station_main`
(`build_description` + `main` on `HypercornHost`), the
`scripts/deploy-{cm5,station}.sh` wrappers over `scripts/deploy-lib.sh`
(source path and SSH target as CLI arguments; rsync, dependency
install, unit render/install, restart, `is-active` gate), the
`deploy/systemd/` units, and `docs/deployment.md`. Verification: V1
fail→pass entrypoint/script tests and real-socket e2es that close
their server on success and failure (398 passed at wrap, mypy strict
and Ruff clean).
