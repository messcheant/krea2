import html
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from functools import partial
from pathlib import Path

import gradio as gr
import psutil

try:
    import pynvml
except Exception:
    pynvml = None

try:
    import torch
except Exception:
    torch = None


psutil.cpu_percent(interval=None)

SAGE_VERSION = "2.2.0"
SAGE_REPO = "tcpassos/sage-wheels-linux"
SAGE_MATRIX = {
    ("2.11.0", "12.8", "3.12"): {"75", "80", "86", "89", "90", "120"},
    ("2.12.0", "13.0", "3.12"): {"75", "80", "86", "89", "90", "120"},
}

COMFY_KITCHEN_VERSION = "0.2.28"
XFORMERS_VERSION = "0.0.35"
ONNX_CUDA12_VERSION = "1.26.0"
ONNX_CUDA13_VERSION = "1.28.0"
OPENCV_VERSION = "4.12.0.88"
INSIGHTFACE_VERSION = "0.7.3"

GPU_ARCHITECTURES = {
    "70": "Volta",
    "72": "Volta",
    "75": "Turing",
    "80": "Ampere",
    "86": "Ampere",
    "87": "Ampere",
    "89": "Ada Lovelace",
    "90": "Hopper",
    "100": "Blackwell",
    "103": "Blackwell",
    "120": "Blackwell",
    "121": "Blackwell",
}

GPU_CHIP_PATTERNS = [
    (r"\bB200\b|\bB100\b", "GB100"),
    (r"RTX\s*PRO\s*6000.*Blackwell", "GB202"),
    (r"RTX\s*5090", "GB202"),
    (r"RTX\s*5080", "GB203"),
    (r"RTX\s*5070\s*Ti", "GB203"),
    (r"RTX\s*5070", "GB205"),
    (r"\bH200\b|\bH100\b", "GH100"),
    (r"L40S|\bL40\b|RTX\s*6000\s*Ada|RTX\s*4090", "AD102"),
    (r"RTX\s*4080", "AD103"),
    (r"\bL4\b|RTX\s*4070\s*Ti|RTX\s*4070", "AD104"),
    (r"\bA100\b", "GA100"),
    (r"\bA40\b|\bA10\b|RTX\s*A6000|RTX\s*3090|RTX\s*3080\s*Ti", "GA102"),
    (r"RTX\s*3080|RTX\s*3070\s*Ti", "GA102"),
    (r"RTX\s*3070|RTX\s*3060\s*Ti", "GA104"),
    (r"RTX\s*3060", "GA106"),
    (r"\bT4\b|RTX\s*2080", "TU104"),
    (r"RTX\s*2070", "TU106"),
    (r"RTX\s*2060", "TU106"),
    (r"\bV100\b", "GV100"),
]

CORE_CONSTRAINT_PACKAGES = (
    "torch",
    "torchvision",
    "torchaudio",
    "numpy",
    "scipy",
    "pillow",
    "protobuf",
    "pydantic",
    "pydantic-settings",
    "transformers",
    "tokenizers",
    "safetensors",
    "aiohttp",
    "yarl",
    "sqlalchemy",
    "comfy-kitchen",
    "onnxruntime-gpu",
    "onnx",
    "opencv-python-headless",
    "opencv-contrib-python-headless",
    "opencv-python",
    "opencv-contrib-python",
)

OPENCV_DISTRIBUTIONS = (
    "opencv-python-headless",
    "opencv-contrib-python-headless",
    "opencv-python",
    "opencv-contrib-python",
)

GPU_HANDLE = None
GPU_NAME = "No NVIDIA GPU"
NVIDIA_DRIVER = "Unavailable"


#get_cpu_name
def get_cpu_name():
    name = platform.processor().strip()
    if name:
        return name

    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as file:
            for line in file:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    count = psutil.cpu_count(logical=True) or 0
    return f"{count} logical CPUs"


