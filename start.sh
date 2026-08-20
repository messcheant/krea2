#!/usr/bin/env bash
set -euo pipefail

# Jika ada argumen, jalankan perintah itu saja (untuk fleksibilitas)
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Aktifkan virtualenv Vast.ai (penting!)
if [ -f /venv/main/bin/activate ]; then
    # shellcheck disable=SC1091
    source /venv/main/bin/activate
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
        echo ">>> Downloading ${out} ..."
        aria2c \
            -x 16 \
            -s 16 \
            -k 1M \
            -c \
            --file-allocation=none \
            -d "$dir" \
            -o "$out" \
            "$url"
    else
        echo ">>> ${out} already exists, skip."
    fi
}

download \
    models/diffusion_models/krea2 \
    "LUSTIFY!-int8.safetensors" \
    "https://huggingface.co/messcheant/keepfast/resolve/main/model/LUSTIFY!-int8.safetensors"

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
    "Realistic-Snapshot.safetensors" \
    "https://huggingface.co/messcheant/keepfast/resolve/main/Realistic-Snapshot.safetensors"

# === Custom Nodes ===
cd /workspace/ComfyUI/custom_nodes

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

# Install requirements custom nodes
find . -maxdepth 2 -name "requirements.txt" -print0 | \
while IFS= read -r -d '' req; do
    echo ">>> Installing requirements from $req"
    pip install --no-cache-dir -r "$req" || true
done

cd /workspace/ComfyUI

# === Start Jupyter (background) ===
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

# Tunggu Jupyter siap
for i in {1..30}; do
    if ! kill -0 "$JUPYTER_PID" 2>/dev/null; then
        echo "Jupyter failed to start:"
        cat /tmp/jupyter.log || true
        exit 1
    fi

    if curl -fsS "http://127.0.0.1:${JUPYTER_PORT:-8888}/api" >/dev/null 2>&1; then
        echo ">>> Jupyter is ready on port ${JUPYTER_PORT:-8888}"
        break
    fi

    if [ "$i" -eq 30 ]; then
        echo "Jupyter timeout:"
        cat /tmp/jupyter.log || true
        exit 1
    fi
    sleep 1
done

# === Start ComfyUI (foreground) ===
# Flag penting: --use-sage-attention + --listen 0.0.0.0 --port 8188
exec python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --use-sage-attention \
    --highvram \
    --disable-dynamic-vram
