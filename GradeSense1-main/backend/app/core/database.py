from motor.motor_asyncio import AsyncIOMotorClient
from app.core.db_config import MONGO_URL, DB_NAME

if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is not set")

# Async client (used by all app queries)
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
