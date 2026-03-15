import io
import os
import zipfile
from typing import List, Tuple
from app.core.logging_config import logger

def extract_zip_files(zip_bytes: bytes) -> List[Tuple[str, bytes]]:
    """
    Extract files from a ZIP archive.
    Returns list of (filename, file_bytes) tuples.
    """
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                # Skip directories and hidden files
                if name.endswith("/") or name.startswith("__MACOSX") or name.startswith("."):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in (".pdf", ".png", ".jpg", ".jpeg"):
                    results.append((os.path.basename(name), zf.read(name)))
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
    return results
