import os
import sys

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from app.services.pipelines.ai_extraction_service import _merge_semantic_with_visual_entities

visual_entities = {
    "questions": [
        {
            "number": 1,
            "page": 0,
            "bbox": [100, 100, 200, 200],
            "confidence": 0.9,
            "subquestions": [],
            "question_type": "short"
        },
        {
            "number": 1,
            "page": 0,
            "bbox": [100, 100, 200, 200], # exact overlap
            "confidence": 0.8,
            "subquestions": [],
            "question_type": "short"
        },
        {
            "number": 2,
            "page": 0,
            "bbox": [100, 250, 200, 350],
            "confidence": 0.95,
            "subquestions": [
                {"label": "a", "marks": 2, "text": ""}
            ],
            "question_type": "short"
        }
    ],
    "subparts": [
        {"q": 2, "label": "a", "page": 0, "bbox": [150, 260, 180, 280], "confidence": 0.9}
    ]
}

stage2_structure = {
    "questions": [
        {
            "number": 1,
            "section": "A",
            "question_text": "What is AI?",
            "question_type": "short",
            "image_evidence": [
                {"page_index": 0, "bbox": [105, 105, 195, 195]} # > 50% overlap
            ]
        },
        {
            "number": 2,
            "section": "B",
            "question_text": "Explain Machine Learning.",
            "question_type": "short",
            "image_evidence": [
                {"page_index": 0, "bbox": [100, 250, 200, 350]}
            ],
            "subquestions": [
                {"label": "a", "text": "Semantic subtext."}
            ]
        },
        {
            "number": 3, # Orphan
            "section": "C",
            "question_text": "Should be recorded as missing match"
        }
    ]
}

try:
    merged = _merge_semantic_with_visual_entities(
        stage2_structure=stage2_structure,
        visual_entities=visual_entities
    )
    print("SUCCESS")
    print("Final questions count:", len(merged["questions"]))
    for q in merged["questions"]:
        print(f"Q{q['number']} text: {q.get('question_text', 'EMPTY')}")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
