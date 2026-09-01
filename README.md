# pgbox (Python SDK & CLI)

Official Python client SDK and CLI for **PGBox Cloud**. Compatible with FastAPI, Pydantic, SQLAlchemy, and Psycopg 3.

## Installation

```bash
pip install pgbox
```

## Developer Paradigms

### 1. Typed Table Models (ORM / Query Paradigm)

```python
from pgbox import PGBoxClient

client = PGBoxClient(
    api_key="your_api_key",
    endpoint="https://cloud.pgboxhub.com",
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
from pgbox import AsyncPGBoxClient

app = FastAPI()
client = AsyncPGBoxClient(api_key="...")

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    return await client.user.find_one(filter={"id": user_id})

@app.post("/orders/{order_id}/approve")
async def approve(order_id: str):
    return await client.actions.approve_order(params={"orderId": order_id})
```

---

## Pydantic Model Generation (`pgbox pull`)

```bash
pgbox pull --db my_database --out models.py
```

---

## License

MIT © [Hydratik](https://github.com/Hydratik)

