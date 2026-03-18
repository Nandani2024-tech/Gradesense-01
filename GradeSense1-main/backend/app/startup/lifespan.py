from fastapi import FastAPI
from app.core.logging_config import logger, initialize_logging
from app.infrastructure.auth.gcp_auth import configure_gcp_credentials
from app.startup.system_checks import verify_system_dependencies
from app.startup.job_cleanup import cleanup_orphaned_grading_jobs
from app.startup.worker_manager import start_background_worker, stop_background_worker

async def lifespan(app: FastAPI):
    """Application lifespan manager - starts/stops background worker and checks dependencies"""
    # Startup: Initialize logging and credentials
    initialize_logging()
    configure_gcp_credentials()
    
    logger.info("🚀 FastAPI app starting up...")
    logger.info("PIPELINE_CUTOVER_ACTIVE")
    
    # Only log route counts to avoid terminal scrambling
    route_count = len(app.routes)
    logger.info(f"REGISTERED ROUTES COUNT: {route_count}")
    
    verify_system_dependencies()
    await cleanup_orphaned_grading_jobs()
    start_background_worker()
    
    logger.info("=" * 60)

    yield

    # Shutdown: Cancel the background worker
    logger.info("🛑 FastAPI app shutting down...")
    await stop_background_worker()
