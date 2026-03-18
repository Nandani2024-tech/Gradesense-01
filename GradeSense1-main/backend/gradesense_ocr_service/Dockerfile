FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# Install everything WITHOUT numpy first
RUN pip install paddlepaddle==2.6.2 \
    paddleocr==2.6.1.3 \
    PyMuPDF==1.20.2 \
    fastapi \
    uvicorn \
    python-multipart

# 🔥 FORCE correct numpy version AFTER everything
RUN pip install numpy==1.24.4 --force-reinstall --no-cache-dir

COPY ocr_service/ .

EXPOSE 8100

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