#init_gpu_info
def init_gpu_info():
    global GPU_HANDLE, GPU_NAME, NVIDIA_DRIVER

    if pynvml is None:
        return

    try:
        pynvml.nvmlInit()
        if pynvml.nvmlDeviceGetCount() <= 0:
            return

        GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
        GPU_NAME = pynvml.nvmlDeviceGetName(GPU_HANDLE)
        NVIDIA_DRIVER = pynvml.nvmlSystemGetDriverVersion()

        if isinstance(GPU_NAME, bytes):
            GPU_NAME = GPU_NAME.decode("utf-8")
        if isinstance(NVIDIA_DRIVER, bytes):
            NVIDIA_DRIVER = NVIDIA_DRIVER.decode("utf-8")
    except Exception:
        GPU_HANDLE = None


#get_distribution_version
def get_distribution_version(*names):
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        except Exception:
            continue
    return None


#base_torch_version
def base_torch_version():
    if not torch:
        return None
    return str(getattr(torch, "__version__", "")).split("+", 1)[0] or None


#python_minor
def python_minor():
    return f"{sys.version_info.major}.{sys.version_info.minor}"


#python_tag
def python_tag():
    return f"{sys.version_info.major}{sys.version_info.minor}"


#cuda_version
def cuda_version():
    if not torch:
        return None
    return getattr(getattr(torch, "version", None), "cuda", None)


#cuda_major
def cuda_major():
    version = cuda_version()
    if not version:
        return None
    try:
        return int(str(version).split(".", 1)[0])
    except Exception:
        return None


#cuda_tag
def cuda_tag(version=None):
    version = version or cuda_version()
    if not version:
        return None

    parts = str(version).split(".")
    if len(parts) < 2:
        return None
    return f"cu{parts[0]}{parts[1]}"


#sm_arch
def sm_arch():
    if not torch or not torch.cuda.is_available():
        return None

    try:
        major, minor = torch.cuda.get_device_capability(0)
        return f"{major}{minor}"
    except Exception:
        return None


#get_gpu_chip_codename
def get_gpu_chip_codename(gpu_name=None):
    name = gpu_name or GPU_NAME
    for pattern, codename in GPU_CHIP_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return codename
    return None


#get_gpu_compute_info
def get_gpu_compute_info():
    sm = sm_arch()
    if not sm:
        return "Unavailable"

    architecture = GPU_ARCHITECTURES.get(sm, "Unknown Architecture")
    chip = get_gpu_chip_codename()
    parts = [f"SM{sm}", architecture]
    if chip:
        parts.append(chip)
    return " · ".join(parts)


#get_cudnn_version
def get_cudnn_version():
    if not torch:
        return "Unavailable"

    try:
        version = torch.backends.cudnn.version()
        if not version:
            return "Unavailable"

        version = int(version)
        major = version // 10000
        minor = (version % 10000) // 100
        patch = version % 100
        return f"{major}.{minor}.{patch}"
    except Exception:
        return "Unavailable"


#version_tuple
def version_tuple(value):
    if value is None:
        return ()

    numbers = re.findall(r"\d+", str(value))
    return tuple(int(number) for number in numbers[:4])


#version_at_least
def version_at_least(value, minimum):
    current = version_tuple(value)
    required = version_tuple(minimum)
    if not current or not required:
        return False

    length = max(len(current), len(required))
    current += (0,) * (length - len(current))
    required += (0,) * (length - len(required))
    return current >= required


#driver_major
def driver_major():
    try:
        return int(str(NVIDIA_DRIVER).split(".", 1)[0])
    except Exception:
        return None


#get_comfy_commandline
def get_comfy_commandline():
    candidates = []

    try:
        for process in psutil.process_iter(["cmdline"]):
            cmdline = process.info.get("cmdline") or []
            if not cmdline:
                continue

            joined = " ".join(str(part) for part in cmdline)
            lower = joined.lower()
            if "comfyui" in lower or ("main.py" in lower and "--listen" in lower):
                candidates.append(cmdline)
    except Exception:
        pass

    if candidates:
        return candidates[0]
    return []


#get_active_attention
def get_active_attention():
    command = get_comfy_commandline()
    flags = set(command)

    if "--use-ck-attention" in flags:
        return "Comfy Kitchen"
    if "--use-sage-attention" in flags:
        return "SageAttention"
    if "--use-flash-attention" in flags:
        return "FlashAttention"
    if "--use-pytorch-cross-attention" in flags:
        return "PyTorch SDPA"
    if "--use-split-cross-attention" in flags:
        return "Split Attention"
    if "--use-quad-cross-attention" in flags:
        return "Sub-Quadratic"

    return "PyTorch SDPA"


