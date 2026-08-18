#!/usr/bin/env bash
# Menghentikan eksekusi jika ada error pada sistem
set -euo pipefail

# Memastikan kita berada di direktori ComfyUI
cd /workspace/ComfyUI

echo "==> Membuat struktur direktori model..."
mkdir -p models/loras/krea2 models/diffusion_models/krea2 models/text_encoders models/vae

echo "==> Mengunduh Checkpoints & VAE..."
aria2c -x 16 -s 16 -k 1M -c -d models/diffusion_models/krea2 -o "LUSTIFY!-int8.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/model/LUSTIFY!-int8.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/text_encoders -o "qwen3-vl-4b-heretic_int8.safetensors" "https://huggingface.co/DreamFast/Qwen3-VL-4b-Heretic-ComfyUI/resolve/main/qwen3-vl-4b-heretic_int8.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/vae -o "qwen_image_vae.safetensors" "https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors"

echo "==> Mengunduh LoRAs..."
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "krea2_identity_edit_v1_2.safetensors" "https://huggingface.co/conradlocke/krea2-identity-edit/resolve/main/krea2_identity_edit_v1_2.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "2000s-Analog-Core.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/2000s-Analog-Core.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "Alt-Girl-E-Girl.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Alt-Girl-E-Girl.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "BloomGirls.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/BloomGirls.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "Realism-Engine.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Realism-Engine.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "Realistic-Snapshot.safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/Realistic-Snapshot.safetensors"
aria2c -x 16 -s 16 -k 1M -c -d models/loras/krea2 -o "[BSS].safetensors" "https://huggingface.co/messcheant/keepfast/resolve/main/%5BBSS%5D.safetensors"

echo "==> Mengunduh Custom Nodes..."
cd /workspace/ComfyUI/custom_nodes
[ -d comfyui-krea2edit ] || git clone https://github.com/lbouaraba/comfyui-krea2edit
[ -d ComfyUI-Pixaroma ] || git clone https://github.com/pixaroma/ComfyUI-Pixaroma
[ -d ComfyUI-KJNodes ] || git clone https://github.com/kijai/ComfyUI-KJNodes

echo "==> Menginstal dependencies Custom Nodes..."
# Skrip cerdas Anda untuk mencari dan menginstal semua requirements.txt
find . -maxdepth 2 -name "requirements.txt" -print -exec pip install --no-cache-dir -r {} \;

echo "==> Memulai ComfyUI..."
cd /workspace/ComfyUI
exec python main.py --listen 0.0.0.0 --port 8188 --highvram
