# Handoff: NH Supreme Court GitHub Actions and droplet release work

You are working in `gmalbert/nh-supreme-court`, the public Granite State
Appeals repository. The goal is to improve the repository’s use of GitHub
Actions for repeatable data builds and prepare it to run alongside the other
court applications on the user-managed `ubuntu-nh-case-law` droplet.

## Context

The current repository is a Streamlit application centered on `cases.py` and
the `pages/` directory. It includes opinion, order, oral-argument, attorney,
firm, topic, citation, and analysis features. The current GitHub snapshot is
approximately 168 MB, of which `data/` is approximately 155 MB.

The repository currently has a substantial refresh workflow at
`.github/workflows/refresh-data.yml`. It already performs many expensive steps
on `ubuntu-latest`, including scraping, PDF restoration from Cloudflare R2,
parsing, dataset building, optional embedding/frontier asset generation, and
validation.

The runtime host is a small user-managed Ubuntu droplet:

```text
Host: ubuntu-nh-case-law
Disk: 24 GB total, approximately 19 GB free at handoff
RAM: approximately 961 MiB total, approximately 457 MiB available
Swap: none confirmed at handoff; verify before relying on it
Current application: Streamlit under systemd/Caddy
```

The host has enough disk for a carefully selected runtime release, but RAM is
the primary constraint. GitHub Actions should absorb build-time CPU, memory,
and temporary storage wherever practical.

## Desired architecture

```text
GitHub Actions
  → scrape/restore source data
  → build datasets, indexes, embeddings, and models
  → validate release
  → package only runtime files
  → upload immutable release to Cloudflare R2

Droplet
  → download exact release ID
  → verify manifest/checksums
  → install atomically
  → restart Streamlit systemd service
  → serve through Caddy
```

R2 should be treated as release storage and transfer infrastructure. A release
must not be considered live merely because it was uploaded; the droplet still
needs an explicit install and restart step.

## Requested work

Inspect the repository first, then propose and implement the smallest safe set
of changes that accomplishes the following:

1. **Separate build-time and runtime assets.**
   - Identify raw PDFs, temporary extraction files, model-training inputs,
     checkpoints, caches, and other files that the public Streamlit process
     does not need.
   - Keep build-only data in the GitHub runner or R2.
   - Document which files the application requires at startup and at request
     time.
   - Do not remove or rewrite historical data without an explicit backup and
     migration plan.

2. **Create an explicit release manifest.**
   - Include application name, release ID, source commit, build timestamp,
     schema/model versions where relevant, required files, byte sizes, and
     SHA-256 checksums.
   - Make the runtime allowlist explicit.
   - Ensure a release can be validated without importing the Streamlit UI.

3. **Extend GitHub Actions.**
   - Preserve the existing scheduled/manual refresh behavior.
   - Keep expensive calculations on `ubuntu-latest`.
   - Run validation before publication.
   - Build an immutable R2 release only after all required checks pass.
   - Update a small application-specific `current.json` pointer only after the
     full release has uploaded successfully.
   - Do not expose R2 credentials to the running application.

4. **Reduce production dependency weight where safe.**
   - Review whether `torch`, `transformers`, `sentence-transformers`,
     `playwright`, and other heavy packages are required by the public runtime
     or only by refresh/build workflows.
   - If a dependency is build-only, move it to a CI requirements file or an
     optional extra without breaking local development or tests.
   - Do not remove a dependency used by an interactive feature without adding
     a clear fallback or disabling that feature explicitly.

5. **Prepare a droplet-side deployment contract.**
   - Define the expected release directory, manifest format, required files,
     and health-check behavior.
   - Provide a dry-run or verification command that does not restart the app.
   - Provide an atomic-install and rollback procedure.
   - Do not replace durable user state or silently rebuild indexes at startup.

6. **Document systemd/Caddy integration.**
   - Do not assume the final port or hostname; mark them as deployment values
     to be confirmed on the droplet.
   - Ensure Streamlit WebSocket proxying remains supported.
   - Describe how staging must use a separate source/release directory, port,
     and state location.

## Important constraints

- The public application is currently Streamlit. Do not convert it to React or
  FastAPI as part of this workflow/release task.
- Do not require raw PDFs to be present on the droplet if the app only needs
  processed text and indexes.
- Do not commit secrets, R2 credentials, `.env` files, or private deployment
  keys.
- Do not use the droplet as the place where the full refresh or embedding build
  runs.
- Preserve UTF-8 handling for all opinion text and JSON.
- Keep the existing application behavior and page URLs unless a change is
  necessary for the release boundary.
- Treat AI/model output and legal summaries as research aids; retain existing
  disclaimers and validation behavior.

## Tests and acceptance criteria

At minimum, run the repository’s unit tests and the Streamlit smoke/browser
checks that cover the changed areas. Add tests for:

- release manifest creation;
- required-file and checksum validation;
- missing or incompatible release metadata;
- clean release with optional files absent;
- application startup against a staged release;
- representative opinion search, case detail, topic, and source-text paths.

The work is complete when:

- a scheduled or manual workflow produces a versioned, immutable R2 release;
- the release contains only the documented runtime allowlist;
- the release can be verified independently of the UI;
- a droplet-side operator can install and roll back a release safely;
- the Streamlit app starts against the installed release;
- no build-only raw corpus or large temporary artifacts are required on the
  production host;
- the final documentation includes exact commands and known deployment values.

## Deliverables

Please return:

1. a short architecture and storage report;
2. the workflow/release changes;
3. tests and their results;
4. deployment and rollback instructions;
5. a list of assumptions that must be confirmed on the droplet.
