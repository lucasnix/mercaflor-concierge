#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_HOST:?Set DEPLOY_HOST in repository variables}"
: "${DEPLOY_HOST_KEY:?Set the server public host key in repository variables}"
: "${DEPLOY_SSH_KEY:?Set DEPLOY_SSH_KEY in repository secrets}"
: "${GITHUB_SHA:?Missing commit}"
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9.-]+$ ]] || { echo 'Invalid SSH host'; exit 1; }
[[ "$DEPLOY_HOST_KEY" =~ ^ssh-ed25519\ [a-zA-Z0-9+/=]+(\ .*)?$ ]] || { echo 'Expected an Ed25519 server host key'; exit 1; }
[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 1
umask 077
key_dir=$(mktemp -d)
trap 'rm -rf -- "$key_dir"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$key_dir/id_ed25519"
printf '%s %s\n' "$DEPLOY_HOST" "$DEPLOY_HOST_KEY" > "$key_dir/known_hosts"
connection=(-T -i "$key_dir/id_ed25519" -p 22 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$key_dir/known_hosts" -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "cpmercaflordeploy@$DEPLOY_HOST")
ssh "${connection[@]}" probe
archive="$key_dir/site.tar.gz"
python3 scripts/deploy_archive.py dist "$archive"
ssh "${connection[@]}" "deploy $GITHUB_SHA" < "$archive"
