# pgbhub (Python SDK & CLI)

Official Python client SDK and CLI for **PGBHub Cloud**. Compatible with FastAPI, Pydantic, SQLAlchemy, and Psycopg 3.

## Installation

```bash
pip install pgbhub
```

## Developer Paradigms

### 1. Typed Table Models (ORM / Query Paradigm)

```python
from pgbhub import PGBHubClient

# project_id alone targets https://my-project.pgbhub.app. The key picks the
# database; pass database= only to name one explicitly.
client = PGBHubClient(api_key="your_api_key", project_id="my-project")

# Access tables directly as model clients
User = client.user

# Query records
profiles = User.find(filter={"id": "8ef5-492a-bb81"})

# Find single unique record
user = User.find_one(filter={"email": "alex@example.com"})

# Create / insert
new_user = User.create(data={
    "email": "alex@example.com",
    "name": "Alex",
    "preferences": {"theme": "dark"}
})

# Update & delete
User.update(filter={"id": "8ef5-492a-bb81"}, data={"name": "Alexander"})
User.delete(filter={"id": "8ef5-492a-bb81"})
```

### 2. Async Client for FastAPI

```python
from fastapi import FastAPI
from pgbhub import AsyncPGBHubClient

app = FastAPI()
client = AsyncPGBHubClient(api_key="...")

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    return await client.user.find_one(filter={"id": user_id})

@app.post("/orders/{order_id}/approve")
async def approve(order_id: str):
    return await client.actions.approve_order(params={"orderId": order_id})
```

---

## Configuration

Everything can come from the environment, so the same code runs anywhere:

| Setting | Argument | Environment variable |
|---|---|---|
| Key | `api_key` | `PGBHUB_API_KEY` (or `PGBHUB_PUBLISHABLE_KEY`) |
| Project | `project_id` | `PGBHUB_PROJECT_ID` |
| Address | `endpoint` | `PGBHUB_ENDPOINT` or `PGBHUB_PROJECT_URL` (default: the project address, else `https://console.pgbhub.com`) |
| Domain | | `PGBHUB_PROJECT_DOMAIN` (default `pgbhub.app`) |
| Database | `database` | `PGBHUB_DATABASE` (sent only when set) |
| Timeout / retries | `timeout=30`, `max_retries=2`, `retry_delay=0.3` | |

Reads (GET) retry on 502/503/504 and connection errors. Writes never retry.

## Errors

Every failure raises `PGBHubError` (also exported as `PGBHubAuthError`) with the server's own message plus `status_code`, `code`, `body` and, for rate limits, `retry_after` seconds:

```python
from pgbhub import PGBHubError

try:
    client.auth.sign_in("a@example.com", "wrong")
except PGBHubError as e:
    print(e.status_code, e.code, e.message, e.retry_after)
```

## Auth

```python
auth = client.auth

result = auth.sign_up("a@example.com", "a-long-password", redirect_to="https://app.example.com/welcome")
if result.get("verification_required"):
    ...  # no session yet: the user must click the emailed link

login = auth.sign_in("a@example.com", "a-long-password")
if login.get("mfa_required"):
    auth.verify_mfa(login["challenge_token"], "123456")

auth.forgot_password("a@example.com", redirect_to="https://app.example.com/reset")
auth.reset_password(token_from_the_link, "a-new-long-password")

auth.request_otp("a@example.com");  auth.verify_otp("a@example.com", "123456")
auth.send_magic_link("a@example.com"); auth.verify_magic_link(token)

auth.change_password("new-password", current_password="old-password")
auth.update_user({"plan": "pro"}); auth.get_events(); auth.list_sessions()
auth.revoke_other_sessions(); auth.delete_account(password="...")

auth.oauth_start("google", "https://app.example.com/callback")  # -> authorize_url, state
auth.get_settings()  # which methods are on, password policy, providers
```

One-time codes and links are only ever emailed; the API never returns them. `redirect_to` must be allowed in the project's auth settings. `AsyncPGBHubClient().auth` has the same methods, awaitable.

## Mail

