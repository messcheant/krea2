#!/bin/bash
set -e

CUSTOM_NODES_DIR="/workspace/ComfyUI/custom_nodes"
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"

echo "Memeriksa dan menginstal custom nodes..."

[ -d comfyui-krea2edit ] || \
    git clone --depth 1 https://github.com/lbouaraba/comfyui-krea2edit

[ -d ComfyUI-Pixaroma ] || \
    git clone --depth 1 https://github.com/pixaroma/ComfyUI-Pixaroma

[ -d ComfyUI-KJNodes ] || \
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes

[ -d ComfyUI-Manager ] || \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager

[ -d ComfyUI-Krea2T-Enhancer ] || \
    git clone --depth 1 https://github.com/capitan01R/ComfyUI-Krea2T-Enhancer


cd /app

echo "Menjalankan aplikasi utama..."

exec python /app/app.py
