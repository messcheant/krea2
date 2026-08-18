# Menggunakan base image PyTorch CUDA 12.8 pilihan Anda
FROM pytorch/pytorch:2.6.0-cuda12.8-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && apt-get install -y -qq \
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


COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8188

# Mengeksekusi script saat container berjalan
CMD ["/start.sh"]
