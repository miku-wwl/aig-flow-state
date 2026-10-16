#!/usr/bin/env bash
# Install the protected SDK-only operator service on the existing VM.
# This script never provisions a credential or replaces existing runtime state.
set -euo pipefail
test "$(id -u)" = 0
umask 077

APP=/opt/aegis-relay/app
STATE_ROOT=/var/lib/aegis-relay-sdk-only
STATE=$STATE_ROOT/runtime
SERVICE=aegis-relay-sdk-only
ARMORIQ_ENV=/etc/aegis-relay-sdk-only/armoriq.env
UNIT=/etc/systemd/system/${SERVICE}.service

test -x "$APP/.venv/bin/python"
test -f "$APP/src/safeops/integration/sdk_application.py"
test -f "$APP/src/safeops/integration/sdk_only.py"
test -f /etc/aegis-relay/deepseek.env

if ! id aegis-sdk-only >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_ROOT" --shell /usr/sbin/nologin aegis-sdk-only
fi

if [ ! -e "$STATE_ROOT" ]; then
  install -d -o aegis-sdk-only -g aegis-sdk-only -m 0700 "$STATE_ROOT"
else
  test -d "$STATE_ROOT"
  test "$(stat -c '%U:%G:%a' "$STATE_ROOT")" = "aegis-sdk-only:aegis-sdk-only:700"
fi

if [ ! -e "$STATE" ]; then
  # safeops init creates its destination exclusively; transfer ownership afterward.
  "$APP/.venv/bin/python" -m safeops.main init --state "$STATE" >/dev/null
  chown -R aegis-sdk-only:aegis-sdk-only "$STATE"
  chmod -R go-rwx "$STATE"
else
  test -d "$STATE"
  test "$(stat -c '%U:%G:%a' "$STATE")" = "aegis-sdk-only:aegis-sdk-only:700"
  test -f "$STATE/identity.json"
  test -f "$STATE/gate.sqlite3"
  test -f "$STATE/capability"
  test -f "$STATE/effects.sqlite3"
fi

if [ ! -e "$STATE/armoriq" ]; then
  runuser -u aegis-sdk-only -- "$APP/.venv/bin/python" -m safeops.main init-live --state "$STATE" >/dev/null
else
  test -d "$STATE/armoriq"
  test "$(stat -c '%U:%G:%a' "$STATE/armoriq")" = "aegis-sdk-only:aegis-sdk-only:700"
  test -f "$STATE/armoriq/identity.json"
  test -f "$STATE/armoriq/dispatch.key"
  test -f "$STATE/armoriq/dispatch.pub"
  test -f "$STATE/armoriq/mcp.bearer"
  test -f "$STATE/armoriq/audit.sqlite3"
fi

if [ -e "$ARMORIQ_ENV" ]; then
  test "$(stat -c '%U:%G:%a' "$ARMORIQ_ENV")" = "root:root:600"
fi

# Only an inactive unit may be installed/replaced; never restart an active Action service.
if systemctl is-active --quiet "$SERVICE"; then
  if ! cmp -s deploy/azure/aegis-relay-sdk-only.service "$UNIT"; then
    echo 'SERVICE_ACTIVE_UNIT_CHANGE_REQUIRES_EXPLICIT_MAINTENANCE'
    exit 1
  fi
else
  install -d -o root -g root -m 0700 /etc/aegis-relay-sdk-only
  install -o root -g root -m 0644 deploy/azure/aegis-relay-sdk-only.service "$UNIT"
fi

systemd-analyze verify "$UNIT"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
if ! systemctl is-active --quiet "$SERVICE"; then
  systemctl reset-failed "$SERVICE"
  systemctl start "$SERVICE"
fi

for _ in $(seq 1 20); do
  if curl --fail --silent --show-error http://127.0.0.1:8770/api/health >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:8770/api/health >/dev/null
ss -ltn | grep -Fq '127.0.0.1:8770'

printf 'SDK_ONLY_SERVICE=ACTIVE\n'
printf 'SDK_ONLY_BIND=127.0.0.1:8770\n'
printf 'SDK_ONLY_STATE=%s\n' "$STATE"
printf 'ARMORIQ_CREDENTIAL_PRESENT=%s\n' "$(if [ -s "$ARMORIQ_ENV" ]; then printf YES; else printf NO; fi)"
