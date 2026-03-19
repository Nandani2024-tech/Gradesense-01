import os
import json
import threading
from typing import Any, Dict
from contextvars import ContextVar

# Context-scoped job ID to avoid passing it through 15 method signatures
current_job_id: ContextVar[str] = ContextVar("current_job_id", default="")

# Thread-safe in-memory aggregators for parallel LLM grading
_grading_inputs: Dict[str, Dict[str, Any]] = {}
_llm_raw_responses: Dict[str, Dict[str, Any]] = {}

_lock = threading.Lock()

def _get_folder() -> str:
    job_id = current_job_id.get()
    if not job_id:
        return ""
    folder = os.path.join("debug", str(job_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def write_debug_json(filename: str, data: Any) -> None:
    """Safely writes a JSON file for the current job."""
    try:
        folder = _get_folder()
        if not folder:
            return
        
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        # DO NOT CRASH PIPELINE ON DEBUG LOG FAILURE
        pass

def write_debug_txt(filename: str, text: str) -> None:
    """Safely writes a text file for the current job."""
    try:
        folder = _get_folder()
        if not folder:
            return
            
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(text))
    except Exception:
        pass

def add_grading_input(question_id: str, payload: Any) -> None:
    """Accumulates grading input parameters before flushing."""
    if not current_job_id.get():
        return
    with _lock:
        job_inputs = _grading_inputs.setdefault(current_job_id.get(), {})
        job_inputs[str(question_id)] = payload

def add_llm_response(question_id: str, payload: Any) -> None:
    """Accumulates raw LLM responses before flushing."""
    if not current_job_id.get():
        return
    with _lock:
        job_resps = _llm_raw_responses.setdefault(current_job_id.get(), {})
        job_resps[str(question_id)] = payload

def flush_grading_inputs() -> None:
    """Writes all accumulated grading inputs (Stage 6) to disk and clears memory."""
    job_id = current_job_id.get()
    if not job_id:
        return
        
    with _lock:
        data = _grading_inputs.pop(job_id, {})
    
    if data:
        write_debug_json("06_grading_inputs.json", data)

def flush_llm_responses() -> int:
    """Writes all accumulated LLM responses (Stage 7) to disk and clears memory. Returns count."""
    job_id = current_job_id.get()
    if not job_id:
        return 0
        
    with _lock:
        data = _llm_raw_responses.pop(job_id, {})
    
    if data:
        write_debug_json("07_llm_raw.json", data)
        return len(data)
    return 0