#get_ffmpeg_version
def get_ffmpeg_version():
    path = shutil.which("ffmpeg")
    if not path:
        return None

    try:
        result = subprocess.run(
            [path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        first_line = (result.stdout or "").splitlines()[0]
        match = re.search(r"ffmpeg version\s+([^\s]+)", first_line, re.IGNORECASE)
        return match.group(1) if match else "Installed"
    except Exception:
        return "Installed"


#get_opencv_version
def get_opencv_version():
    return get_distribution_version(*OPENCV_DISTRIBUTIONS)


#get_onnx_provider
def get_onnx_provider():
    if not get_distribution_version("onnxruntime-gpu", "onnxruntime"):
        return None

    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            return "CUDAExecutionProvider"
        if providers:
            return providers[0]
    except Exception:
        pass
    return None


#snapshot_core_versions
def snapshot_core_versions():
    snapshot = {}
    for package in CORE_CONSTRAINT_PACKAGES:
        version = get_distribution_version(package)
        if version:
            snapshot[package] = version
    return snapshot


#create_constraints_file
def create_constraints_file():
    snapshot = snapshot_core_versions()
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="comfy-console-constraints-",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )

    with handle:
        for package, version in snapshot.items():
            handle.write(f"{package}=={version}\n")

    return handle.name, snapshot


#core_versions_unchanged
def core_versions_unchanged(before):
    changed = []
    for package, expected in before.items():
        current = get_distribution_version(package)
        if current != expected:
            changed.append(f"{package}: {expected} -> {current or 'missing'}")
    return changed


#run_command
def run_command(command, timeout=1800, env=None):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )

    lines = []
    try:
        for line in iter(process.stdout.readline, ""):
            if line:
                lines.append(line.rstrip())
            if process.poll() is not None and not line:
                break
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        lines.append("Installation timed out.")
    except Exception as exc:
        process.kill()
        lines.append(str(exc))

    return process.returncode if process.returncode is not None else 1, "\n".join(lines)


#run_pip_install
def run_pip_install(requirements, extra_args=None, use_constraints=True, timeout=1800):
    extra_args = extra_args or []
    constraints_path = None
    before = snapshot_core_versions()

    try:
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
        ]

        if use_constraints:
            constraints_path, before = create_constraints_file()
            command.extend(["--constraint", constraints_path])

        command.extend(extra_args)
        command.extend(requirements)

        dry_run_command = command[:6] + ["--dry-run"] + command[6:]
        dry_code, dry_output = run_command(dry_run_command, timeout=min(timeout, 600))
        if dry_code != 0:
            return 1, "Compatibility check failed before installation.\n\n" + dry_output

        returncode, output = run_command(command, timeout=timeout)
        output = "[compatibility check]\n" + dry_output + "\n\n[install]\n" + output
        changed = core_versions_unchanged(before)

        if changed:
            output += "\n\nCore package protection failed:\n" + "\n".join(changed)
            return 1, output

        return returncode, output
    finally:
        if constraints_path:
            try:
                os.unlink(constraints_path)
            except OSError:
                pass


#pip_check
def pip_check():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
    )
    return result.returncode, (result.stdout or "").strip()


#sage_wheel_url
def sage_wheel_url():
    torch_version = base_torch_version()
    cuda = cuda_version()
    py_minor = python_minor()
    py_tag = python_tag()
    sm = sm_arch()
    cu_tag = cuda_tag(cuda)

    if not all((torch_version, cuda, py_minor, py_tag, sm, cu_tag)):
        return None

    supported_sms = SAGE_MATRIX.get((torch_version, str(cuda), py_minor))
    if not supported_sms or sm not in supported_sms:
        return None

    release = f"sage-{SAGE_VERSION}-torch-{torch_version}-{cu_tag}-py{py_tag}"
    wheel = f"sageattention-{SAGE_VERSION}-{sm}-cp{py_tag}-cp{py_tag}-linux_x86_64.whl"
    return f"https://github.com/{SAGE_REPO}/releases/download/{release}/{wheel}"


