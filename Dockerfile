FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    aria2 \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
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
