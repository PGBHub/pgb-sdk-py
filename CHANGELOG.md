# Changelog

## 1.1.0

**Fixes (these affect existing apps)**
- A project id alone now targets `https://<project>.pgbhub.app`; the default was the shared cloud address, and docs pointed at `console.pgbhub.com`. Override with `PGBHUB_PROJECT_DOMAIN`.
- A database name is only sent when you configure one. Project keys cannot use the default `postgres` name.
- Data calls (`client.table(...)`, `request()`) raise `PGBHubError` with the server's message instead of a bare `httpx.HTTPStatusError`.
- `get_user()` returns `None` only for a signed-out or expired session; other failures raise.
- The README example used a `db_url` argument that does not exist; removed.

**New**
- `PGBHubError` (`PGBHubAuthError` is the same class) with `status_code`, `code`, `body`, `retry_after`.
- `timeout`, `max_retries`, `retry_delay`; reads retry transient failures, writes never do.
- Auth: `get_settings`, `forgot_password`, `reset_password`, `resend_verification`, `change_password`, `update_user`, `delete_account`, `get_events`, `list_sessions`, `revoke_session`, `revoke_other_sessions`, `enroll_mfa`, `confirm_mfa`, `disable_mfa`, `verify_mfa`, `oauth_start`, `oauth_callback`; `redirect_to` on sign-up, magic link, reset and resend. Sync and async.
- Actions: effects, `effects_queued` / `effects_preview` on responses, and `register` / `list` / `get` / `delete` / `run` / `deliveries` / `retry_delivery` (sync and async).
- CLI: `--endpoint` and `--db` default to the environment / key.