```python
from pgbhub import PGBHubError, MAIL_PROVIDER_UNAVAILABLE

try:
    sent = client.mail.send(
        "alex@example.com",
        "Your receipt",
        "Thanks for your order.",
        html="<p>Thanks for your order.</p>",
        reply_to="support@acme.dev",  # optional: one address for the Reply-To header
    )
    print(sent["message_id"])
except PGBHubError as e:
    if e.code == MAIL_PROVIDER_UNAVAILABLE:  # 503: no mail provider configured right now
        ...
```

Sending needs the project's **secret key**. `reply_to` is a single address: line breaks, commas and semicolons are refused with a 400. `message_id` identifies the sent message (on an older server it is filled from `mail_id`). `from_addr` sets the sender. `AsyncPGBHubClient().mail.send(...)` is the same, awaitable.

## Storage: private buckets and signed URLs

Buckets are **public** by default. A **private** bucket's objects are readable only with the project's
**secret** key (`pgb_sec_...`), by project members in the console, or through a signed URL. Publishable keys
(`pgb_pub_...`) never read private objects, and a private object's public URL (`/storage/<bucket>/<path>`)
answers 404 to anyone without the secret key: hand out a signed URL instead.

These calls need the secret key, so make them on a server:

```python
client = PGBHubClient(project_id="my-project", api_key=os.environ["PGB_SECRET_KEY"])

client.storage.create_bucket("receipts", visibility="private")  # visibility defaults to "public"

# A 15-minute download link for one object (at most 24 hours for GET).
link = client.storage.create_signed_url("receipts", "2026/inv-1.pdf", expires_in=900)
print(link["url"], link["expires_at"])

# An upload link (at most 1 hour). With content_type, the upload must use exactly that type.
put = client.storage.create_signed_url("receipts", "2026/inv-2.pdf", method="PUT", content_type="application/pdf")
client.storage.upload_to_signed_url(put["url"], pdf_bytes, "application/pdf")  # no API key: the URL is the credential

client.storage.set_bucket_visibility("receipts", "private")
client.storage.set_bucket_visibility("assets", "public", confirm_public=True)  # ValueError without confirm_public
```

- `create_signed_url` calls `POST /storage/sign` on the project's address (`project_id=...` or a
  `https://<slug>.pgbhub.app` endpoint). `create_bucket` and `set_bucket_visibility` address the project by
  `project_id`, or by the slug in that endpoint.
- Anyone holding a signed URL can use it until it expires. A GET URL also answers HEAD.
- Without a bound `content_type`, a signed PUT refuses HTML, SVG, XML and JavaScript (415).
- Making a bucket private takes effect within seconds, but copies a browser or the CDN already fetched are not
  recalled.
- `AsyncPGBHubClient().storage` has the same methods, awaitable.

## Actions

```python
client.actions.save_user({"email": "a@example.com"})            # run
client.actions.save_user({"email": "a@example.com"}, dry_run=True)  # preview, including effects_preview

client.actions.register(
    name="signup",
    sql="INSERT INTO users (email) VALUES (%(email)s) RETURNING id",
    effects=[
        {"type": "mail", "to": "{{params.email}}", "subject": "Welcome", "body": "Hi!"},
        {"type": "queue", "queue": "onboarding", "payload": {"user": "{{results.0.id}}"}},
    ],
)
client.actions.list(); client.actions.get("signup"); client.actions.delete("signup")
client.actions.deliveries(status="failed"); client.actions.retry_delivery(12)
client.actions.run(name_in_a_variable, {"x": 1})
```

Effects run after the SQL commits, retry on their own, and can target a function, queue, mail, event, job, realtime channel, container, another action, or a webhook.

## Local vs. Cloud

The same code runs against local PostgreSQL-backed PGBHub and PGBHub Cloud; switch with the environment only (`PGBHUB_ENDPOINT`, `PGBHUB_API_KEY`).

---

## Deterministic Pydantic Model Generation (Zero AI Tokens)

Run the CLI in your project to pull the live schema from your local or cloud database and deterministically generate Pydantic v2 models without spending a single AI token:

```bash
pgbhub pull --db my_database --out models.py
```

---

## Comprehensive Developer & AI Agent Guide

For detailed documentation, architectural diagrams, LLM agent tool definitions, and copy-pastable recipes, see the **[PGBHub Master Developer & AI Agent Guide](file:///Users/alveis/Projects/Hydratik/pgbhub/PGB_DEVELOPER_GUIDE.md)**.

---

## License

MIT © [Hydratik](https://github.com/Hydratik)