#attention_tool_info
def attention_tool_info(tool_key):
    if tool_key == "sage":
        installed = get_distribution_version("sageattention")
        if installed:
            return tool_info("SageAttention", installed=installed)

        compatible = (
            platform.system() == "Linux"
            and platform.machine() in {"x86_64", "AMD64"}
            and sage_wheel_url() is not None
        )
        return tool_info("SageAttention", compatible=compatible)

    if tool_key == "comfy_kitchen":
        installed = get_distribution_version("comfy-kitchen")
        if installed:
            return tool_info("Comfy Kitchen", installed=installed)

        compatible = (
            version_at_least(python_minor(), "3.10")
            and version_at_least(base_torch_version(), "2.5.0")
        )
        return tool_info("Comfy Kitchen", compatible=compatible)

    if tool_key == "flash":
        installed = get_distribution_version("flash-attn")
        if installed:
            return tool_info("FlashAttention", installed=installed)

        sm = sm_arch()
        compatible = (
            platform.system() == "Linux"
            and sm is not None
            and int(sm) >= 80
            and cuda_major() is not None
            and cuda_major() >= 12
            and version_at_least(base_torch_version(), "2.2.0")
            and shutil.which("nvcc") is not None
        )
        detail = None if compatible else "CUDA toolkit / supported GPU required"
        return tool_info("FlashAttention", compatible=compatible, detail=detail)

    if tool_key == "xformers":
        installed = get_distribution_version("xformers")
        if installed:
            return tool_info("xFormers", installed=installed)

        compatible_cuda = str(cuda_version()) in {"12.6", "12.8", "13.0"}
        compatible = (
            platform.system() == "Linux"
            and version_at_least(base_torch_version(), "2.10.0")
            and compatible_cuda
        )
        return tool_info("xFormers", compatible=compatible)

    if tool_key == "triton":
        installed = get_distribution_version("triton")
        if installed:
            return tool_info("Triton", installed=installed, installable=False)
        return tool_info(
            "Triton",
            compatible=False,
            installable=False,
            detail="Managed by PyTorch",
        )

    return tool_info(tool_key, compatible=False)


#optional_tool_info
def optional_tool_info(tool_key):
    if tool_key == "onnx":
        gpu_version = get_distribution_version("onnxruntime-gpu")
        cpu_version = get_distribution_version("onnxruntime")

        if gpu_version:
            provider = get_onnx_provider()
            detail = provider if provider else "GPU package installed"
            return tool_info("ONNX Runtime GPU", installed=gpu_version, detail=detail)

        if cpu_version:
            return tool_info(
                "ONNX Runtime GPU",
                compatible=False,
                detail=f"CPU runtime {cpu_version} detected",
            )

        compatible = (
            platform.system() == "Linux"
            and platform.machine() in {"x86_64", "AMD64"}
            and cuda_major() in {12, 13}
            and sys.version_info >= (3, 11)
        )
        return tool_info("ONNX Runtime GPU", compatible=compatible)

    if tool_key == "ffmpeg":
        installed = get_ffmpeg_version()
        if installed:
            return tool_info("FFmpeg", installed=installed)

        compatible = platform.system() == "Linux" and shutil.which("apt-get") is not None
        return tool_info("FFmpeg", compatible=compatible)

    if tool_key == "opencv":
        installed = get_opencv_version()
        if installed:
            return tool_info("OpenCV", installed=installed)

        return tool_info("OpenCV", compatible=sys.version_info >= (3, 8))

    if tool_key == "pyav":
        installed = get_distribution_version("av")
        if installed:
            return tool_info("Video Tools", installed=installed)

        return tool_info("Video Tools", compatible=sys.version_info >= (3, 10))

    if tool_key == "insightface":
        installed = get_distribution_version("insightface")
        if installed:
            return tool_info("InsightFace", installed=installed)

        onnx_gpu = get_distribution_version("onnxruntime-gpu")
        opencv = get_opencv_version()
        compiler = shutil.which("g++") or shutil.which("c++") or shutil.which("gcc")
        compatible = bool(onnx_gpu and opencv and compiler and sys.version_info >= (3, 10))
        detail = None if compatible else "Requires ONNX GPU, OpenCV and compiler"
        return tool_info("InsightFace", compatible=compatible, detail=detail)

    return tool_info(tool_key, compatible=False)


