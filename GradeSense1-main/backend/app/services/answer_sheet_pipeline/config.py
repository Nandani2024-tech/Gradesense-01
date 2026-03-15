import os

ANCHOR_LEFT_RATIO = float(os.getenv("ANCHOR_LEFT_RATIO", "0.38"))
REGION_OCR_CONF_MIN = float(os.getenv("REGION_OCR_CONF_MIN", "0.52"))
REGION_OCR_VISION_CONF_MIN = float(os.getenv("REGION_OCR_VISION_CONF_MIN", "0.45"))
PIPELINE_ENABLED = os.getenv("ANSWER_PACKET_PIPELINE_ENABLED", "true").lower() in ("1", "true", "yes", "on")
PDF_IMAGE_BATCH_PAGES = int(os.getenv("PDF_IMAGE_BATCH_PAGES", "4"))
PDF_IMAGE_JPEG_QUALITY = int(os.getenv("PDF_IMAGE_JPEG_QUALITY", "82"))
PDF_IMAGE_NORMALIZE = os.getenv("PDF_IMAGE_NORMALIZE", "true").lower() in ("1", "true", "yes", "on")
