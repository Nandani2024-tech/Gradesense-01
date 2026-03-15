import asyncio
from app.core.logging_config import logger
from app.services.background import run_background_worker

# Global reference to the background worker task
_worker_task = None

def start_background_worker():
    """Start the integrated background task worker"""
    global _worker_task
    logger.info("🔄 Starting integrated background task worker...")
    _worker_task = asyncio.create_task(run_background_worker())
    logger.info("🔄 Background worker started")
    return _worker_task

async def stop_background_worker():
    """Stop the background task worker"""
    global _worker_task
    if _worker_task and not _worker_task.done():
        logger.info("⏹️ Stopping background task worker...")
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            logger.info("✅ Background task worker stopped cleanly")
