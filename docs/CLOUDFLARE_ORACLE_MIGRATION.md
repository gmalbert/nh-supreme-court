# Cloudflare Pages and Oracle Cloud migration

This describes a proposed deployment for the React/FastAPI migration. It is
not an instruction to cut over the current site: the new application still
requires feature and visual parity checks and a staging deployment.

## Request and data flow

1. Cloudflare Pages serves the React build. Its Pages Function proxies `/api/*`
   and the API documentation routes to an Access-protected API hostname.
2. A Cloudflare Tunnel on the Oracle Compute instance forwards staging to
   FastAPI on `127.0.0.1:8104` and production to `127.0.0.1:8000`. Both API
   services bind only to loopback and are not directly exposed to the internet.
3. The existing release installer pulls and verifies runtime data from R2,
   switches `/srv/nhsc/current`, and restarts the service. The API reads
   `/srv/nhsc/current/data` and does not receive the R2 credentials.

For the API hostname, configure a Cloudflare Access **Service Auth** policy
that accepts a dedicated service token. Set the token as encrypted Pages
Function secrets `NHSC_ACCESS_CLIENT_ID` and `NHSC_ACCESS_CLIENT_SECRET`, and
set `NHSC_API_ORIGIN` to the HTTPS origin of that protected hostname, without
a path. The Function fails closed when any of these settings are missing. It
does not forward browser-supplied Access headers or cookies, and rejects
redirects to another origin. Rotate the service token and protect the review
endpoint separately; the Pages service token lets all site visitors reach the
public API and is not a user identity or review authorization.

The `webapp/frontend` Pages project root contains `functions/` and the Vite
app. Use `npm ci && npm run build` and output directory `dist`. The build copies
`public/_routes.json` into `dist`, restricting Function execution to the API
and docs routes. Do not add a top-level `404.html` unless configuring a SPA
fallback explicitly; Pages' default SPA behavior serves `index.html` for
unmatched frontend routes.

Connect Cloudflare Pages to the GitHub repository using **Connect to Git**.
Set the Pages project root directory to `webapp/frontend`, the build command to
`npm run build`, and the build output directory to `dist`. Select the GitHub
repository's default branch as the production branch. Cloudflare's native Git
integration builds and deploys pushes to that branch and creates preview
deployments for other branches. Do not enable a second Wrangler deployment
workflow for this project. If the migration branch was pushed before the Pages
GitHub integration was connected, push a new commit to that branch to trigger
its preview build. Keep the repository's existing production branch configured
as the Pages production branch until the preview has been reviewed.

Before the first deployment, set the `NHSC_API_ORIGIN` Pages Function variable
and the encrypted `NHSC_ACCESS_CLIENT_ID` and `NHSC_ACCESS_CLIENT_SECRET`
Function secrets in both the Pages **Production** and **Preview** environments.
Point Preview at the staging API hostname and use a separate Access service
token; point Production at the production API hostname and use its own service
token. A preview deployment will return `503` until its bindings are configured.
See Cloudflare's [Git integration guide](https://developers.cloudflare.com/pages/configuration/git-integration/).

## Oracle instance preparation

- Prepare an Oracle Linux or Ubuntu Compute instance with systemd, Python 3.11+
  and its `venv` support, `curl`, `tar`, and outbound HTTPS access for package
  installation. The staging data workflow installs AWS CLI v2 from AWS's
  verified install script if it is absent. Install the verified R2 data release
  first; on a fresh host,
  `nhsc-release install` activates the verified data without attempting an API
  restart until the API service unit exists. `/api/health` requires
  `/srv/nhsc/current/data/processed/opinions.csv` before code activation.
- The manual GitHub Actions workflow `Deploy FastAPI to Oracle Cloud` packages
  `webapp/backend`, `utils`, and `requirements-runtime.txt`, uploads an
  SHA-256-verified archive, installs a per-commit virtual environment under
  `/opt/nhsc/app/releases/<git-sha>` for production or
  `/opt/nhsc/staging-api/releases/<git-sha>` for staging. Each environment has
  its own current/previous pointers, systemd unit, health check, and data root.
  The staging API uses `nhsc-staging-api.service`, port 8104, and
  `/srv/nhsc-staging`; production uses `nhsc-api.service`, port 8000, and
  `/srv/nhsc`. This lets the staging API share the existing `streamlit-server`
  VM without replacing the Streamlit service. The runtime-data workflow remains
  separate and deploys verified R2 releases through `deploy/nhsc-release`.
  Select **staging** for the first data install and validation before deploying
  staging API code. Both workflows support rollback within the selected
  environment.
