FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FILE_ROOT=/workspace \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN mkdir -p \
    /workspace/ComfyUI \
    /workspace/ComfyUI/models \
    /workspace/ComfyUI/custom_nodes \
    /workspace/ComfyUI/input \
    /workspace/ComfyUI/output \
    && touch /workspace/ComfyUI/main.py

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY component ./component
COPY css ./css

EXPOSE 7860 8188

CMD ["python", "/app/app.py"]