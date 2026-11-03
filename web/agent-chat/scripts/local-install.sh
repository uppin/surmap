#!/bin/sh
# Installs web/agent-chat from the private registry on a machine with no route to public npm.
#
# yarn.lock stays committed with public registry.yarnpkg.com URLs. For the duration of the
# install this script swaps in a copy whose tarball URLs point at $LOCAL_REGISTRY_URL, runs a
# frozen install against that copy, and restores the committed yarn.lock on exit.
#
#   sh scripts/local-install.sh [extra yarn install arguments]
set -eu

cd "$(dirname "$0")/.."

LOCK=yarn.lock
BACKUP=yarn.lock.local-install-backup
PUBLIC=https://registry.yarnpkg.com
REGISTRY=$(printf '%s' "${LOCAL_REGISTRY_URL:-https://npm.dev.wixpress.com}" | sed 's#/*$##')
TEMP=$(mktemp "${TMPDIR:-/tmp}/agent-chat-yarn-lock.XXXXXX")

restore() {
  if [ -f "$BACKUP" ]; then
    mv "$BACKUP" "$LOCK"
  fi
  rm -f "$TEMP"
}
trap restore EXIT
trap 'exit 130' INT TERM

if [ -e "$BACKUP" ]; then
  echo "local-install: $BACKUP exists, so a previous run was interrupted; restore yarn.lock from it, then retry." >&2
  exit 1
fi

committed=$(cksum < "$LOCK")
cp "$LOCK" "$BACKUP"
sed "s#${PUBLIC}/#${REGISTRY}/#g" "$BACKUP" > "$TEMP"
cp "$TEMP" "$LOCK"

echo "local-install: installing from $REGISTRY with a frozen lockfile"
yarn install --frozen-lockfile --registry "$REGISTRY" "$@"

if ! cmp -s "$LOCK" "$TEMP"; then
  echo "local-install: yarn rewrote yarn.lock during a frozen install; refusing to continue." >&2
  exit 1
fi

restore
if [ "$(cksum < "$LOCK")" != "$committed" ]; then
  echo "local-install: the restored yarn.lock differs from the committed one." >&2
  exit 1
fi
echo "local-install: yarn.lock restored to its committed, public-URL form."
