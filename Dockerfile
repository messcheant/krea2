FROM yanwk/comfyui-boot:cu128-slim

USER root

RUN apt-get update -qq && apt-get install -y -qq \
    aria2 \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir onnxruntime-gpu --extra-index-url https://pypi.ngc.nvidia.com


COPY start.sh /root/user-scripts/01-krea2-setup.sh
RUN chmod +x /root/user-scripts/01-krea2-setup.sh


ENV CLI_ARGS="--use-ck-attention --listen 0.0.0.0 --port 8188"
