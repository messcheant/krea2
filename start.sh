#!/usr/bin/env bash
set -euo pipefail

cd /workspace/ComfyUI

mkdir -p models/loras/krea2 models/diffusion_models/krea2 models/text_encoders models/vae

download() {
    local dir="$1" out="$2" url="$3"
    if [ ! -f "${dir}/${out}" ]; then
        aria2c -x 16 -s 16 -k 1M -c -d "$dir" -o "$out" "$url"
    fi
}

download models/diffusion_models/krea2 "LUSTIFY!-int8.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/model/LUSTIFY!-int8.safetensors"
download models/text_encoders "qwen3-vl-4b-heretic_int8.safetensors" "https://huggingface.co/DreamFast/Qwen3-VL-4b-Heretic-ComfyUI/resolve/main/qwen3-vl-4b-heretic_int8.safetensors"
download models/vae "qwen_image_vae.safetensors" "https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors"

download models/loras/krea2 "krea2_identity_edit_v1_2.safetensors" "https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2.safetensors"
download models/loras/krea2 "2000s-Analog-Core.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/2000s-Analog-Core.safetensors"
download models/loras/krea2 "Alt-Girl-E-Girl.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Alt-Girl-E-Girl.safetensors"
download models/loras/krea2 "BloomGirls.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/BloomGirls.safetensors"
download models/loras/krea2 "Realism-Engine.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Realism-Engine.safetensors"
download models/loras/krea2 "Realistic-Snapshot.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Realistic-Snapshot.safetensors"
download models/loras/krea2 "[BSS].safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/%5BBSS%5D.safetensors"

cd /workspace/ComfyUI/custom_nodes
[ -d comfyui-krea2edit ] || git clone --depth 1 https://github.com/lbouaraba/comfyui-krea2edit
[ -d ComfyUI-Pixaroma ] || git clone --depth 1 https://github.com/pixaroma/ComfyUI-Pixaroma
[ -d ComfyUI-KJNodes ] || git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes

find . -maxdepth 2 -name "requirements.txt" -exec pip install --no-cache-dir -r {} \;

cd /workspace/ComfyUI

jupyter lab \
    --ip=0.0.0.0 \
    --port="${JUPYTER_PORT:-8888}" \
    --no-browser \
    --allow-root \
    --NotebookApp.token="${JUPYTER_TOKEN:-comfy}" \
    --NotebookApp.password='' \
    --ServerApp.root_dir=/workspace \
    > /tmp/jupyter.log 2>&1 &

exec python main.py --listen 0.0.0.0 --port 8188 --use-ck-attention