#tool_info
def tool_info(name, installed=None, compatible=True, installable=True, detail=None):
    if installed:
        return {
            "name": name,
            "state": "installed",
            "status": f"Installed · {installed}",
            "button": "Installed",
            "interactive": False,
            "detail": detail,
        }

    if not installable:
        return {
            "name": name,
            "state": "ready" if compatible else "unavailable",
            "status": detail or ("Ready" if compatible else "Unavailable"),
            "button": "Ready" if compatible else "Unavailable",
            "interactive": False,
            "detail": detail,
        }

    if not compatible:
        return {
            "name": name,
            "state": "unavailable",
            "status": "Unavailable",
            "button": "Unavailable",
            "interactive": False,
            "detail": detail,
        }

    return {
        "name": name,
        "state": "missing",
        "status": "Not Installed",
        "button": "Install",
        "interactive": True,
        "detail": detail,
    }


#tool_status_html
def tool_status_html(info):
    return f"""
    <div class="tool-status tool-{html.escape(info['state'])}">
        <span>{html.escape(info['name'])}</span>
        <strong>{html.escape(info['status'])}</strong>
    </div>
    """


#log_html
def log_html(text):
    escaped = html.escape(text or "Ready. Select an optional component to install.")
    return f'<pre class="install-log-text">{escaped}</pre>'


#install_sage
def install_sage():
    wheel_url = sage_wheel_url()
    if not wheel_url:
        return 1, "No compatible SageAttention prebuilt wheel for this environment."

    return run_pip_install(
        [wheel_url],
        extra_args=["--no-deps"],
        use_constraints=False,
        timeout=900,
    )


#install_comfy_kitchen
def install_comfy_kitchen():
    return run_pip_install(
        [f"comfy-kitchen=={COMFY_KITCHEN_VERSION}"],
        extra_args=["--no-deps", "--only-binary=:all:"],
        use_constraints=False,
        timeout=900,
    )


#install_flash_attention
def install_flash_attention():
    info = attention_tool_info("flash")
    if not info["interactive"]:
        return 1, info.get("detail") or "FlashAttention is not compatible with this environment."

    build_deps = ["packaging", "ninja", "einops"]
    deps_code, deps_output = run_pip_install(build_deps, timeout=300)
    if deps_code != 0:
        return deps_code, deps_output

    env = os.environ.copy()
    env.setdefault("MAX_JOBS", str(max(1, min(4, psutil.cpu_count(logical=True) or 1))))

    constraints_path, before = create_constraints_file()
    try:
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--constraint",
            constraints_path,
            "--no-build-isolation",
            "--no-deps",
            "flash-attn",
        ]
        code, output = run_command(command, timeout=1800, env=env)
        changed = core_versions_unchanged(before)
        if changed:
            output += "\n\nCore package protection failed:\n" + "\n".join(changed)
            return 1, output
        return code, deps_output + "\n" + output
    finally:
        try:
            os.unlink(constraints_path)
        except OSError:
            pass


#install_xformers
def install_xformers():
    cu_tag = cuda_tag()
    if cu_tag not in {"cu126", "cu128", "cu130"}:
        return 1, "No official xFormers wheel index for this CUDA runtime."

    index_url = f"https://download.pytorch.org/whl/{cu_tag}"
    return run_pip_install(
        [f"xformers=={XFORMERS_VERSION}"],
        extra_args=["--no-deps", "--index-url", index_url],
        use_constraints=False,
        timeout=900,
    )


#install_onnx_runtime
def install_onnx_runtime():
    major = cuda_major()
    if major == 12:
        version = ONNX_CUDA12_VERSION
    elif major == 13:
        version = ONNX_CUDA13_VERSION
    else:
        return 1, "ONNX Runtime GPU installer supports CUDA 12.x or 13.x only."

    if get_distribution_version("onnxruntime") and not get_distribution_version("onnxruntime-gpu"):
        return 1, "CPU onnxruntime is installed. Remove it first to avoid conflicting runtimes."

    return run_pip_install([f"onnxruntime-gpu=={version}"], timeout=900)


