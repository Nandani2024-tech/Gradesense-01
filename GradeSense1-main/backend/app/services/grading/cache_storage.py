import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from app.repositories import GradingRepo
from app.core.logging_config import logger
from app.models.submission import QuestionScore
from .constants import GRADING_CACHE_VERSION, DISABLE_GRADING_CACHE

# In-memory grading cache
grading_repo = GradingRepo()
grading_cache = {}
grading_cache_meta = {}

async def get_cached_grading(paper_hash: str, skip_cache: bool = False) -> Optional[Tuple[List[QuestionScore], Dict[str, Any]]]:
    """Retrieve grading results from memory or database cache."""
    if skip_cache or DISABLE_GRADING_CACHE:
        return None

    # Check memory cache
    if paper_hash in grading_cache:
        logger.info(f"Cache hit (memory) for paper {paper_hash}")
        cached_meta = grading_cache_meta.get(paper_hash, {}) or {}
        return grading_cache[paper_hash], cached_meta

    # Check database cache
    try:
        cached_result = await grading_repo.find_one_grading_result({"paper_hash": paper_hash})
        if cached_result and "results" in cached_result:
            logger.info(f"Cache hit (db) for paper {paper_hash}")
            results_data = json.loads(cached_result["results"])
            cached_meta = cached_result.get("mapping_meta", {}) or {}
            
            # Map back to QuestionScore objects
            scores = [QuestionScore(**s) for s in results_data]
            
            # Populate memory cache
            grading_cache[paper_hash] = scores
            grading_cache_meta[paper_hash] = cached_meta
            
            return scores, cached_meta
    except Exception as e:
        logger.error(f"Error checking grading cache: {e}")
        
    return None

async def save_grading_to_cache(paper_hash: str, scores: List[QuestionScore], packet_meta: Dict[str, Any]):
    """Save grading results to memory and database cache."""
    if DISABLE_GRADING_CACHE:
        return

    try:
        # Update memory cache
        grading_cache[paper_hash] = scores
        grading_cache_meta[paper_hash] = packet_meta
        
        # Update database cache
        results_json = json.dumps([s.model_dump() for s in scores])
        await grading_repo.update_grading_result(
            {"paper_hash": paper_hash},
            {"$set": {
                "paper_hash": paper_hash,
                "results": results_json,
                "mapping_meta": packet_meta,
                "version": GRADING_CACHE_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error saving grading cache: {e}")

def clear_memory_cache():
    """Clear the in-memory grading cache."""
    grading_cache.clear()
    grading_cache_meta.clear()
