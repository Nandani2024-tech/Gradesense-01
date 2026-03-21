import asyncio
from app.services.pipelines.ai_structured.engine import run_ai_pipeline

async def test_ai_pipeline(exam_id, submission_id):
    try:
        print(f"🚀 Testing Phase 3 AI pipeline for exam {exam_id}, submission {submission_id}")
        aligned = await run_ai_pipeline(exam_id, submission_id)

        # Basic sanity checks
        assert "questions" in aligned, "❌ Output missing 'questions'"
        for q in aligned["questions"]:
            assert "number" in q, f"❌ Question missing number: {q}"
            assert "marks" in q, f"❌ Question missing marks: {q}"
            if "subquestions" in q:
                for sq in q["subquestions"]:
                    assert "label" in sq, f"❌ Subquestion missing label: {sq}"
                    assert "student_answer" in sq, f"❌ Subquestion missing answer: {sq}"

        # Check total marks
        total_marks = sum(q.get("marks", 0) for q in aligned["questions"])
        print(f"✅ Total marks computed: {total_marks}")

        # Optional: feed into mock grading engine
        # result = await GradingEngine.run_production_grading(blueprint=aligned, vision_answers=aligned)
        print("✅ Phase 4 AI pipeline test passed. All questions/subquestions intact.")

    except Exception as e:
        if type(e).__name__ == "CustomServiceException":
            code = e.args[0] if len(e.args) > 0 else "unknown_error"
            status = e.args[1] if len(e.args) > 1 else "N/A"
            print(f"❌ Phase 4 AI pipeline test failed: {code} (HTTP {status})")
        else:
            print(f"❌ Phase 4 AI pipeline test failed: {e}")



# Run standalone
if __name__ == "__main__":
    exam_id = "exam_6660725c"
    submission_id = "sub_dfcb4fb8"
    asyncio.run(test_ai_pipeline(exam_id, submission_id))
