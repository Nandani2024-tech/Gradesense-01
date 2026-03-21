# File: test_run_ai_pipeline.py
# Place this in your backend folder and run: python test_run_ai_pipeline.py

import asyncio
import logging

# Import your Phase 3 function
from app.services.pipelines.ai_structured.engine import run_ai_pipeline

# Optional: Configure logging to print to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Test inputs
    exam_id = "test_exam_001"
    submission_id = "test_submission_001"

    try:
        logger.info(f"🚀 Starting Phase 3 pipeline test: exam_id={exam_id}, submission_id={submission_id}")
        aligned = await run_ai_pipeline(exam_id, submission_id)
        logger.info(f"✅ Phase 3 pipeline test completed successfully")
        logger.info(f"Aligned output: {aligned}")

    except Exception as e:
        logger.error(f"❌ Phase 3 pipeline test failed: {e}")

# Run the test when script is executed directly
if __name__ == "__main__":
    asyncio.run(main())
