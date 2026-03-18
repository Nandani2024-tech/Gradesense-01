from fastapi import FastAPI
from pydantic import BaseModel
from paddleocr import PaddleOCR
import base64
import numpy as np
from PIL import Image
import io

app = FastAPI()

ocr = PaddleOCR(use_angle_cls=True, lang='en')

class OCRRequest(BaseModel):
    image_base64: str

def bbox_from_points(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)




@app.post("/ocr")
async def ocr_endpoint(req: OCRRequest):
    print("🔥 DOCKER OCR HIT")

    img_bytes = base64.b64decode(req.image_base64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    np_img = np.array(img)

    result = ocr.ocr(np_img)

    words = []
    lines = []

    if result and isinstance(result[0], list):
        for line in result[0]:
            bbox, (text, conf) = line
            x1, y1, x2, y2 = bbox_from_points(bbox)

            line_obj = {
                "text": text,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": conf
            }

            lines.append(line_obj)

            for word in text.split():
                words.append({
                    "text": word,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": conf
                })

    return {
        "words": words,
        "lines": lines
    }
