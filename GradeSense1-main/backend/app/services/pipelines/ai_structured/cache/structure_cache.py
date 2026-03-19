from typing import Any, Dict, Optional
from app.infrastructure.cache import get_structure_cache, set_structure_cache
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger

logger = pipeline_logger(__name__)

@with_logging
def get_cached_structure(exam_id: str, blueprint_version: int, extraction_hash_seed: str) -> Optional[Dict[str, Any]]:
    return get_structure_cache(exam_id, blueprint_version, extraction_hash_seed)

@with_logging
def set_cached_structure(exam_id: str, blueprint_version: int, extraction_hash_seed: str, data: Dict[str, Any]) -> None:
    set_structure_cache(exam_id, blueprint_version, extraction_hash_seed, data)
