import html
import importlib.metadata
import os
import platform
import subprocess
import sys

import gradio as gr
import psutil
import pynvml

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


def get_cpu_name():
    name = platform.processor().strip()

    if name:
        return name

    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    count = psutil.cpu_count(logical=True) or 0
    return f"{count} logical CPUs"


CPU_NAME = get_cpu_name()
GPU_HANDLE = None
GPU_NAME = "No NVIDIA GPU"
NVIDIA_DRIVER = "Unavailable"

try:
    pynvml.nvmlInit()

    if pynvml.nvmlDeviceGetCount() > 0:
        GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
        GPU_NAME = pynvml.nvmlDeviceGetName(GPU_HANDLE)
        NVIDIA_DRIVER = pynvml.nvmlSystemGetDriverVersion()

        if isinstance(GPU_NAME, bytes):
            GPU_NAME = GPU_NAME.decode("utf-8")

        if isinstance(NVIDIA_DRIVER, bytes):
            NVIDIA_DRIVER = NVIDIA_DRIVER.decode("utf-8")
except Exception:
    GPU_HANDLE = None


TORCH_VERSION = getattr(torch, "__version__", "Unavailable") if torch else "Unavailable"
CUDA_VERSION = (
    getattr(getattr(torch, "version", None), "cuda", None) or "Unavailable"
    if torch
    else "Unavailable"
)


def _base_torch_version():
    if not torch:
        return None
    return str(getattr(torch, "__version__", "")).split("+", 1)[0]


def _python_minor():
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _python_tag():
    return f"{sys.version_info.major}{sys.version_info.minor}"


def _cuda_version():
    if not torch:
        return None
    return getattr(getattr(torch, "version", None), "cuda", None)


def _cuda_tag(cuda_version):
    if not cuda_version:
        return None
    parts = str(cuda_version).split(".")
    if len(parts) < 2:
        return None
    return f"cu{parts[0]}{parts[1]}"


def _sm_arch():
    if not torch or not torch.cuda.is_available():
        return None

    try:
        major, minor = torch.cuda.get_device_capability(0)
        return f"{major}{minor}"
    except Exception:
        return None


def _sage_installed_version():
    try:
        return importlib.metadata.version("sageattention")
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def get_sage_info():
    installed = _sage_installed_version()
    torch_version = _base_torch_version()
    cuda_version = _cuda_version()
    python_version = _python_minor()
    sm = _sm_arch()

    detail_parts = []

    if torch_version:
        detail_parts.append(f"Torch {torch_version}")
    if cuda_version:
        detail_parts.append(f"CUDA {cuda_version}")
    if sm:
        detail_parts.append(f"SM{sm}")

    detail = " · ".join(detail_parts) or "Environment unavailable"

    if installed:
        return {
            "state": "installed",
            "title": f"Installed · {installed}",
            "detail": detail,
            "button": "Installed",
            "interactive": False,
        }

    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        return {
            "state": "unavailable",
            "title": "No compatible prebuilt",
            "detail": detail,
            "button": "Unavailable",
            "interactive": False,
        }

    if not torch_version or not cuda_version or not sm:
        return {
            "state": "unavailable",
            "title": "No compatible prebuilt",
            "detail": detail,
            "button": "Unavailable",
            "interactive": False,
        }

    supported_sms = SAGE_MATRIX.get((torch_version, str(cuda_version), python_version))

    if not supported_sms or sm not in supported_sms:
        return {
            "state": "unavailable",
            "title": "No compatible prebuilt",
            "detail": detail,
            "button": "Unavailable",
            "interactive": False,
        }

    return {
        "state": "ready",
        "title": "Not installed",
        "detail": detail,
        "button": "Install Prebuilt",
        "interactive": True,
    }


def sage_status_html(info=None):
    info = info or get_sage_info()
    state = html.escape(info["state"])
    title = html.escape(info["title"])
    detail = html.escape(info["detail"])

    return f"""
    <div class="sage-status sage-{state}">
        <span>SageAttention</span>
        <strong>{title}</strong>
        <small>{detail}</small>
    </div>
    """


def _sage_wheel_url():
    torch_version = _base_torch_version()
    cuda_version = _cuda_version()
    python_version = _python_minor()
    python_tag = _python_tag()
    sm = _sm_arch()
    cuda_tag = _cuda_tag(cuda_version)

    if not all((torch_version, cuda_version, python_version, python_tag, sm, cuda_tag)):
        return None

    supported_sms = SAGE_MATRIX.get((torch_version, str(cuda_version), python_version))
    if not supported_sms or sm not in supported_sms:
        return None

    release = (
        f"sage-{SAGE_VERSION}-torch-{torch_version}-"
        f"{cuda_tag}-py{python_tag}"
    )
    wheel = (
        f"sageattention-{SAGE_VERSION}-{sm}-"
        f"cp{python_tag}-cp{python_tag}-linux_x86_64.whl"
    )

    return (
        f"https://github.com/{SAGE_REPO}/releases/download/"
        f"{release}/{wheel}"
    )


