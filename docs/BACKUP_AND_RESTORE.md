# PostgreSQL backup and restore runbook

## Automated backup

The `Dina PostgreSQL backup` workflow runs daily at 02:17 UTC and can also
be started manually. It creates a PostgreSQL custom-format dump, checks that
`pg_restore --list` can read the archive, calculates a SHA-256 checksum, and
uploads both files to S3 with server-side AES-256 encryption.

Configure these GitHub repository secrets:

- `BACKUP_DATABASE_URL`: production PostgreSQL connection string, with the
  least-privileged role that can dump the required Dina database.
- `BACKUP_S3_BUCKET`: destination bucket name, without the `s3://` prefix.
- `BACKUP_AWS_ACCESS_KEY_ID`: credentials limited to writing the backup prefix.
- `BACKUP_AWS_SECRET_ACCESS_KEY`: matching secret key.

Configure the repository variable `BACKUP_AWS_REGION` to the bucket's AWS
region. Do not put credentials or database URLs in repository files, workflow
arguments, or logs.

Configure an S3 lifecycle policy for `dina/postgresql/` to expire old backups
according to the organization's retention policy. Enable bucket versioning and
block public access. The workflow deliberately fails if any required setting is
missing; a skipped or empty backup must not look successful.

## Restore drill

A successful `pg_restore --list` checks archive readability, not recoverability.
Run a restore drill regularly against a separate, disposable PostgreSQL database:

1. Download a selected `dina/postgresql/<backup-name>.dump` and its matching
   `.sha256` file from the private bucket.
2. Verify the checksum with `sha256sum -c <backup-name>.dump.sha256` after
   ensuring the checksum file's filename matches the local dump name.
3. Create a clean, isolated test database. Never use the production connection
   string for a restore drill.
4. Restore using `pg_restore --exit-on-error --no-owner --no-acl --dbname="$RESTORE_TEST_DATABASE_URL" <backup-name>.dump`.
5. Apply read-only validation queries: check migration/schema presence, row
   counts for organizations, memberships, accounts, journal entries, payment
   attempts and subscriptions, and confirm the restored application can start
   against the test database.
6. Record the restore duration and the newest recoverable backup. Investigate
   any missing tables, failed rows or unexpected counts before considering the
   backup process healthy.

The backup workflow does not automatically restore into a database. This is
intentional: a scheduled job must never overwrite a live database as a side
effect of testing its own backup.
