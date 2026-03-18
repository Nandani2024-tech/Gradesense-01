from dataclasses import dataclass
from typing import List

@dataclass
class OCRLine:
    text: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    page_index: int
    width: float
    height: float

    @property
    def y_mid(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def bbox(self) -> List[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    @staticmethod
    def from_dict(row: dict, page_index: int = 0, width: float = 1.0, height: float = 1.0) -> 'OCRLine':
        return OCRLine(
            text=str(row.get("text", "")).strip(),
            x1=float(row.get("x1", 0.0)),
            y1=float(row.get("y1", 0.0)),
            x2=float(row.get("x2", 0.0)),
            y2=float(row.get("y2", 0.0)),
            confidence=float(row.get("confidence", row.get("conf", 0.0)) or 0.0),
            page_index=page_index,
            width=width,
            height=height,
        )
