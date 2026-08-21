FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    FILE_ROOT=/workspace \
    PIP_NO_CACHE_DIR=1

ARG ZROK_VERSION=2.0.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        aria2 \
        curl \
        ca-certificates \
        tar \
        libgl1 \
        libglib2.0-0 \
    && git clone --depth=1 https://github.com/Comfy-Org/ComfyUI.git /workspace/ComfyUI \
    && grep -vE '^(torch|torchvision|torchaudio)([<>=!~ ].*)?$' \
        /workspace/ComfyUI/requirements.txt > /tmp/comfy-requirements.txt \
    && pip install --no-cache-dir -r /tmp/comfy-requirements.txt \
    && curl -fsSL \
        https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
        -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared \
    && curl -fsSL \
        https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
        -o /tmp/ngrok.tgz \
    && tar -xzf /tmp/ngrok.tgz -C /usr/local/bin \
    && chmod +x /usr/local/bin/ngrok \
    && curl -fsSL \
        https://github.com/openziti/zrok/releases/download/v${ZROK_VERSION}/zrok_${ZROK_VERSION}_linux_amd64.tar.gz \
        -o /tmp/zrok.tar.gz \
    && tar -xzf /tmp/zrok.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/zrok2 \
    && rm -rf \
        /workspace/ComfyUI/.git \
        /tmp/comfy-requirements.txt \
        /tmp/ngrok.tgz \
        /tmp/zrok.tar.gz \
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
