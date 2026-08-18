FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive

RUN rm -f /etc/apt/sources.list.d/cuda*.list \
    && rm -f /etc/apt/sources.list.d/nvidia*.list \
    && apt-get update && apt-get install -y \
    aria2 \
    git \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /workspace

RUN git clone https://github.com/comfyanonymous/ComfyUI.git

WORKDIR /workspace/ComfyUI


RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir onnxruntime-gpu --extra-index-url https://pypi.ngc.nvidia.com

RUN pip install --no-cache-dir sageattention

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8188

# Mengeksekusi script saat container berjalan
CMD ["/start.sh"]