#install_ffmpeg
def install_ffmpeg():
    apt = shutil.which("apt-get")
    if not apt:
        return 1, "apt-get is not available in this container."

    update_code, update_output = run_command([apt, "update"], timeout=600)
    if update_code != 0:
        return update_code, update_output

    install_code, install_output = run_command(
        [apt, "install", "-y", "--no-install-recommends", "ffmpeg"],
        timeout=900,
    )
    return install_code, update_output + "\n" + install_output


#install_opencv
def install_opencv():
    existing = get_opencv_version()
    if existing:
        return 0, f"OpenCV is already installed: {existing}"

    return run_pip_install(
        [f"opencv-python-headless=={OPENCV_VERSION}"],
        timeout=600,
    )


#install_pyav
def install_pyav():
    return run_pip_install(["av>=16.0.0"], timeout=600)


#install_insightface
def install_insightface():
    info = optional_tool_info("insightface")
    if not info["interactive"]:
        return 1, info.get("detail") or "InsightFace prerequisites are not ready."

    safe_dependencies = [
        "onnx",
        "tqdm",
        "requests",
        "scikit-image",
        "easydict",
        "cython",
        "albumentations",
        "prettytable",
    ]

    deps_code, deps_output = run_pip_install(safe_dependencies, timeout=900)
    if deps_code != 0:
        return deps_code, deps_output

    install_code, install_output = run_pip_install(
        [f"insightface=={INSIGHTFACE_VERSION}"],
        extra_args=["--no-deps"],
        timeout=1800,
    )
    return install_code, deps_output + "\n" + install_output


#install_tool
def install_tool(tool_key):
    installers = {
        "sage": install_sage,
        "comfy_kitchen": install_comfy_kitchen,
        "flash": install_flash_attention,
        "xformers": install_xformers,
        "onnx": install_onnx_runtime,
        "ffmpeg": install_ffmpeg,
        "opencv": install_opencv,
        "pyav": install_pyav,
        "insightface": install_insightface,
    }

    installer = installers.get(tool_key)
    if installer is None:
        return 1, "No installer is registered for this component."

    return installer()


#verify_tool
def verify_tool(tool_key):
    try:
        if tool_key == "sage":
            import sageattention
            return bool(sageattention)

        if tool_key == "comfy_kitchen":
            import comfy_kitchen
            return bool(comfy_kitchen)

        if tool_key == "flash":
            from flash_attn import flash_attn_func
            return callable(flash_attn_func)

        if tool_key == "xformers":
            import xformers
            import xformers.ops
            return bool(xformers)

        if tool_key == "onnx":
            import onnxruntime as ort
            return "CUDAExecutionProvider" in ort.get_available_providers()

        if tool_key == "ffmpeg":
            return get_ffmpeg_version() is not None

        if tool_key == "opencv":
            import cv2
            return bool(cv2.__version__)

        if tool_key == "pyav":
            import av
            return bool(av.__version__)

        if tool_key == "insightface":
            import insightface
            return bool(insightface)
    except Exception:
        return False

    return False


#get_tool_info
def get_tool_info(tool_key):
    if tool_key in {"sage", "comfy_kitchen", "flash", "xformers", "triton"}:
        return attention_tool_info(tool_key)
    return optional_tool_info(tool_key)


