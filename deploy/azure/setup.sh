#!/usr/bin/env bash
# Run only on the newly approved VM. No credential values are accepted as arguments.
set -euo pipefail
test "$(id -u)" = 0
hostname=${1:?canonical Azure DNS hostname required}
baseline=${2:?40-character baseline Git SHA required}
[[ "$hostname" =~ ^[a-z0-9-]+\.australiaeast\.cloudapp\.azure\.com$ ]]
[[ "$baseline" =~ ^[a-f0-9]{40}$ ]]

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates curl git caddy
if ! id aegis-relay >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/aegis-relay --shell /usr/sbin/nologin aegis-relay
fi
install -d -m 0755 /opt/aegis-relay /opt/aegis-relay/python
install -d -o aegis-relay -g aegis-relay -m 0700 /var/lib/aegis-relay
install -d -m 0700 /etc/aegis-relay
if [ ! -x /usr/local/bin/uv ]; then
  curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/0.11.16/install.sh -o /tmp/aegis-uv-install.sh
  UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh /tmp/aegis-uv-install.sh
fi
export UV_PYTHON_INSTALL_DIR=/opt/aegis-relay/python
uv python install 3.13.9
if [ ! -d /opt/aegis-relay/app ]; then
  git clone https://github.com/miku-wwl/aig-flow-state.git /opt/aegis-relay/app
  git -C /opt/aegis-relay/app checkout --detach "$baseline"
else
  # Refuse to reuse an unrelated deployment tree.
  test -f /opt/aegis-relay/deployment-baseline
  test "$(cat /opt/aegis-relay/deployment-baseline)" = "$baseline"
fi
printf '%s\n' "$baseline" >/opt/aegis-relay/deployment-baseline
tar --no-same-owner -xzf /tmp/aegis-source.tar.gz -C /opt/aegis-relay/app
cd /opt/aegis-relay/app
uv sync --locked --no-dev --python 3.13.9
chmod -R go-w /opt/aegis-relay
if [ ! -e /var/lib/aegis-relay/public ]; then
  runuser -u aegis-relay -- .venv/bin/python -m safeops.public_demo init --state /var/lib/aegis-relay/public
else
  test -f /var/lib/aegis-relay/public/demo.sqlite3
fi

if [ ! -e /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 0600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  printf '/swapfile none swap sw 0 0\n' >>/etc/fstab
fi

sed "s/__HOSTNAME__/$hostname/g" deploy/azure/aegis-relay.service >/etc/systemd/system/aegis-relay.service
sed "s/__HOSTNAME__/$hostname/g" deploy/azure/Caddyfile.template >/etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable aegis-relay caddy
systemctl restart caddy
# The service is started separately after the authorized SSH credential transfer.
printf 'SETUP=READY_FOR_PRIVATE_ENVIRONMENT\n'
