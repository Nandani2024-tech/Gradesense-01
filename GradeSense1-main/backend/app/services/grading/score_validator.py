from typing import Dict, Any
from app.layers.universal.grader import ScoreValidator as DomainScoreValidator

class ScoreValidator:
    """
    Facade for score validation using the domain layer rules.
    """

    def validate(self, result: Dict[str, Any], max_marks: float) -> Dict[str, Any]:
        """Backward compatible wrapper for DomainScoreValidator.validate"""
        return DomainScoreValidator.validate(result, max_marks)
