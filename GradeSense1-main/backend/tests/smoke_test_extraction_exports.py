import sys
import os

# Add the backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_extraction_exports():
    print("Attempting to import background tasks from app.services.extraction...")
    try:
        from app.services.extraction import _process_question_paper_async, _process_model_answer_async
        print("SUCCESS: Functions imported successfully from app.services.extraction.")
        return True
    except ImportError as e:
        print(f"FAIL: ImportError encountered: {e}")
        return False
    except Exception as e:
        print(f"FAIL: An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    success = test_extraction_exports()
    sys.exit(0 if success else 1)
