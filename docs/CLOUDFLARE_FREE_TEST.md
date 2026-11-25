# Dina on Cloudflare Workers Free (test branch)

This deployment target is isolated to the `cloudflare-free-test` branch. It does not change the production `main` branch or its hosting configuration.

## What runs where

- The existing FastAPI application in `backend/src/main.py` runs on Cloudflare Python Workers through its ASGI adapter.
- PostgreSQL remains PostgreSQL. Create a separate **test database** with a provider that accepts remote connections, then connect it through a Cloudflare Hyperdrive binding.
- Cloudflare Workers Free is the compute target. Hyperdrive is used for connection pooling; it does not move PostgreSQL data into Cloudflare.
- The Flutter app can use the deployed Worker URL as `API_BASE_URL`.

## Free-plan constraints that affect Dina

Cloudflare Workers Free currently allows 100,000 requests/day but only **10 ms CPU time per request** and 128 MB memory. Database/network wait time does not count as CPU time.

Dina's existing password policy uses Argon2id with 64 MiB memory, time cost 3 and parallelism 4. Registration/login and password verification are CPU-intensive and are expected to exceed the Free CPU budget. Do not weaken the password policy just to make these requests fit. Consequently this free deployment is suitable first for health checks and light API-path compatibility tests; full authentication and full-app acceptance testing are not guaranteed on Free.

The PDF export path imports ReportLab lazily. ReportLab is not included in the standard Pyodide package set used by this Worker, so PDF export must be treated as unsupported until a compatible PyEmscripten build or a separate export service is provided. CSV and XLSX paths are separate.

## One-time setup

Requirements: a Cloudflare account on the Free Workers plan, Node.js/npm, uv, Wrangler/Pywrangler, and a **dedicated disposable PostgreSQL test database**. Never connect this test Worker to production data.

1. Create a PostgreSQL database/schema for testing and apply every migration in order:

   ```bash
   for f in database/migrations/*.sql; do
     psql "$DINA_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
   done
   ```

2. Create the Hyperdrive configuration (use the test database URL, not production):

   ```bash
   npx wrangler hyperdrive create dina-test --connection-string="$DINA_TEST_DATABASE_URL"
   ```

3. Replace the placeholder `hyperdrive[0].id` in `wrangler.jsonc` with the returned ID.

4. Set a new random production-format signing secret in the Worker secret store:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   npx wrangler secret put SECRET_KEY
   # Optional: only if payment webhooks are part of this test
   npx wrangler secret put PAYMENT_WEBHOOK_SECRET
   ```

5. Install and deploy from the repository root:

   ```bash
   uv sync --group dev
   uv run pywrangler deploy
   ```

6. Test the returned `https://dina-api-free-test.<account>.workers.dev/health` and `/health/ready` endpoints. The latter confirms the test database connection.

7. Build the Android app against the deployed URL:

   ```bash
   cd app
   flutter build apk --debug --dart-define=API_BASE_URL=https://dina-api-free-test.<account>.workers.dev
   ```

## Local Worker preview

The `localConnectionString` in `wrangler.jsonc` is a local-only dummy DSN. Run a local PostgreSQL instance and apply migrations before:

```bash
uv sync --group dev
uv run pywrangler dev
```

Set a local `SECRET_KEY` through Wrangler's local secrets mechanism before using protected endpoints. The Cloudflare production secret is not copied into the repository.

## CI validation

The `Cloudflare Workers Free compatibility` job runs `pywrangler deploy --dry-run`. This validates dependency packaging and Worker bundling without deploying or requiring Cloudflare credentials. A successful dry-run is not a live deployment and does not prove that the external PostgreSQL provider, Hyperdrive configuration, or Free CPU budget will work for every API route.
