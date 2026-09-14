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

client = PGBHubClient(
    api_key="your_api_key",
    endpoint="https://cloud.pgbhub.com",
    database="my_database"
)

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

## Local vs. Cloud: Seamless Switching

The exact same `pgbhub` client code works identically against **local PostgreSQL** (Docker / offline) and **PGBHub Cloud**:

```python
import os
from pgbhub import PGBHubClient

# 1-env switch:
# Local:      DATABASE_URL="postgresql://postgres:postgres@localhost:5432/myapp"
# Production: PGBHUB_ENDPOINT="https://console.pgbhub.com" PGBHUB_API_KEY="pgb_live_..."
client = PGBHubClient(
    endpoint=os.getenv("PGBHUB_ENDPOINT"),
    api_key=os.getenv("PGBHUB_API_KEY"),
    db_url=os.getenv("DATABASE_URL"),
    database="myapp"
)
```

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

