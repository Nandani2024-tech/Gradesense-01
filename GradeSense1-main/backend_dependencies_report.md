# GradeSense Backend: Dependencies and External Services

This document details the external services, module dependencies, and fallback strategies integrated into the GradeSense backend.

## 1. Module Dependencies

| Module / File Name | External Service | Purpose | Input / Output | Configurable | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `app/services/llm/llm_service.py` | **Google Gemini** | Core LLM for grading, semantic reasoning, and structured extraction. | Prompts + Images → JSON Response | Yes (`GEMINI_MODEL_NAME`) | Working |
| `app/utils/ocr_services/vision_ocr_service.py` | **Google Cloud Vision** | High-precision text detection. | Base64 Image → OCR Lines/Words | Yes (`VISION_MIN_CONFIDENCE`) | Working |
| `app/utils/ocr_services/paddle_ocr_service.py` | **PaddleOCR / PPStructure** | Local/Server-side OCR and table detection. | Base64 Image → Text/HTML Tables | Yes (`PADDLE_LANG`, model dirs) | Working |
| `app/services/aws/textract_client.py` | **AWS Textract** | Specialized async analysis for forms and tables. | S3 URI → Document Blocks | Yes (`AWS_PIPELINE_ENABLED`) | Working |
| `app/services/aws/s3_storage.py` | **AWS S3** | Intermediate storage for Textract jobs and raw layer archives. | Bytes/JSON → S3 URI | Yes (`AWS_S3_BUCKET`) | Working |
| `app/infrastructure/storage/gridfs_storage.py` | **MongoDB / GridFS** | Primary database and large binary storage (Images). | Metadata/Binary → DB Records | Yes (`MONGO_URL`, `DB_NAME`) | Working |

## 2. Fallbacks & Error Handling

GradeSense employs a multi-layered approach to ensure reliability when external services fail.

| Target Service | Implementation File | Fallback Type | Mechanism |
| :--- | :--- | :--- | :--- |
| **All OCR Providers** | `app/utils/ocr_provider/core.py` | **Chain Fallback** | `Primary (e.g. Paddle) → Fallback (e.g. Vision) → Ultimate (Gemini)`. Triggered if primary returns empty or low confidence. |
| **Vision API Calls** | `app/utils/ocr_services/vision_ocr_service.py` | **Retry** | Uses `@with_retry` decorator for transient API errors (2 retries). |
| **AI Extraction Pipeline** | `app/services/pipelines/ai_extraction_service.py` | **Repair & Retry** | If validation fails, uses `apply_structure_repairs` and may trigger a semantic retry pass. |
| **GridFS Storage** | `app/services/storage/gridfs_helpers.py` | **Legacy Fallback** | Falls back to direct image storage if GridFS record is missing. |

### Recommendations for Missing Fallbacks:
- **LLM Rate Limits**: Implementation of a global rate-limiting queue or alternative LLM provider (e.g., Anthropic/OpenAI) as a hot fallback for grading.
- **S3 Connectivity**: Local transient storage fallback if S3 is unreachable during the Textract pipeline.

## 3. Configuration

External configurations are handled primarily through environment variables but are currently **scattered** across several configuration modules.

| Config Module | Domain | Key Variables |
| :--- | :--- | :--- |
| `app/core/config.py` | General Pipeline | `COLLEGE_V2_PIPELINE_ENABLED`, `MARK_VALIDATION_ENABLED` |
| `app/core/db_config.py` | Database | `MONGO_URL`, `DB_NAME` |
| `app/utils/ocr_services/config.py` | OCR & LLM | `GEMINI_MODEL_NAME`, `PADDLE_LANG`, `VISION_MODE` |
| `app/services/aws/config.py` | AWS Infrastructure | `AWS_REGION`, `AWS_S3_BUCKET`, `AWS_TEXTRACT_ROLE_ARN` |

### Configuration Characteristics:
- **Centralization**: **Low**. Configurations are grouped by functional area rather than a single technical registry.
- **Client-Specific**: Most settings are global, though `RuntimeConfig` in OCR allows per-request overrides for hints and languages.
- **Security**: Relies on `.env` files (loaded via `dotenv`) for local development; expected to use environment injection in production.

---
**Reference Note**: Use this document to audit external service health and ensure MVP pipelines have robust fallback paths.
