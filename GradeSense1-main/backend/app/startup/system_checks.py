import os
import shutil
import subprocess
from app.core.logging_config import logger

def verify_system_dependencies():
    """Verify system-level dependencies required for the API"""
    logger.info("🔍 Checking system dependencies...")
    if not shutil.which("pdftoppm"):
        if os.name != 'nt':  # Only relevant for Linux, usually already in path for Windows
            logger.warning("⚠️ poppler-utils not found. Please install pdftoppm for PDF support.")
        else:
            logger.warning("⚠️ poppler-utils (pdftoppm) not found in PATH. Please install Poppler for Windows.")
    else:
        logger.info("✅ poppler-utils is already installed")
