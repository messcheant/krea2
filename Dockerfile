FROM vastai/pytorch:2.11.0-cuda-13.0.3-py312-24.04-2026-08-18

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    WORKSPACE=/workspace

USER root

RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        aria2 \
        git \
        wget \
        curl \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN . /venv/main/bin/activate && \
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /workspace/ComfyUI && \
    cd /workspace/ComfyUI && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
        jupyterlab \
        jupyter-server-terminals \
        terminado \
        ipywidgets \
        opencv-python-headless \
        pillow \
        requests \
        tqdm \
        safetensors \
        einops \
        transformers \
        accelerate \
        diffusers

RUN . /venv/main/bin/activate && \
    pip install --no-cache-dir \
        --index-url https://wheels.astral.sh/simple/cu130/ \
        --extra-index-url https://pypi.org/simple \
        "sageattention==2.2.0+cu.13.0.torch.2.11"

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8188 8888 1111

WORKDIR /workspace/ComfyUI
ENTRYPOINT ["/start.sh"]
