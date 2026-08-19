FROM yanwk/comfyui-boot:cu128-slim

USER root

RUN zypper --non-interactive refresh && \
    zypper --non-interactive install --no-confirm \
      aria2 \
      git \
      wget \
      libglvnd \
      glib2 \
    && zypper clean --all

RUN pip install --no-cache-dir onnxruntime-gpu --extra-index-url https://pypi.ngc.nvidia.com


COPY start.sh /root/user-scripts/01-krea2-setup.sh
RUN chmod +x /root/user-scripts/01-krea2-setup.sh


ENV CLI_ARGS="--use-ck-attention --listen 0.0.0.0 --port 8188"
