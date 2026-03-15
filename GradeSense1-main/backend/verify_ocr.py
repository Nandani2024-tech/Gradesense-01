
import asyncio
from app.utils.ocr_services import get_ocr_service, get_paddle_service, get_gemini_ocr_service
from app.utils.paddle_service import get_paddle_service as get_legacy_paddle_service

async def test_minimal():
    print("Testing OCR Modularization...")
    
    # Test 1: Singleton Factory
    service1 = get_ocr_service("paddle")
    service2 = get_paddle_service()
    print(f"Paddle service singleton: {service1 is service2}")
    
    # Test 2: Legacy Wrapper
    legacy_service = get_legacy_paddle_service()
    print(f"Legacy wrapper available: {legacy_service.is_available()}")
    
    # Test 3: Gemini service (lazy availability)
    gemini_service = get_gemini_ocr_service()
    print(f"Gemini service identified: {gemini_service._model_name}")
    print(f"Gemini service available: {gemini_service.is_available()}")

    # Test 4: Result Normalization
    from app.utils.ocr_services.legacy_compat import normalize_ocr_result
    raw_lines = [{"text": "Hello World", "x1": 0, "y1": 0, "x2": 100, "y2": 10}]
    norm = normalize_ocr_result(raw_lines, provider="test")
    print(f"Normalization words count: {len(norm['words'])}")
    print(f"Normalization line_id: {norm['lines'][0]['line_id']}")
    
    # Test 5: Config
    from app.utils.ocr_services.config import PADDLE_LANG
    print(f"Config PADDLE_LANG: {PADDLE_LANG}")

    print("Verification complete!")

if __name__ == "__main__":
    asyncio.run(test_minimal())
