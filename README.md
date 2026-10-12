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
| Address | `endpoint` | `PGBHUB_ENDPOINT` or `PGBHUB_PROJECT_URL` (default: the project address, else `https://cloud.pgbhub.com`) |
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

