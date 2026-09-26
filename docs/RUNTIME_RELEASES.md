# Runtime releases

GitHub Actions builds all scraped, parsed, indexed, and model-derived data. The
public Streamlit process only receives a verified runtime release; it must not
run scrapers, parsers, index builders, model trainers, or embedding builders.

## Release contents

`scripts/build_runtime_release.py` creates a directory and gzip archive with
only the allowlisted data paths defined in `utils/runtime_release.py`:

- `data/processed/` (opinion text, oral-argument data, public indexes, and metadata);
- `data/retrieval/`;
- the small public reference files in `data/` needed by the UI.

It excludes `data/raw/` entirely. Each release has a `manifest.json` recording
the application, release ID, source commit, timestamp, allowlist, required
files, byte sizes, and SHA-256 checksum for every released file.

Dense embedding artifacts are also deliberately excluded from the public
runtime release. They are built in GitHub Actions but would require Torch and
Sentence Transformers to turn a live query into a vector. The application
automatically uses its shipped TF-IDF retrieval fallback instead, so the
public service stays lightweight without silently downloading a model.

## One-time runtime seed

Some complete oral-argument artifacts are intentionally ignored by Git. Before
the first Actions release, upload the complete local `data/processed/` tree to
the existing private R2 bucket at:

```text
releases/nh-supreme-court/runtime-seed/data/processed/
```

Use a temporary or existing **write-capable** R2 credential locally; never put
it on the droplet. With the R2 environment variables already set in the local
shell, run:

```powershell
$r2Endpoint = "https://$env:CLOUDFLARE_ACCOUNT_ID.r2.cloudflarestorage.com"
aws s3 sync data\processed `
  "s3://$env:R2_BUCKET/releases/nh-supreme-court/runtime-seed/data/processed" `
  --endpoint-url $r2Endpoint `
  --no-progress
```

The refresh workflow restores this seed before rebuilding current data. It
then publishes the immutable release separately. The seed is a private build
input, not the droplet's serving source.

Build and inspect a local release:

```powershell
python scripts/build_runtime_release.py --output-root dist/releases --release-id local-test
python scripts/verify_runtime_release.py dist/releases/local-test
```

The production process sets both values below. With no variables, developers
continue to use the checkout's `data/` directory.

```text
NHSC_DATA_ROOT=/opt/nh-supreme-court/current/data
NHSC_RUNTIME_MODE=production
```

`NHSC_RUNTIME_MODE=production` disables the legacy automatic dataset rebuild.
An invalid or incomplete release must be rejected by deployment verification,
not repaired by the web process.

## R2 layout and promotion

The existing private bucket keeps raw PDFs under `pdfs/`. Runtime releases use
a separate prefix:

```text
releases/nh-supreme-court/<release-id>/manifest.json
releases/nh-supreme-court/<release-id>/runtime.tar.gz
releases/nh-supreme-court/current.json
```

The workflow uploads immutable manifest and archive objects first, then writes
`current.json` last. Uploading an object never activates it on the droplet.

## Droplet contract

The future privileged installer must download `current.json`, fetch the named
archive and manifest, verify checksums before activation, unpack into a new
release directory, switch the `current` symlink atomically, restart the
Streamlit service, and check `/_stcore/health`. On health-check failure it must
restore the preceding symlink and restart that prior service.

Deployment-specific values remain intentionally unset: SSH host/user, systemd
unit, local health port, and the deployment-only R2 read credential. The
Streamlit systemd unit must not receive R2 credentials.

Install `deploy/nhsc-release` as `/usr/local/sbin/nhsc-release` and create a
root-readable `/etc/nhsc-release.env` containing the R2 read credentials,
bucket/account ID, release root, service name, and health URL. GitHub needs
`NHSC_DEPLOY_SSH_KEY` and `NHSC_DEPLOY_KNOWN_HOSTS` secrets plus
`NHSC_DEPLOY_HOST` and `NHSC_DEPLOY_USER` environment variables. Use GitHub's
`production` Environment protection rule to require approval before the
automatic deployment job runs. Set `NHSC_DEPLOY_ENABLED` to `true` only after
those values and the droplet installer are in place; publishing to R2 works
independently while deployment is disabled.
