import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.grading_core import run_grading_orchestrator
from app.services.grading.grading_service import create_initial_submission, update_submission_with_results
from app.core.database import db

async def verify_integration():
    # Use existing exam and some dummy PDF data
    exam_id = "exam_6660725c"  # from phase4_test_ai_pipeline.py
    job_id = "job_test_integration"
    student_info = {"student_id": "TEST_STU_001", "student_name": "Test Student"}
    
    # We need some dummy PDF bytes or read a real one if available
    # Since I don't have a PDF easily, I'll mock the pdf_to_clean_images if needed
    # but let's see if we can just trigger it.
    
    print("🚀 Starting verification script")
    
    # 1. Simulate Worker: Create initial submission
    # We'll use an empty byte string for now and mock if it fails
    pdf_bytes = b"%PDF-1.4 dummy content" 
    
    # Note: pdf_to_clean_images might fail on dummy bytes. 
    # Let's mock it for the test if we are just testing wiring.
    import app.services.answer_sheet_pipeline
    original_pdf_to_images = app.services.answer_sheet_pipeline.pdf_to_clean_images
    app.services.answer_sheet_pipeline.pdf_to_clean_images = lambda x, **kwargs: ["image_base64_placeholder"]

    try:
        print("Step 1: Creating initial submission...")
        submission_id = await create_initial_submission(
            exam_id=exam_id,
            job_id=job_id,
            student_info=student_info,
            pdf_bytes=pdf_bytes,
            filename="test_paper.pdf"
        )
        print(f"✅ Created submission: {submission_id}")

        # 2. Simulate Worker: Call Orchestrator
        print("Step 2: Calling run_grading_orchestrator...")
        # Mock run_ai_pipeline to avoid actual LLM calls if needed, 
        # but the task is about wiring.
        # If we want to skip LLM, we can mock run_ai_pipeline.
        
        import app.services.pipelines.ai_structured.engine
        original_run_ai_pipeline = app.services.pipelines.ai_structured.engine.run_ai_pipeline
        app.services.pipelines.ai_structured.engine.run_ai_pipeline = lambda eid, sid: asyncio.sleep(0, result={
            "answers": [
                {"question_number": "1", "combined_text": "France is Paris", "mapping_confidence": 0.9},
                {"question_number": "2", "sub_label": "a", "combined_text": "Osmosis is...", "mapping_confidence": 0.8}
            ]
        }) or {"answers": [{"question_number": "1", "combined_text": "Paris", "mapping_confidence": 0.9}]}

        # Actually, let's let it run if the environment is set up.
        # But for wiring test, mocking is safer.
        
        result = await run_grading_orchestrator(
            exam_id=exam_id,
            submission_id=submission_id
        )
        
        print(f"✅ Orchestrator result status: {result.get('status')}")
        print(f"✅ Total awarded: {result.get('total_awarded')}")
        
        # 3. Simulate Worker: Update submission
        print("Step 3: Updating submission with results...")
        await update_submission_with_results(submission_id, result)
        print("✅ Submission updated.")

        # 4. Check DB
        final_doc = await db.submissions.find_one({"submission_id": submission_id})
        print(f"✅ Final status in DB: {final_doc.get('status')}")
        print(f"✅ Final total_score in DB: {final_doc.get('total_score')}")

    finally:
        # Restore mocks
        app.services.answer_sheet_pipeline.pdf_to_clean_images = original_pdf_to_images
        # cleanup test data
        await db.submissions.delete_one({"submission_id": submission_id})
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    asyncio.run(verify_integration())
