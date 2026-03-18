from typing import Optional, List, Any, Tuple
from bson import ObjectId
from app.infrastructure.storage.gridfs_storage import fs

class FileRepo:
    def __init__(self):
        self.fs = fs

    def put(self, data: bytes, **kwargs) -> str:
        """Store file in GridFS."""
        return str(self.fs.put(data, **kwargs))

    def get(self, file_id: str) -> Optional[bytes]:
        """Retrieve file from GridFS."""
        try:
            oid = ObjectId(file_id)
            if self.fs.exists(oid):
                return self.fs.get(oid).read()
            return None
        except Exception:
            return None

    def exists(self, file_id: str) -> bool:
        """Check if file exists in GridFS."""
        try:
            return self.fs.exists(ObjectId(file_id))
        except Exception:
            return False

    def delete(self, file_id: str) -> None:
        """Delete file from GridFS."""
        try:
            self.fs.delete(ObjectId(file_id))
        except Exception:
            pass

    def find(self, query: dict) -> Any:
        """Find files in GridFS."""
        return self.fs.find(query)
