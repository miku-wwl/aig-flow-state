# Single-VM public simulation

Provisioning is conditional on explicit operator cost approval. The target is a
new Australia East Ubuntu Minimal x64 B2ats_v2 VM, one 30-GiB Standard_LRS HDD
OS disk, no data disk, Standard IPv4,
one NIC/VNet/NSG. Permit public TCP 80/443; permit TCP 22 only from the operator's
current public IPv4 /32. Do not open 8765, SQLite or Caddy's admin port.

Use existing Azure CLI authentication. Never upgrade the student subscription.
Confirm allocation restrictions, quota and approved cost before creation. B1s
was unavailable for the inspected subscription; this is not a claim of a free
meter entitlement. Recheck live prices and free usage before relying on benefits.

The requested 16-GiB StandardSSD_LRS disk was rejected by Azure because this
Canonical Ubuntu Minimal image requires at least 30 GiB. The operator then
approved a 30-GiB Standard_LRS HDD (billed as S4/32 GiB) within the same USD 3.50
estimate. Do not silently enlarge the disk, add a data disk or use a premium disk.
Read back the actual disk size and type before installing the application. The
advertised free managed-disk benefit specifies P6/64 GiB; this disk does not
inherit that meter benefit. Subscription-specific remaining benefit is unverified.

Use Trusted Launch for this Gen2 VM. The image and B-series support it; do not
disable Trusted Launch or register the Standard-security feature to bypass it.

The deployment operator prepares a source archive from tracked source plus the
reviewed new source/deployment files. It contains no .git, .runtime, .artifacts,
private key, capability, environment secret or database. Clone the public GitHub
repository at its recorded baseline SHA, overlay that archive and install with
`uv sync --locked --no-dev`. The Core remains pinned to
`fd742b783058a53400c465b4ab59c6e80715895a`; verify installed direct_url metadata.
Record a SHA-256 source manifest because these deployment changes are not pushed
without separate authorization.

Transfer source and setup.sh using SSH. Verify the SSH host public key through
the Azure control plane before sending the DeepSeek credential. Execute setup.sh
as root with only hostname and baseline Git SHA arguments. It initializes a NEW
private control directory once, and preserves all later session state.

Only after separate key-transfer authorization, send the existing local DeepSeek
key over SSH standard input into `/etc/aegis-relay/deepseek.env` (root:root 0600),
without command arguments, terminal echo, shell tracing or logs. Do not install
ArmorIQ CLI credentials or an operator capability on this public service.
Start the service after the private environment exists. One loopback worker and
Caddy serve the public hostname with a trusted ACME certificate.

The public facade composes only mock execution with a separate Core and business
store per anonymous cookie session. The original operator app remains unchanged
and is never mounted publicly. The protected SDK-only operator service below
uses separate state and credentials and loopback access through an SSH tunnel;
none of its live approval/execution APIs are routed by Caddy.

## Protected SDK-only operator service

`setup-sdk-only-operator.sh` installs an additional `aegis-relay-sdk-only`
systemd service on the existing VM. It runs as the separate `aegis-sdk-only`
Unix account, uses a new state directory at
`/var/lib/aegis-relay-sdk-only/runtime`, and listens only on `127.0.0.1:8770`. It does
not change the public service, Caddy configuration, firewall, or Azure
resources. The deployment script initializes state only in a new empty
directory; it refuses to overwrite an existing state or replace a changed unit
while the service is active. It explicitly provisions the separate local signed
dispatch permit keys and audit database with `safeops init-live`.

Access it through an authenticated SSH local port forward bound to the
operator's loopback interface, then open `http://127.0.0.1:18770`. The Runtime
capability stays separate from ArmorIQ credentials and is loaded into the UI
from a private local file; the application keeps it in browser memory. The
ArmorIQ environment file, when separately authorized and provisioned, is
`/etc/aegis-relay-sdk-only/armoriq.env` (`root:root`, mode `0600`). The service
starts without that optional file, but SDK preparation fails closed until
credentials exist. The environment file is not served through Caddy.

The service reads the existing DeepSeek environment file for bounded planning
(`deepseek-flash`, thinking disabled, 28-second timeout, 600 output tokens).
Its systemd memory ceiling is 384 MiB to fit the existing small VM alongside
the public service.
Only a single operator using the private SSH tunnel can reach the live UI; no
public route or unauthenticated browser endpoint is added. Verify the service
listener remains loopback-only and keep its approval, authorization, SDK stage,
execution and audit APIs off the public reverse proxy.

Limits: 4 Plans/session, 40/day and 160 total, one concurrent model generation,
1500 input characters, 600 output tokens, 28-second timeout, 80 sessions total,
8 new sessions/IP/day, 90 API requests/IP/minute and 5000 API requests/day. Limits
and sessions persist across restart. A Secure HttpOnly SameSite=Strict session
cookie, same-origin mutation checks and CSRF token are required. The server
retains each Runtime capability; public Authorization headers are rejected.

Validate cloud DNS/TLS, anonymous privileged rejection, an explicit synthetic
Plan/Approval/Admission/Authorization/mock execution and matching durable receipt.
Restart the service safely and read back the same Action/record. Never dispatch
an Unknown Action. Do not run a real ArmorIQ Action, live Deny probe or startup
business operation.

Keep the approved demo available through 21 October 2026 NZDT. Stopping a VM
does not stop disk/IP costs. After exporting authorized sanitized evidence, the
operator can remove only `rg-aegis-relay-demo-20261016` to stop its ongoing costs;
do not delete unrelated resources or historic Windows state.