- Create GitHub Actions environments named `staging` and `production`. In each
  environment, configure `NHSC_DEPLOY_ENABLED=true`, `NHSC_DEPLOY_HOST`, and
  `NHSC_DEPLOY_USER` as environment secrets or variables, and secrets
  `NHSC_DEPLOY_SSH_KEY` and `NHSC_DEPLOY_KNOWN_HOSTS` for that environment's
  host. `NHSC_DEPLOY_SSH_KEY` may contain an OpenSSH private key or a PuTTY
  `.ppk` key; the workflow converts `.ppk` keys on its temporary runner. For
  cohosted staging, use the same host, SSH user, key, and known-host
  entry as production. If the private
  key is encrypted, also set the optional `NHSC_DEPLOY_SSH_PASSPHRASE` secret;
  both Oracle deployment workflows load it through a temporary SSH agent.
  Add production environment approval rules as appropriate. The deployment SSH
  user must be able to run the installer's system setup and `systemctl`
  operations with `sudo` without an interactive prompt. The installer creates
  the unprivileged `nhsc` service account and installs the unit for the selected
  environment. Keep `/etc/nhsc-api.env` and `/etc/nhsc-api-staging.env`
  root-readable and use them only for app configuration and provider secrets.
  Create `/var/lib/nhsc` and `/var/lib/nhsc-staging` for separate reviewed
  corrections databases; set each environment's `NHSC_REVIEW_DB` and
  `NHSC_REVIEW_TOKEN` in its protected API environment file.
- Install and configure `cloudflared` using a locally or remotely managed
  tunnel. The example `deploy/cloudflared.nhsc.example.yml` shows the local
  routing shape, not real credentials or a hostname. Keep the tunnel
  credentials protected. Permit the tunnel's required outbound connectivity,
  including the documented TCP/UDP port 7844 as applicable, in both OCI network
  rules and the instance firewall. Do not open port 8000 to the internet.
- Install the API runtime prerequisites (`python3`, `python3-venv`, `curl`,
  `tar`, and systemd) on the VM. Configure the existing
  `deploy/nhsc-release` installer for production with
  `NHSC_RELEASE_ROOT=/srv/nhsc`, `NHSC_SERVICE=nhsc-api.service`, and
  `NHSC_HEALTH_URL=http://127.0.0.1:8000/api/health`. For staging, create a
  separate root-readable `/etc/nhsc-release-staging.env` with
  `NHSC_RELEASE_ROOT=/srv/nhsc-staging`,
  `NHSC_SERVICE=nhsc-staging-api.service`, and
  `NHSC_HEALTH_URL=http://127.0.0.1:8104/api/health`. Both configs need the R2
  read credentials (`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`),
  `NHSC_R2_BUCKET`, and `NHSC_R2_ACCOUNT_ID`. Keep R2 credentials in these
  installer configs, not in either API environment file. Create
  `/var/lib/nhsc-staging` for staging review data and set its separate database
  and review token in `/etc/nhsc-api-staging.env`.
  Verify the installer and rollback process in staging before enabling any
  automated deployment.

The installer keeps a `previous` symlink after a successful activation.
`nhsc-release rollback` verifies that release, switches to it, restarts the
service, and checks health; if the check fails it restores the original release.
After a successful rollback, the two release pointers are exchanged. Downloads
are extracted into a separate staging directory before an installed release is
selected, so a verification or reinstall does not overwrite live files.

The API prewarms its in-memory research index in the background when
`NHSC_RUNTIME_MODE=production`. `/api/health` reports basic data availability;
`/api/research/status` separately reports `warming`, `ready`, or `unavailable`.
Wait for `ready` before directing staging traffic to search. The first build
can take considerable time and memory; the dashboard warns visitors while it
is running. Each API worker builds its own index. Set `NHSC_PREWARM_SEARCH=0`
to disable prewarming, or `1` to enable it outside production. This setting
does not write to the immutable release and does not change search results.

## Staging checks before cutover

Confirm the source and runtime release versions, local `/api/health`, Pages
Function bindings, tunnel and Access policy, and frontend routes. Check that
the private API hostname rejects requests without its service token, that
Pages can reach the API, that browser-originated review writes require the
separate review token, and that R2 refresh and rollback work. Compare every
Streamlit page and workflow with the React site on desktop and mobile. Keep
the current public deployment active until the missing features and these
checks are complete.

References: [Cloudflare Pages routing](https://developers.cloudflare.com/pages/functions/routing/),
[Pages Function bindings](https://developers.cloudflare.com/pages/functions/bindings/),
[Pages SPA behavior](https://developers.cloudflare.com/pages/configuration/serving-pages/),
[Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/),
[Tunnel firewall requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/),
and [OCI Compute security](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/compute_security.htm).
