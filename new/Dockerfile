FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    FILE_ROOT=/workspace \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        aria2 \
        curl \
        libgl1 \
        libglib2.0-0 \
    && git clone --depth=1 https://github.com/Comfy-Org/ComfyUI.git /workspace/ComfyUI \
    && grep -vE '^(torch|torchvision|torchaudio)([<>=!~ ].*)?$' /workspace/ComfyUI/requirements.txt > /tmp/comfy-requirements.txt \
    && pip install --no-cache-dir -r /tmp/comfy-requirements.txt \
    && rm -rf \
        /workspace/ComfyUI/.git \
        /tmp/comfy-requirements.txt \
        /var/lib/apt/lists/* \
        /root/.cache


WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY component ./component
COPY css ./css

EXPOSE 7860 8188

ENTRYPOINT ["python", "/app/app.py"]
