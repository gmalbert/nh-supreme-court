# Cloudflare R2 PDF Storage Migration

## Goal

Move the raw court PDFs out of Git history and into a private Cloudflare R2 bucket. GitHub Actions will continue to run the refresh code, but it will restore the PDFs from R2 before parsing and upload newly downloaded PDFs afterward.

The Streamlit app does not need to read the PDFs from R2. It already links users to the official court URLs in `pdf_url`; the raw files are pipeline inputs used for parsing, auditing, and dataset generation.

## Target architecture

```text
GitHub repository
  - application code
  - scraper/parser code
  - indexes and processed datasets

GitHub Actions runner
  - restores only the PDFs needed for the selected refresh years from R2
  - scrapes current indexes
  - downloads only PDFs missing locally
  - parses PDFs
  - uploads new PDFs to R2
  - commits processed datasets

Cloudflare R2
  - private persistent copy of data/raw/pdfs/
```

R2 Standard currently includes 10 GB-month of storage, 1 million Class A operations, 10 million Class B operations, and free egress each month. The current local archive is approximately 455 MB across 4,802 PDFs, so it fits comfortably within the storage allowance. Confirm current pricing before enabling billing: <https://developers.cloudflare.com/r2/pricing/>.

## Before starting

Do not delete the local PDFs until the first R2 upload and a restore test both succeed.

Run these checks from the repository root:

```powershell
$pdfs = Get-ChildItem data\raw\pdfs -Recurse -File
[PSCustomObject]@{
    Files = $pdfs.Count
    MiB = [math]::Round((($pdfs | Measure-Object Length -Sum).Sum / 1MB), 2)
}
```

The expected baseline is approximately 4,802 files and 455 MiB. If the count is materially different, investigate before uploading.

## 1. Create the R2 bucket

In the Cloudflare dashboard:

1. Open **R2 Object Storage**.
2. Create a private bucket, for example `nh-supreme-court-pdfs`.
3. Use Standard storage.
4. Do not enable public access. The app does not need public R2 URLs.
5. Record the Cloudflare Account ID.

Use a bucket prefix of `pdfs/` so the remote layout mirrors the local directory:

```text
R2 bucket: nh-supreme-court-pdfs
  pdfs/2002/*.pdf
  pdfs/2003/*.pdf
  ...
  pdfs/orders/2025/*.pdf
```

## 2. Create a narrowly scoped R2 API token

Create an R2 API token with:

- Object Read and Write
- Access limited to the new bucket

Do not use a global Cloudflare API token. Save the generated access key ID and secret immediately; the secret is shown only once.

Add these GitHub Actions secrets under **Repository Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `R2_BUCKET` | `nh-supreme-court-pdfs` |
| `R2_ACCESS_KEY_ID` | R2 access key ID |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |

The repository does not need to know the Cloudflare account password or a full Cloudflare API token.

## 3. Install the AWS-compatible client locally

R2 exposes an S3-compatible API. Install the AWS CLI on the machine that holds the current PDF archive.

```powershell
python -m pip install awscli
aws --version
```

Set temporary session variables. Replace the placeholder values; do not commit this file or the values.

```powershell
$env:AWS_ACCESS_KEY_ID = "replace-with-r2-access-key-id"
$env:AWS_SECRET_ACCESS_KEY = "replace-with-r2-secret-access-key"
$env:AWS_DEFAULT_REGION = "auto"
$r2Endpoint = "https://$env:CLOUDFLARE_ACCOUNT_ID.r2.cloudflarestorage.com"
$r2Bucket = "nh-supreme-court-pdfs"
```

If the account ID is not already an environment variable:

```powershell
$env:CLOUDFLARE_ACCOUNT_ID = "replace-with-cloudflare-account-id"
```

## 4. Upload the existing local archive once

First, list the bucket to confirm the credentials and endpoint work:

```powershell
aws s3 ls "s3://$r2Bucket" --endpoint-url $r2Endpoint
```

Upload the existing PDFs:

```powershell
aws s3 sync `
  data\raw\pdfs `
  "s3://$r2Bucket/pdfs" `
  --endpoint-url $r2Endpoint `
  --no-progress
```

Verify the remote object count:

```powershell
$remoteCount = aws s3 ls "s3://$r2Bucket/pdfs" --recursive --endpoint-url $r2Endpoint |
    Where-Object { $_ -match '\.pdf$' } |
    Measure-Object
$remoteCount
```

The remote count should match the local PDF count.

## 5. Test a restore before changing the workflow

Use a separate temporary folder so the existing archive is not touched:

