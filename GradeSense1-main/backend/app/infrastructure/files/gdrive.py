import re
import requests
from typing import Optional
from app.core.logging_config import logger

def extract_file_id_from_url(url: str) -> Optional[str]:
    """Extract Google Drive file ID from various URL formats."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def download_from_google_drive(file_id: str) -> Optional[bytes]:
    """Download a file from Google Drive using its file ID."""
    try:
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        session = requests.Session()
        response = session.get(url, stream=True, timeout=60)

        # Handle large file confirmation page
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                url = f"https://drive.google.com/uc?export=download&confirm={value}&id={file_id}"
                response = session.get(url, stream=True, timeout=60)
                break

        if response.status_code == 200:
            content = response.content
            if len(content) > 0:
                return content
        logger.error(f"Google Drive download failed: status {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error downloading from Google Drive: {e}")
        return None
