import os

# Configurable zoom for balance between quality and memory usage
PDF_TO_IMAGES_ZOOM = float(os.getenv("PDF_TO_IMAGES_ZOOM", "1.3"))

# Configurable quality (good balance of quality vs size)
PDF_TO_IMAGES_JPEG_QUALITY = int(os.getenv("PDF_TO_IMAGES_JPEG_QUALITY", "60"))
