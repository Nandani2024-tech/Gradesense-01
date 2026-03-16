# Phase 3: Constants Canonicalization Report

## 1. Constants Moved

| Constant              | Original File                  | New Location        |
| --------------------- | ------------------------------ | ------------------- |
| `QUESTION_TYPE_LITERAL` | `app/layers/ai_structured/schemas.py` | `app/constants/layers.py` |
| `_EXPLICIT_SOURCES`     | `app/layers/ai_structured/mark_reasoner.py` | `app/constants/layers.py` |

---

## 2. Files Updated

The following files were modified to import constants from the canonical `app/constants/layers.py` module rather than defining them inline:

* `app/layers/ai_structured/schemas.py`
* `app/layers/ai_structured/mark_reasoner.py`

---

## 3. Duplicate Check

Checked the repository using text search to confirm no duplicate logic or hidden configurations remain.

* `QUESTION_TYPE_LITERAL` → **1 definition** (in `app/constants/layers.py`) and 1 import (`schemas.py`)
* `_EXPLICIT_SOURCES` → **1 definition** (in `app/constants/layers.py`) and 1 import (`mark_reasoner.py`)

---

## 4. Import Validation

Successfully verified runtime loading without module or circular import errors for:
* `app.layers.ai_structured`
* `app.layers.universal`
* `app.layers.college`
* `app.layers.upsc`

## Expected Outcome Reached

✔ All shared constants live in `app/constants/layers.py`
✔ Domain modules import constants from a single source
✔ No duplicated constants exist
✔ Domain logic files contain only logic, not configuration