```powershell
$restoreDir = Join-Path $env:TEMP "nh-supreme-court-r2-restore"
New-Item -ItemType Directory -Force $restoreDir | Out-Null

aws s3 sync `
  "s3://$r2Bucket/pdfs" `
  $restoreDir `
  --endpoint-url $r2Endpoint `
  --no-progress

$restored = Get-ChildItem $restoreDir -Recurse -File
[PSCustomObject]@{
    Files = $restored.Count
    MiB = [math]::Round((($restored | Measure-Object Length -Sum).Sum / 1MB), 2)
}
```

Do not proceed until the restored count and size match the local baseline.

## 6. Update the GitHub Actions workflow

The current workflow already uses `xvfb-run` for browser-based scraping. Add the R2 sync steps around the download phase in `.github/workflows/refresh-data.yml`.

### Add the client installation

After the existing dependency installation step, add:

```yaml
      - name: Install R2 sync client
        run: python -m pip install awscli
```

### Restore PDFs for the selected refresh years

Add this step after the scraper steps and before `Download new PDFs`:

```yaml
      - name: Restore raw PDFs from Cloudflare R2
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: auto
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          R2_BUCKET: ${{ secrets.R2_BUCKET }}
        run: |
          set -euo pipefail
          R2_ENDPOINT="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
          YEAR_ARGS="${{ github.event.inputs.years }}"
          if [ "${{ github.event.inputs.historical_backfill }}" = "true" ]; then
            YEAR_ARGS=$(seq 2002 $(date +%Y))
          elif [ -z "$YEAR_ARGS" ]; then
            CURRENT_YEAR=$(date +%Y)
            YEAR_ARGS="$((CURRENT_YEAR - 3)) $((CURRENT_YEAR - 2)) $((CURRENT_YEAR - 1)) $CURRENT_YEAR"
          fi

          echo "Restoring PDF archive years: $YEAR_ARGS"
          for YEAR in $YEAR_ARGS; do
            aws s3 sync \
              "s3://${R2_BUCKET}/pdfs/${YEAR}" \
              "data/raw/pdfs/${YEAR}" \
              --endpoint-url "${R2_ENDPOINT}" \
              --no-progress

            if [ "$YEAR" -ge 2014 ]; then
              aws s3 sync \
                "s3://${R2_BUCKET}/pdfs/orders/${YEAR}" \
                "data/raw/pdfs/orders/${YEAR}" \
                --endpoint-url "${R2_ENDPOINT}" \
                --no-progress
            fi
          done
```

The default run restores the current year plus the prior three years. A manually supplied `years` value restores only those years; `historical_backfill=true` restores the full archive. The existing downloader will naturally skip PDFs restored from R2 because its current local-file check is already idempotent.

### Upload new PDFs after downloading

Add this step after both PDF download steps and before parsing:

```yaml
      - name: Persist raw PDFs to Cloudflare R2
        if: always()
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: auto
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          R2_BUCKET: ${{ secrets.R2_BUCKET }}
        run: |
          set -euo pipefail
          R2_ENDPOINT="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
          aws s3 sync \
            data/raw/pdfs \
            "s3://${R2_BUCKET}/pdfs" \
            --endpoint-url "${R2_ENDPOINT}" \
            --no-progress
```

`if: always()` ensures newly downloaded files are persisted even if one download request fails. The credentials remain masked by GitHub Actions.

## 7. Validate the first R2-backed run

Run the workflow manually with a narrow year selection first, such as the current year only. Confirm:

1. The restore step reports existing objects.
2. The opinion and order download steps report mostly `skipped`, not `downloaded`.
3. Parsing succeeds using restored PDFs.
4. The upload step completes.
5. Validation succeeds.
6. The processed-data commit contains data changes only—not `data/raw/pdfs/`.

Then run the normal four-year refresh and confirm the download count is limited to genuinely new or missing PDFs.

## 8. Keep raw PDFs out of Git

Leave this `.gitignore` rule in place:

```gitignore
data/raw/
```

Do not use `git add -f data/raw/pdfs`. R2 is now the persistent source for raw pipeline artifacts; Git should contain the reproducible code, indexes, and processed outputs.

## Security and operating notes

- Keep the R2 bucket private.
- Scope the API token to this bucket only.
- Store credentials only in GitHub Secrets or temporary local environment variables.
- Never put R2 credentials in workflow YAML, Python source, or committed documentation.
- R2 is storage; GitHub Actions remains the compute environment.
- The Streamlit app does not need R2 credentials and should not access the private bucket.
- R2 cache/storage is not a substitute for a second backup. If the PDFs are important as an archive, periodically export a backup separately.

## Rollback

If the R2 integration fails:

1. Disable the restore and upload steps in `refresh-data.yml`.
2. Restore the prior workflow commit.
3. Keep the official `pdf_url` links and processed datasets unchanged.

The application will continue to function because it does not depend on local PDFs at runtime.
