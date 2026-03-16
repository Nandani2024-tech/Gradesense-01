
try:
    from app.adapters.llm.college_prompts import COLLEGE_SYSTEM_PROMPT
    print("Import COLLEGE_SYSTEM_PROMPT success")
except Exception as e:
    print(f"Import COLLEGE_SYSTEM_PROMPT failed: {e}")

try:
    from app.adapters.llm.upsc_prompts import UPSC_SYSTEM_PROMPT, GS4_SYSTEM_PROMPT, get_upsc_system_prompt
    print("Import UPSC prompts success")
except Exception as e:
    print(f"Import UPSC prompts failed: {e}")

try:
    from app.adapters.llm.college_v3_adapter import build_cbse_prompt, parse_grade_response
    print("Import college_v3_adapter success")
except Exception as e:
    print(f"Import college_v3_adapter failed: {e}")

try:
    from app.services.pipelines.grading_resolver import resolve_grading_layer
    print("Import grading_resolver success")
except Exception as e:
    print(f"Import grading_resolver failed: {e}")

try:
    from app.layers.college import COLLEGE_SYSTEM_PROMPT
    print("Import from app.layers.college success")
except Exception as e:
    print(f"Import from app.layers.college failed: {e}")

try:
    from app.layers.upsc import UPSC_SYSTEM_PROMPT
    print("Import from app.layers.upsc success")
except Exception as e:
    print(f"Import from app.layers.upsc failed: {e}")

print("Verification complete.")
