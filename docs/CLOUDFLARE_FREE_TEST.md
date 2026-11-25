# Dina on Cloudflare Workers Free (test branch)

This deployment target is isolated to `cloudflare-free-test`. It does not change `main`, the production API, or production data.

## Architecture

- The existing FastAPI application in `backend/src/main.py` runs on Cloudflare Python Workers using Cloudflare's ASGI adapter.
- PostgreSQL remains an external PostgreSQL service. Cloudflare Hyperdrive provides pooled connections; it does not host or replace PostgreSQL.
- Use a separate, disposable test database. Never point this Worker at production.
- The Flutter app can use the deployed Worker URL as `API_BASE_URL`.

## Free services

A practical $0 test setup is:

1. **Cloudflare Workers Free** for the FastAPI compute.
2. **Neon Free** for a disposable PostgreSQL project/database.
3. **Cloudflare Hyperdrive Free** to connect the Worker to PostgreSQL.

Neon's current Free plan includes 100 CU-hours and 1 GB PostgreSQL storage per project. It scales to zero after five minutes idle. See [Neon Free plan limits](https://neon.com/docs/introduction/free-tier) and [Neon pricing](https://neon.com/pricing).

Cloudflare Workers Free currently allows 100,000 requests/day, 128 MB memory, and 10 ms CPU per HTTP request. Hyperdrive Free includes 100,000 database queries/day. These are usage limits, not a guarantee that every Dina route fits the CPU budget. See [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) and [Hyperdrive pricing](https://developers.cloudflare.com/hyperdrive/platform/pricing/).

**Important application limitation:** Dina uses Argon2id password hashing with a deliberately strong memory/time cost. Registration and login are CPU-intensive and are likely to exceed the Workers Free 10 ms CPU budget. Do not weaken password hashing to make the free tier pass. Start with health/readiness and light API compatibility tests. Full authentication and end-to-end testing may require a higher CPU allowance or a different free compute host.

The PDF export path imports ReportLab lazily. ReportLab is not included in the standard Python Worker package set used here, so PDF export is not considered supported on this target until separately verified. Do not assume every existing backend route is production-ready on Workers.

## One-time setup

### 1. Create a disposable PostgreSQL database

Create a project on [Neon](https://console.neon.tech/) using its Free plan. Create/use a dedicated test database and copy its direct PostgreSQL connection string (not a production database URL).

Do not put the database URL in Git, a source file, or this chat.

### 2. Create a Cloudflare Hyperdrive configuration

In a terminal with Wrangler authenticated to your Cloudflare account, create Hyperdrive using the Neon test connection string:

```bash
npx wrangler@4 hyperdrive create dina-api-free-test --connection-string="$DINA_TEST_DATABASE_URL"
```

Save the returned Hyperdrive ID. Hyperdrive must point to the same test database whose direct URL will be used for migrations.

### 3. Create a Cloudflare API token

Create a token scoped to the target Cloudflare account with permission to deploy/edit Workers scripts. Do not use a Global API Key. Keep the token private.

### 4. Add GitHub Actions variables and secrets

In GitHub, open **Settings → Secrets and variables → Actions** for this repository.

Add these **repository variables**:

| Variable | Value |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `DINA_TEST_HYPERDRIVE_ID` | Hyperdrive ID returned in step 2 |

Add these **repository secrets**:

| Secret | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token from step 3 |
| `DINA_TEST_DATABASE_URL` | Direct Neon test database URL from step 1 |
| `DINA_WORKER_SECRET_KEY` | A new random secret of at least 32 characters, used only by this test Worker |
| `DINA_PAYMENT_WEBHOOK_SECRET` | Optional; only needed to test payment webhook signature validation |

Generate the Worker signing secret locally with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never reuse the production `SECRET_KEY`.

### 5. Deploy from the feature branch

The repository includes a deployment workflow:
`.github/workflows/deploy-cloudflare-test.yml`.

After all variables and secrets above are configured, push a commit to `cloudflare-free-test`. The workflow automatically deploys from this branch only.

The workflow:
- refuses to run from any branch other than `cloudflare-free-test`;
- applies the existing SQL migration files to the dedicated test database;
- injects the Hyperdrive ID into the deployment config without committing it;
- uploads the test-only Worker secrets;
- deploys the Python Worker.

The workflow is not enabled on `main` and never deploys production. Each push to this isolated test branch redeploys the test Worker.

### 6. Verify and connect the Android app

Use the `workers.dev` URL printed by Wrangler in the deployment logs. Test:

- `/health` — Worker responds.
- `/health/ready` — Worker can reach the test PostgreSQL database.
- Then build the Android app with the deployed URL:

```bash
cd app
flutter build apk --debug --dart-define=API_BASE_URL=https://YOUR-WORKER-HOST.workers.dev
```

Replace the example host with the exact URL printed by Wrangler. The app already appends `/api/v1` to the configured base URL.

## Local Worker preview

The `localConnectionString` in `wrangler.jsonc` is a local-only dummy DSN. Run a local PostgreSQL instance and apply migrations before:

```bash
uv sync --group dev
uv run pywrangler dev
```

Set a local `SECRET_KEY` through Wrangler's local secrets mechanism before using protected endpoints.

## CI validation versus live deployment

The `Cloudflare Workers Free compatibility` CI job runs `pywrangler deploy --dry-run`. This validates dependency packaging and Worker bundling without publishing anything. A successful dry-run is not a live deployment and does not prove that the configured external PostgreSQL provider, Hyperdrive connection, or Free CPU budget will work for every API route.

The live deployment workflow only runs after the GitHub variables and secrets above have been configured.