def install_sageattention():
    info = get_sage_info()

    if info["state"] == "installed":
        yield sage_status_html(info), gr.update(
            value="Installed",
            interactive=False,
        )
        return

    wheel_url = _sage_wheel_url()

    if not wheel_url:
        unavailable = get_sage_info()
        yield sage_status_html(unavailable), gr.update(
            value="Unavailable",
            interactive=False,
        )
        return

    installing = {
        "state": "installing",
        "title": "Installing prebuilt...",
        "detail": info["detail"],
    }

    yield sage_status_html(installing), gr.update(
        value="Installing...",
        interactive=False,
    )

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-deps",
                wheel_url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            failed = {
                "state": "failed",
                "title": "Install failed",
                "detail": info["detail"],
            }
            yield sage_status_html(failed), gr.update(
                value="Retry Install",
                interactive=True,
            )
            return

        installed = _sage_installed_version() or SAGE_VERSION
        done = {
            "state": "installed",
            "title": f"Installed · {installed}",
            "detail": info["detail"],
        }
        yield sage_status_html(done), gr.update(
            value="Installed",
            interactive=False,
        )

    except Exception:
        failed = {
            "state": "failed",
            "title": "Install failed",
            "detail": info["detail"],
        }
        yield sage_status_html(failed), gr.update(
            value="Retry Install",
            interactive=True,
        )


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

    return f"""
    <div class="page-head">
        <div>
            <div class="eyebrow">SYSTEM</div>
            <h1>Dashboard</h1>
            <p>Container resource overview</p>
        </div>
    </div>

    <div class="metric-grid">
        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">CPU</span>
                <span class="metric-percent">{cpu_usage:.1f}%</span>
            </div>

            <div class="metric-name">{html.escape(CPU_NAME)}</div>

            <div class="bar">
                <div style="width: {min(cpu_usage, 100):.1f}%"></div>
            </div>

            <div class="metric-foot">
                {psutil.cpu_count(logical=True) or 0} logical processors
            </div>
        </section>

        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">RAM</span>
                <span class="metric-percent">{ram.percent:.1f}%</span>
            </div>

            <div class="metric-name">{ram_used:.1f} / {ram_total:.1f} GB</div>

            <div class="bar">
                <div style="width: {min(ram.percent, 100):.1f}%"></div>
            </div>

            <div class="metric-foot">{ram_available:.1f} GB available</div>
        </section>

        <section class="metric-card">
            <div class="metric-header">
                <span class="metric-tag">GPU</span>
                <span class="metric-percent">{gpu_percent:.1f}%</span>
            </div>

            <div class="metric-name">{html.escape(GPU_NAME)}</div>

            <div class="bar">
                <div style="width: {min(gpu_percent, 100):.1f}%"></div>
            </div>

            <div class="metric-foot">{gpu_used:.1f} / {gpu_total:.1f} GB VRAM</div>
        </section>
    </div>
    """


def info_item(label, value):
    return f"""
    <div class="system-info-item">
        <span>{html.escape(label)}</span>
        <strong>{html.escape(str(value))}</strong>
    </div>
    """


def create_dashboard(file_root, visible=True):
    sage_info = get_sage_info()

    with gr.Column(
        visible=visible,
        elem_classes=["page", "dashboard-page"]
    ) as page:
        dashboard = gr.HTML(get_dashboard_html(file_root))

        with gr.Row(elem_classes=["info-panel"]):
            gr.HTML(info_item("Python", platform.python_version()))
            gr.HTML(info_item("PyTorch", TORCH_VERSION))
            gr.HTML(info_item("CUDA", CUDA_VERSION))
            gr.HTML(info_item("NVIDIA Driver", NVIDIA_DRIVER))

            with gr.Column(elem_classes=["sage-card"]):
                sage_status = gr.HTML(sage_status_html(sage_info))
                sage_button = gr.Button(
                    sage_info["button"],
                    interactive=sage_info["interactive"],
                    elem_classes=["sage-install-button"],
                )

        sage_button.click(
            fn=install_sageattention,
            inputs=[],
            outputs=[sage_status, sage_button],
            show_progress="hidden",
        )

        timer = gr.Timer(value=1.0, active=True)
        timer.tick(
            fn=lambda: get_dashboard_html(file_root),
            inputs=[],
            outputs=dashboard,
            show_progress="hidden"
        )

    return page