#perform_install
def perform_install(tool_key):
    initial = get_tool_info(tool_key)
    installing = dict(initial)
    installing.update(
        state="installing",
        status="Installing...",
        button="Installing...",
        interactive=False,
    )

    yield (
        tool_status_html(installing),
        gr.update(value="Installing...", interactive=False),
        log_html(f"Installing {initial['name']}..."),
    )

    code, output = install_tool(tool_key)
    verified = code == 0 and verify_tool(tool_key)

    check_code, check_output = pip_check()
    full_output = output
    if check_output:
        full_output += f"\n\n[pip check]\n{check_output}"

    if code == 0 and verified:
        refreshed = get_tool_info(tool_key)
        if check_code != 0:
            full_output += "\n\nInstalled and verified, but pip check reports dependency warnings."
        else:
            full_output += "\n\nInstallation verified successfully."

        yield (
            tool_status_html(refreshed),
            gr.update(value="Installed", interactive=False),
            log_html(full_output),
        )
        return

    failed = dict(initial)
    failed.update(
        state="failed",
        status="Install Failed",
        button="Retry",
        interactive=True,
    )

    if code == 0 and not verified:
        full_output += "\n\nPackage installation completed, but runtime verification failed."

    yield (
        tool_status_html(failed),
        gr.update(value="Retry", interactive=True),
        log_html(full_output),
    )


#get_storage_info
def get_storage_info(file_root):
    root = Path(file_root or "/workspace")
    if not root.exists():
        root = Path("/")

    try:
        usage = shutil.disk_usage(root)
        total = usage.total / (1024 ** 3)
        used = usage.used / (1024 ** 3)
        free = usage.free / (1024 ** 3)
        percent = (usage.used / usage.total * 100) if usage.total else 0
        return str(root), used, total, free, percent
    except Exception:
        return str(root), 0, 0, 0, 0


#get_dashboard_html
def get_dashboard_html(file_root):
    cpu_usage = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()

    ram_used = ram.used / (1024 ** 3)
    ram_total = ram.total / (1024 ** 3)
    ram_available = ram.available / (1024 ** 3)

    gpu_used = 0
    gpu_total = 0
    gpu_percent = 0

    if GPU_HANDLE is not None:
        try:
            memory = pynvml.nvmlDeviceGetMemoryInfo(GPU_HANDLE)
            gpu_used = memory.used / (1024 ** 3)
            gpu_total = memory.total / (1024 ** 3)
            if memory.total:
                gpu_percent = (memory.used / memory.total) * 100
        except Exception:
            pass

    storage_path, storage_used, storage_total, storage_free, storage_percent = get_storage_info(file_root)
    torch_display = getattr(torch, "__version__", "Unavailable") if torch else "Unavailable"
    cuda_display = cuda_version() or "Unavailable"

    return f"""
    <div class="console-head">
        <div>
            <div class="console-title">COMFY CONSOLE</div>
            <div class="console-subtitle">Lightweight runtime console</div>
        </div>
        <div class="system-ready"><span></span>SYSTEM READY</div>
    </div>

    <div class="section-label">SYSTEM</div>
    <div class="metric-grid">
        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">CPU</span>
                <span class="metric-percent">{cpu_usage:.1f}%</span>
            </div>
            <div class="metric-name">{html.escape(CPU_NAME)}</div>
            <div class="bar"><div style="width:{min(cpu_usage, 100):.1f}%"></div></div>
            <div class="metric-foot">{psutil.cpu_count(logical=True) or 0} logical processors</div>
        </section>

        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">RAM</span>
                <span class="metric-percent">{ram.percent:.1f}%</span>
            </div>
            <div class="metric-name">{ram_used:.1f} / {ram_total:.1f} GB</div>
            <div class="bar"><div style="width:{min(ram.percent, 100):.1f}%"></div></div>
            <div class="metric-foot">{ram_available:.1f} GB available</div>
        </section>

        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">GPU</span>
                <span class="metric-percent">{gpu_percent:.1f}%</span>
            </div>
            <div class="metric-name">{html.escape(GPU_NAME)}</div>
            <div class="bar"><div style="width:{min(gpu_percent, 100):.1f}%"></div></div>
            <div class="metric-foot">{gpu_used:.1f} / {gpu_total:.1f} GB VRAM</div>
        </section>
    </div>

    <div class="section-label section-gap">RUNTIME</div>
    <section class="runtime-panel">
        <div class="runtime-item"><span>Python</span><strong>{html.escape(platform.python_version())}</strong></div>
        <div class="runtime-item"><span>PyTorch</span><strong>{html.escape(torch_display)}</strong></div>
        <div class="runtime-item"><span>CUDA</span><strong>{html.escape(str(cuda_display))}</strong></div>
        <div class="runtime-item"><span>NVIDIA Driver</span><strong>{html.escape(str(NVIDIA_DRIVER))}</strong></div>
        <div class="runtime-item"><span>cuDNN</span><strong>{html.escape(get_cudnn_version())}</strong></div>
        <div class="runtime-item"><span>GPU Compute</span><strong>{html.escape(get_gpu_compute_info())}</strong></div>
    </section>

    <div class="section-label section-gap">STORAGE</div>
    <section class="storage-panel">
        <div class="storage-head">
            <span>Workspace</span>
            <strong>{storage_used:.1f} / {storage_total:.1f} GB</strong>
        </div>
        <div class="bar storage-bar"><div style="width:{min(storage_percent, 100):.1f}%"></div></div>
        <div class="storage-foot">
            <span>{html.escape(storage_path)}</span>
            <span>{storage_free:.1f} GB free</span>
        </div>
    </section>
    """


