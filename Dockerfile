FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime
 
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONUNBUFFERED=1 \
    JUPYTER_TOKEN=comfy \
    JUPYTER_PORT=8888
 
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        aria2 \
        git \
        wget \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*
 
WORKDIR /workspace
 
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
 
WORKDIR /workspace/ComfyUI
 
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir onnxruntime-gpu --extra-index-url https://pypi.ngc.nvidia.com && \
    pip install --no-cache-dir jupyterlab ipywidgets
 
COPY start.sh /start.sh
RUN chmod +x /start.sh
 
EXPOSE 8188 8888
 
ENTRYPOINT ["/start.sh"]
