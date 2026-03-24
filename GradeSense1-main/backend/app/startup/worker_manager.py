import asyncio
from app.core.logging_config import logger
from app.services.background import run_background_worker
from app.workers.grading_worker import grading_worker_loop

# Global reference to the background worker tasks
_worker_task = None
_grading_worker_task = None

def start_background_worker():
    """Start the integrated background task worker and grading worker"""
    global _worker_task, _grading_worker_task
    logger.info("🔄 Starting integrated background task worker...")
    _worker_task = asyncio.create_task(run_background_worker())
    
    logger.info("🔄 Starting grading worker queue consumer...")
    _grading_worker_task = asyncio.create_task(grading_worker_loop())
    
    logger.info("🔄 Background workers started")
    return _worker_task

async def stop_background_worker():
    """Stop the background task workers"""
    global _worker_task, _grading_worker_task
    
    if _grading_worker_task and not _grading_worker_task.done():
        logger.info("⏹️ Stopping grading worker task...")
        _grading_worker_task.cancel()
        try:
            await _grading_worker_task
        except asyncio.CancelledError:
            logger.info("✅ Grading worker task stopped")

    if _worker_task and not _worker_task.done():
        logger.info("⏹️ Stopping background task worker...")
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            logger.info("✅ Background task worker stopped cleanly")