#section_title_html
def section_title_html(title, subtitle=None):
    subtitle_html = f'<div class="section-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    return f'<div class="section-title-block"><div class="section-label">{html.escape(title)}</div>{subtitle_html}</div>'


#active_attention_html
def active_attention_html():
    return f"""
    <div class="active-attention">
        <span>Active Attention</span>
        <strong>{html.escape(get_active_attention())}</strong>
    </div>
    """


#create_tool_row
def create_tool_row(tool_key):
    info = get_tool_info(tool_key)
    with gr.Row(elem_classes=["tool-row"]):
        status = gr.HTML(tool_status_html(info), elem_classes=["tool-status-wrap"])
        button = gr.Button(
            info["button"],
            interactive=info["interactive"],
            elem_classes=["tool-button"],
        )
    return tool_key, status, button


#create_optional_card
def create_optional_card(tool_key):
    info = get_tool_info(tool_key)
    with gr.Column(elem_classes=["optional-card"]):
        status = gr.HTML(tool_status_html(info), elem_classes=["optional-status-wrap"])
        button = gr.Button(
            info["button"],
            interactive=info["interactive"],
            elem_classes=["optional-button"],
        )
    return tool_key, status, button


#bind_installer
def bind_installer(binding, log_output):
    tool_key, status, button = binding
    button.click(
        fn=partial(perform_install, tool_key),
        inputs=[],
        outputs=[status, button, log_output],
        show_progress="hidden",
    )


#refresh_dashboard
def refresh_dashboard(file_root):
    return get_dashboard_html(file_root), active_attention_html()


#create_dashboard
def create_dashboard(file_root, visible=True):
    with gr.Column(
        visible=visible,
        elem_classes=["page", "dashboard-page"],
    ) as page:
        dashboard = gr.HTML(get_dashboard_html(file_root))
        bindings = []

        gr.HTML(section_title_html("ACCELERATION"))
        with gr.Column(elem_classes=["acceleration-panel"]):
            active_attention = gr.HTML(active_attention_html())
            bindings.append(create_tool_row("sage"))
            bindings.append(create_tool_row("comfy_kitchen"))
            bindings.append(create_tool_row("flash"))
            bindings.append(create_tool_row("xformers"))
            bindings.append(create_tool_row("triton"))

        gr.HTML(section_title_html("OPTIONAL TOOLS", "Install only what your workflow needs."))
        with gr.Row(elem_classes=["optional-grid"]):
            bindings.append(create_optional_card("onnx"))
            bindings.append(create_optional_card("ffmpeg"))
            bindings.append(create_optional_card("opencv"))
            bindings.append(create_optional_card("pyav"))
            bindings.append(create_optional_card("insightface"))

        gr.HTML(section_title_html("INSTALL LOG"))
        log_output = gr.HTML(log_html("Ready. Select an optional component to install."))

        for binding in bindings:
            bind_installer(binding, log_output)

        timer = gr.Timer(value=1.0, active=True)
        timer.tick(
            fn=partial(refresh_dashboard, file_root),
            inputs=[],
            outputs=[dashboard, active_attention],
            show_progress="hidden",
        )

    return page


CPU_NAME = get_cpu_name()
init_gpu_info()
