# Server deployment

**Date:** 2026-10-27
**Feature:** Survey data APIs

Made both survey servers runnable and deployable: process entrypoints
on real sockets with health routes, SSH deployment scripts that take
the source path and SSH target as CLI arguments, systemd units, and a
restart-and-verify-active step at the end of every deployment.
Real-socket end-to-end tests start each server, exercise it over the
wire, and close it whether the test passes or fails.
