# React and FastAPI migration

The React application and FastAPI service implement the public navigation and
profile routes declared in `cases.py`. The frontend API path audit maps every
React API path form to a FastAPI route declaration. Interactive and rendered
parity still need final staging verification; keep the current public
application and verified runtime release process authoritative until then.

The FastAPI runtime uses `requirements-runtime.txt`; Streamlit is optional and
is not installed on the Oracle API service. Shared cached data helpers use
Streamlit's cache when the UI package is present and a bounded in-process cache
in the API service. Provider and review credentials are read from environment
variables on the server.

For local development, install the runtime Python dependencies and run
`python -m uvicorn webapp.backend.main:app --host 127.0.0.1 --port 8000` from
the repository root. In `webapp/frontend`, install the dependencies from
`package.json` and run `npm run dev`. Vite proxies `/api` to port 8000.
`NHSC_DATA_ROOT` selects the data directory within a verified runtime release.

## Reviewed corrections

Review writes are disabled unless both `NHSC_REVIEW_TOKEN` and `NHSC_REVIEW_DB`
are configured for the API process. Set the token as a secret and point the
database setting to a persistent, service-writable SQLite file outside the
immutable data release. The token is submitted in the `X-Review-Token` request
header. Only observations currently in the displayed review queue can be
saved. Corrections are written to the `reviewed_observation` table with their
source hash and extractor version; they do not change published data or the
release's `field_observations.sqlite`. Back up this separate database and
include its records in the review pipeline before promoting corrections.
Protect the review endpoint at the deployment edge and keep the token out of
the frontend build and version control.
