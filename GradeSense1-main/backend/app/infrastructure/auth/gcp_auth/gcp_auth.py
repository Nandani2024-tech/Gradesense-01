"""Main GCP authentication configuration."""

import os
import logging
from .config_helper import resolve_gcp_path, get_env_var

logger = logging.getLogger("gradesense")

def configure_gcp_credentials(service_name: str = "Vision API"):
    """
    Configure Google Cloud authentication for a specific service.
    
    Args:
        service_name: Name of the service being configured (for logging).
    """
    # Main environment variable for GCP authentication
    gcp_credentials_path = get_env_var("GOOGLE_APPLICATION_CREDENTIALS")
    
    if gcp_credentials_path:
        absolute_path = resolve_gcp_path(gcp_credentials_path)
        
        # Ensure environment variable is set to absolute path
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(absolute_path)
        logger.info(f"✅ GCP credentials for {service_name} configured at: {absolute_path}")
    else:
        logger.warning(f"⚠️ GOOGLE_APPLICATION_CREDENTIALS not set - {service_name} may fail")
