import sys
import os

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Mock EmailStr to bypass missing email-validator dependency in the environment
import pydantic.networks
if not hasattr(pydantic.networks, 'EmailStr'):
    pydantic.networks.EmailStr = str
pydantic.EmailStr = str

print("Testing backward compatibility imports from app.models.exam...")

try:
    from app.models.exam import Exam, ExamCreate, StudentExamCreate, AnnotationData, ExamQuestion, SubQuestion, StudentSubmission
    print("✅ All imports successful!")
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting Pydantic validation and instantiation...")

try:
    # Test SubQuestion
    sq = SubQuestion(sub_id="a", max_marks=5.0)
    print("✅ SubQuestion instantiated")

    # Test ExamQuestion
    eq = ExamQuestion(question_number=1, max_marks=10.0, sub_questions=[sq])
    print("✅ ExamQuestion instantiated")

    # Test Exam
    exam = Exam(
        exam_id="test_exam",
        batch_id="test_batch",
        subject_id="test_subject",
        exam_type="test_type",
        exam_name="Test Exam",
        total_marks=100.0,
        exam_date="2024-03-12",
        grading_mode="balanced",
        teacher_id="test_teacher",
        questions=[eq]
    )
    print("✅ Exam instantiated")

    # Test ExamCreate
    ec = ExamCreate(
        batch_id="test_batch",
        subject_id="test_subject",
        exam_type="test_type",
        exam_name="Test Exam",
        exam_date="2024-03-12",
        grading_mode="balanced"
    )
    print("✅ ExamCreate instantiated")

    # Test StudentSubmission
    ss = StudentSubmission(
        submission_id="test_sub",
        exam_id="test_exam",
        student_id="test_student",
        student_name="Test Student",
        student_email="test@example.com",
        answer_file_ref="ref",
        submitted_at="2024-03-12T10:00:00Z",
        status="submitted"
    )
    print("✅ StudentSubmission instantiated")

    # Test AnnotationData
    ad = AnnotationData(type="checkmark", x=100, y=200)
    print("✅ AnnotationData instantiated")

    print("\n🚀 All tests passed!")

except Exception as e:
    print(f"❌ Validation failed: {e}")
    sys.exit(1)
