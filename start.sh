#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

cd /workspace/ComfyUI

mkdir -p \
    models/loras/krea2 \
    models/diffusion_models/krea2 \
    models/text_encoders \
    models/vae

download() {
    local dir="$1"
    local out="$2"
    local url="$3"

    if [ ! -f "${dir}/${out}" ]; then
        aria2c \
            -x 16 \
            -s 16 \
            -k 1M \
            -c \
            --file-allocation=none \
            -d "$dir" \
            -o "$out" \
            "$url"
    fi
}

download \
    models/diffusion_models/krea2 \
    "RedCraft.safetensors" \
    "https://huggingface.co/messcheant/keepfast/resolve/main/model/RedCraft.safetensors?download=true"

download \
    models/text_encoders \
    "qwen3-vl-4b-heretic_int8.safetensors" \
    "https://huggingface.co/DreamFast/Qwen3-VL-4b-Heretic-ComfyUI/resolve/main/qwen3-vl-4b-heretic_int8.safetensors"

download \
    models/vae \
    "qwen_image_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors"

download \
    models/vae \
    "Wan2.1_VAE_upscale2x_imageonly_real_v1.safetensors" \
    "https://huggingface.co/spacepxl/Wan2.1-VAE-upscale2x/resolve/main/Wan2.1_VAE_upscale2x_imageonly_real_v1.safetensors"

download \
    models/loras/krea2 \
    "krea2_identity_edit_v1_2.safetensors" \
    "https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2.safetensors"

download \
    models/loras/krea2 \
    "real-fake-beast-slider.safetensors" \
    "https://huggingface.co/messcheant/keepfast/resolve/main/real-fake-beast-slider.safetensors?download=true"

download \
    models/loras/krea2 \
    "breast-slider.safetensors" \
    "https://huggingface.co/messcheant/keepfast/resolve/main/breast-slider.safetensors"

cd /workspace/ComfyUI/custom_nodes

[ -d comfyui-krea2edit ] || \
    git clone --depth 1 \
    https://github.com/lbouaraba/comfyui-krea2edit

[ -d ComfyUI-Pixaroma ] || \
    git clone --depth 1 \
    https://github.com/pixaroma/ComfyUI-Pixaroma

[ -d ComfyUI-KJNodes ] || \
    git clone --depth 1 \
    https://github.com/kijai/ComfyUI-KJNodes

[ -d ComfyUI-Manager ] || \
    git clone --depth 1 \
    https://github.com/ltdrdata/ComfyUI-Manager

[ -d ComfyUI-Krea2T-Enhancer ] || \
    git clone --depth 1 \
    https://github.com/capitan01R/ComfyUI-Krea2T-Enhancer

find . \
    -maxdepth 2 \
    -name "requirements.txt" \
    -print0 |
while IFS= read -r -d '' req; do
    pip install --no-cache-dir -r "$req"
done

cd /workspace/ComfyUI

jupyter lab \
    --ip=0.0.0.0 \
    --port="${JUPYTER_PORT:-8888}" \
    --no-browser \
    --allow-root \
    --ServerApp.allow_remote_access=True \
    --ServerApp.root_dir=/workspace \
    --ServerApp.token='' \
    --ServerApp.password='' \
    > /tmp/jupyter.log 2>&1 &

JUPYTER_PID=$!

for i in {1..30}; do
    if ! kill -0 "$JUPYTER_PID" 2>/dev/null; then
        cat /tmp/jupyter.log || true
        exit 1
    fi

    if curl -fsS \
        "http://127.0.0.1:${JUPYTER_PORT:-8888}/api" \
        >/dev/null 2>&1; then
        break
    fi

    if [ "$i" -eq 30 ]; then
        cat /tmp/jupyter.log || true
        exit 1
    fi

    sleep 1
done

exec python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --highvram \
    --disable-dynamic-vram
