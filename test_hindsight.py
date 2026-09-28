import os

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

url = os.getenv("HINDSIGHT_URL")
api_key = os.getenv("HINDSIGHT_API_KEY")
bank_id = os.getenv("HINDSIGHT_BANK_ID")

if not url or not api_key or not bank_id:
    raise RuntimeError("Missing Hindsight configuration in .env")

client = Hindsight(
    base_url=url,
    api_key=api_key,
)

try:
    client.retain(
        bank_id=bank_id,
        content=(
            "A payment service outage returned HTTP 503 because the database "
            "connection pool was exhausted. The fix was to increase the pool "
            "limit, restart affected workers, and verify active connections."
        ),
    )

    result = client.recall(
        bank_id=bank_id,
        query="Have we seen a payment service 503 caused by database connection limits?",
    )

    print("Hindsight connection succeeded.")
    print("Recall results:")

    for memory in result.results:
        print("-", memory.text)
finally:
    client.close()