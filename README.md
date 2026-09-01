# pgbox (Python SDK & CLI)

Official Python client SDK and CLI for **PGBox Cloud**. Compatible with FastAPI, Pydantic, SQLAlchemy, and Psycopg 3.

## Installation

```bash
pip install pgbox
```

## Quick Start

```python
from pgbox import PGBoxClient

client = PGBoxClient(
    api_key="your_api_key",
    endpoint="https://cloud.pgboxhub.com",
    database="my_database"
)

# Invoke dynamic actions
res = client.actions.approve_order(
    params={"orderId": "ord_102", "userId": "usr_99"},
    dry_run=False
)

print(res.status, res.duration_ms, res.results)
```

## Async Client for FastAPI

```python
from pgbox import AsyncPGBoxClient

async_client = AsyncPGBoxClient(api_key="...")

@app.post("/orders/{order_id}/approve")
async def approve(order_id: str):
    return await async_client.actions.approve_order(params={"orderId": order_id})
```

## Pydantic Model Generation (`pgbox pull`)

```bash
pgbox pull --db my_database --out models.py
```

## License

MIT © [Hydratik](https://github.com/Hydratik)
