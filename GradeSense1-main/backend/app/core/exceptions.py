from fastapi import HTTPException

class CustomServiceException(HTTPException):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(status_code=status_code, detail=message)

class ExtractionValidationError(CustomServiceException):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=400)
