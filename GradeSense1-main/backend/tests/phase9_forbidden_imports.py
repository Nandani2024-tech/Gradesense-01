import os
import re

# --- CONFIGURATION ---
ROUTES_DIR = r"C:\BaseLine\GradeSense1-main\backend\app\routes"

FORBIDDEN_IMPORTS = {
    "gridfs_storage": "FileService",
    "file_utils": "FileService",
    "pdf_converter": "FileService",
    "answer_sheet_pipeline": "FileService",
    "grading_pipeline": "GradingService",
    "simple_pipeline": "GradingService",
    "auto_extract_questions": "ExtractionService",
    "_process_model_answer_async": "ExtractionService",
    "_process_question_paper_async": "ExtractionService",
    "preflight_submission_mapping": "MappingService",
    "workers": "Service/Worker layer"  # generic placeholder
}
ALLOWED_IMPORTS = ["schemas", "services", "middleware"]

# --- UTILITIES ---
def scan_file(file_path):
    violations = []
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            # detect import statements
            match = re.search(r"(?:from|import)\s+([\w_.]+)", line)
            if match:
                imported_module = match.group(1)
                for forbidden, service in FORBIDDEN_IMPORTS.items():
                    if forbidden in imported_module:
                        violations.append({
                            "line": i,
                            "imported": imported_module,
                            "suggested": service
                        })
    return violations

def process_routes():
    report = []
    total_violations = 0
    files_with_violations = 0

    for root, _, files in os.walk(ROUTES_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            file_path = os.path.join(root, file)
            violations = scan_file(file_path)
            if violations:
                files_with_violations += 1
                total_violations += len(violations)
                for v in violations:
                    report.append({
                        "file": file_path,
                        "forbidden_import": v["imported"],
                        "line": v["line"],
                        "suggested_fix": v["suggested"]
                    })
    return report, files_with_violations, total_violations

# --- RUN SCRIPT ---
if __name__ == "__main__":
    report, files_with_violations, total_violations = process_routes()

    print("\n=== Forbidden Imports Audit Report ===\n")
    print(f"Total Files Scanned: {sum([len(files) for _, _, files in os.walk(ROUTES_DIR)])}")
    print(f"Files with Violations: {files_with_violations}")
    print(f"Total Violations Found: {total_violations}\n")

    print("Detailed Violations:\n")
    print(f"{'Route File':50} {'Forbidden Import':30} {'Line':5} {'Suggested Fix'}")
    print("-" * 110)
    for r in report:
        print(f"{r['file']:50} {r['forbidden_import']:30} {r['line']:5} {r['suggested_fix']}")

    print("\n--- End of Report ---")
    print("Next Steps:")
    print("1. Manually replace the forbidden imports with calls to suggested services.")
    print("2. Ensure routes remain thin controllers.")
    print("3. Run tests (pytest) after cleanup.")
