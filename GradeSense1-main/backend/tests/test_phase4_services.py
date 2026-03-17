"""
Phase 4 Architecture Validation Tests
Student & Submission Logic Extraction

Run using:
python -m tests.test_phase4_services
"""

import inspect
import sys


def print_result(name, passed):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")


def test_student_service_import():
    """Ensure student_service exists and imports correctly."""
    try:
        from app.services.students import student_service
        print_result("Student Service Import", True)
        return student_service
    except Exception as e:
        print_result("Student Service Import", False)
        print(e)
        return None


def test_submission_service_import():
    """Ensure submission_service exists and imports correctly."""
    try:
        from app.services.submissions import submission_service
        print_result("Submission Service Import", True)
        return submission_service
    except Exception as e:
        print_result("Submission Service Import", False)
        print(e)
        return None


def test_student_service_functions(service):
    """Verify required student service functions exist."""
    required = [
        "identify_student",
        "create_student"
    ]

    passed = True

    for func in required:
        if not hasattr(service, func):
            print_result(f"StudentService missing {func}", False)
            passed = False
        else:
            print_result(f"StudentService has {func}", True)

    return passed


def test_submission_service_functions(service):
    """Verify required submission service functions exist."""
    required = [
        "create_submission",
        "normalize_scores"
    ]

    passed = True

    for func in required:
        if not hasattr(service, func):
            print_result(f"SubmissionService missing {func}", False)
            passed = False
        else:
            print_result(f"SubmissionService has {func}", True)

    return passed


def test_routes_are_thin():
    """
    Ensure routes do NOT contain database calls directly.
    This validates thin-controller architecture.
    """
    try:
        import app.routes.students as students_routes
        source = inspect.getsource(students_routes)

        if "db." in source:
            print_result("Routes still contain DB access", False)
            return False

        print_result("Routes are thin controllers", True)
        return True

    except Exception as e:
        print_result("Route thinness test failed", False)
        print(e)
        return False


def test_service_structure():
    """
    Ensure correct folder structure exists.
    """

    expected_paths = [
        "app/services/students",
        "app/services/submissions"
    ]

    passed = True

    for path in expected_paths:
        try:
            __import__(path.replace("/", "."))
            print_result(f"Folder exists: {path}", True)
        except Exception:
            print_result(f"Folder missing: {path}", False)
            passed = False

    return passed


def run_tests():
    print("\nRunning Phase 4 Architecture Tests\n")

    student_service = test_student_service_import()
    submission_service = test_submission_service_import()

    if student_service:
        test_student_service_functions(student_service)

    if submission_service:
        test_submission_service_functions(submission_service)

    test_service_structure()
    test_routes_are_thin()

    print("\nPhase 4 Tests Completed\n")


if __name__ == "__main__":
    run_tests()
