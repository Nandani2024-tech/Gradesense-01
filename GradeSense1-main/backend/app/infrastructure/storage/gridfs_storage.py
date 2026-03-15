from pymongo import MongoClient
from gridfs import GridFS
from app.core.db_config import MONGO_URL, DB_NAME

if not MONGO_URL:
    raise RuntimeError("MONGO_URL environment variable is not set")

# Sync client (used by GridFS - Motor doesn't have async GridFS)
sync_client = MongoClient(MONGO_URL)
sync_db = sync_client[DB_NAME]
fs = GridFS(sync_db)
