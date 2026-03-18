from typing import Dict

DEFAULT_QUOTAS: Dict[str, int] = {
    "max_exams_per_month": 100,
    "max_papers_per_month": 1000,
    "max_students": 500,
    "max_batches": 50
}

class QuotaService:
    def get_default_quotas(self) -> Dict[str, int]:
        return DEFAULT_QUOTAS

    def check_quota(self, user_id: str, quota_name: str) -> bool:
        # Simplified for now, just returns True as the original deps.py didn't have logic here
        return True

quota_service = QuotaService()
