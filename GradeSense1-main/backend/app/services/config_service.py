from typing import Dict, List

ADMIN_WHITELIST: List[str] = [
    "gradingtoolaibased@gmail.com",
    # Add more admin emails here
]

DEFAULT_FEATURES: Dict[str, bool] = {
    "ai_suggestions": True,
    "sub_questions": True,
    "bulk_upload": True,
    "analytics": True,
    "peer_comparison": True,
    "export_data": True
}

class ConfigService:
    def get_admin_whitelist(self) -> List[str]:
        return ADMIN_WHITELIST

    def get_default_features(self) -> Dict[str, bool]:
        return DEFAULT_FEATURES

    def is_admin_email(self, email: str) -> bool:
        return email in ADMIN_WHITELIST

config_service = ConfigService()
