import os
import re
import queue
import shutil
import signal
import subprocess
import threading

import gradio as gr


COMFY_DIR = "/workspace/ComfyUI"

comfy_process = None
tunnel_process = None


def _toggle_token(provider):
    if provider in ("Platform Proxy", "Quick Tunnel"):
        return gr.update(
            visible=False,
            value=""
        )

    if provider == "Ngrok":
        return gr.update(
            visible=True,
            label="Ngrok Auth Token",
            placeholder="Enter ngrok auth token",
            value=""
        )

    return gr.update(
        visible=True,
        label="Zrok Token",
        placeholder="Enter zrok environment token",
        value=""
    )


def _status_html(running):
    if running:
        return """
        <div class="comfy-status running">
            <span></span>
            Running
        </div>
        """

    return """
    <div class="comfy-status stopped">
        <span></span>
        Stopped
    </div>
    """


def _kill_process(process):
    if not process:
        return

    try:
        if process.poll() is None:
            os.killpg(
                os.getpgid(process.pid),
                signal.SIGTERM
            )

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL
                )
                process.wait()
    except Exception:
        pass


def _runpod_url():
    pod_id = os.environ.get("RUNPOD_POD_ID")

    if pod_id:
        return f"https://{pod_id}-8188.proxy.runpod.net"

    return "Platform Proxy (port 8188)"


def _extract_public_url(line):
    patterns = [
        r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9.-]+\.ngrok-free\.app",
        r"https://[a-zA-Z0-9.-]+\.ngrok\.io",
        r"https://[a-zA-Z0-9.-]+\.share\.zrok\.io",
    ]

    for pattern in patterns:
        match = re.search(pattern, line)

        if match:
            return match.group(0)

    return None


def _build_tunnel(provider, token):
    token = (token or "").strip()

    if provider == "Platform Proxy":
        return None

    if provider == "Quick Tunnel":
        if shutil.which("cloudflared") is None:
            raise RuntimeError(
                "cloudflared is not installed"
            )

        return [
            "cloudflared",
            "tunnel",
            "--url",
            "http://127.0.0.1:8188",
            "--no-autoupdate"
        ]

    if provider == "Ngrok":
        if shutil.which("ngrok") is None:
            raise RuntimeError(
                "ngrok is not installed"
            )

        if not token:
            raise RuntimeError(
                "Ngrok auth token is required"
            )

        subprocess.run(
            [
                "ngrok",
                "config",
                "add-authtoken",
                token
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        return [
            "ngrok",
            "http",
            "8188",
            "--log",
            "stdout"
        ]

    if provider == "Zrok":
        if shutil.which("zrok2") is None:
            raise RuntimeError(
                "zrok2 is not installed"
            )

        if not token:
            raise RuntimeError(
                "Zrok token is required"
            )

        subprocess.run(
            [
                "zrok2",
                "enable",
                token
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        return [
            "zrok2",
            "share",
            "public",
            "http://127.0.0.1:8188",
            "--headless"
        ]

    raise RuntimeError(
        "Unknown tunnel provider"
    )


def _stream_process(process, source, log_queue):
    try:
        for raw_line in iter(
            process.stdout.readline,
            ""
        ):
            line = raw_line.rstrip()

            if line:
                log_queue.put(
                    (source, line)
                )
    finally:
        log_queue.put(
            (source, None)
        )


def _stop_all():
    global comfy_process
    global tunnel_process

    _kill_process(tunnel_process)
    _kill_process(comfy_process)

    tunnel_process = None
    comfy_process = None


def toggle_comfy(
    provider,
    token,
    start_command
):
    global comfy_process
    global tunnel_process

    if (
        comfy_process is not None
        and comfy_process.poll() is None
    ):
        _stop_all()

        yield (
            "[INFO] ComfyUI stopped.",
            "",
            _status_html(False),
            gr.update(
                value="Start",
                variant="primary"
            )
        )

        return

    yield from _start_comfy(
        provider,
        token,
        start_command
    )


def _start_comfy(
    provider,
    token,
    start_command
):
    global comfy_process
    global tunnel_process

    logs = []
    log_queue = queue.Queue()

    provider = provider or "Platform Proxy"
    start_command = (start_command or "").strip()

    public_url = ""

    def emit(message):
        logs.append(message)
        return "\n".join(logs)

    if not start_command:
        yield (
            emit(
                "[ERROR] Start command is required"
            ),
            "",
            _status_html(False),
            gr.update(
                value="Start",
                variant="primary"
            )
        )
        return

    try:
        tunnel_cmd = _build_tunnel(
            provider,
            token
        )
    except Exception as error:
        yield (
            emit(f"[ERROR] {error}"),
            "",
            _status_html(False),
            gr.update(
                value="Start",
                variant="primary"
            )
        )
        return

    yield (
        emit("[INFO] Starting ComfyUI"),
        "",
        _status_html(False),
        gr.update(
            value="Starting...",
            interactive=False
        )
    )

    yield (
        emit(
            f"[CMD] {start_command}"
        ),
        "",
        _status_html(False),
        gr.update(
            interactive=False
        )
    )

    try:
        comfy_process = subprocess.Popen(
            start_command,
            cwd=COMFY_DIR,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid
        )

    except Exception as error:
        comfy_process = None

        yield (
            emit(
                f"[ERROR] Failed to start ComfyUI: {error}"
            ),
            "",
            _status_html(False),
            gr.update(
                value="Start",
                interactive=True,
                variant="primary"
            )
        )

        return

    threading.Thread(
        target=_stream_process,
        args=(
            comfy_process,
            "COMFY",
            log_queue
        ),
        daemon=True
    ).start()

    if provider == "Platform Proxy":

        public_url = _runpod_url()

        yield (
            emit(
                "[INFO] Tunnel disabled"
            ),
            public_url,
            _status_html(True),
            gr.update(
                value="Stop",
                interactive=True,
                variant="stop"
            )
        )

        yield (
            emit(
                "[INFO] ComfyUI listening on port 8188"
            ),
            public_url,
            _status_html(True),
            gr.update(
                value="Stop",
                variant="stop"
            )
        )

    else:
        yield (
            emit(
                f"[INFO] Starting {provider}"
            ),
            "",
            _status_html(True),
            gr.update(
                value="Stop",
                interactive=True,
                variant="stop"
            )
        )

        try:
            tunnel_process = subprocess.Popen(
                tunnel_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid
            )

        except Exception as error:
            _stop_all()

            yield (
                emit(
                    f"[ERROR] Failed to start tunnel: {error}"
                ),
                "",
                _status_html(False),
                gr.update(
                    value="Start",
                    interactive=True,
                    variant="primary"
                )
            )

            return

        threading.Thread(
            target=_stream_process,
            args=(
                tunnel_process,
                "TUNNEL",
                log_queue
            ),
            daemon=True
        ).start()

    while (
        comfy_process is not None
        and comfy_process.poll() is None
    ):
        try:
            source, line = log_queue.get(
                timeout=0.25
            )

        except queue.Empty:
            continue

        if line is None:
            continue

        url = _extract_public_url(line)

        if url:
            public_url = url

        yield (
            emit(
                f"[{source}] {line}"
            ),
            public_url,
            _status_html(True),
            gr.update(
                value="Stop",
                variant="stop",
                interactive=True
            )
        )

    return_code = (
        comfy_process.poll()
        if comfy_process
        else None
    )

    _stop_all()

    yield (
        emit(
            f"[INFO] ComfyUI exited with code {return_code}"
        ),
        public_url,
        _status_html(False),
        gr.update(
            value="Start",
            interactive=True,
            variant="primary"
        )
    )


def restart_comfy(
    provider,
    token,
    start_command
):
    _stop_all()

    yield from _start_comfy(
        provider,
        token,
        start_command
    )


def create_comfyui(visible=False):
    with gr.Column(
        visible=visible,
        elem_classes=[
            "page",
            "comfyui-page"
        ]
    ) as page:

        gr.HTML("""
        <div class="page-head comfy-page-head">
            <div>
                <div class="eyebrow">APPLICATION</div>
                <h1>Configuration</h1>
                <p>Configure ComfyUI runtime and public access</p>
            </div>
        </div>
        """)

        # Ganti bagian gr.Accordion("Configuration", open=True, ...) menjadi:
        with gr.Column(
            elem_classes=["comfy-config"]
        ):
            # Header statis pengganti Accordion
            gr.HTML('<div class="comfy-config-header">Configuration</div>')
            
            with gr.Column(elem_classes=["comfy-config-body"]):
                provider = gr.Radio(
                    label="Access Method",
                    choices=[
                        "Platform Proxy",
                        "Zrok",
                        "Ngrok",
                        "Quick Tunnel"
                    ],
                    value="Platform Proxy",
                    elem_classes=["comfy-provider"]
                )

                token = gr.Textbox(
                    label="Token",
                    type="password",
                    placeholder="Enter token",
                    visible=False,
                    elem_classes=["comfy-input"]
                )

                start_command = gr.Textbox(
                    label="Start Command",
                    value="python main.py --listen 0.0.0.0 --port 8188",
                    placeholder="python main.py --listen 0.0.0.0 --port 8188 --lowvram",
                    elem_classes=["comfy-input"]
                )

                public_url = gr.Textbox(
                    label="Public URL",
                    value="",
                    placeholder="Public URL will appear here",
                    interactive=False,
                    elem_classes=["comfy-public-url"]
                )

        with gr.Row(
            elem_classes=["comfy-actions"]
        ):
            start_button = gr.Button(
                "Start",
                variant="primary",
                elem_classes=["comfy-start-button"]
            )

        with gr.Row(
            elem_classes=["comfy-log-header"]
        ):
            gr.HTML(
                '<div class="comfy-log-title">LOGS</div>'
            )

            with gr.Row(
                elem_classes=["comfy-log-controls"]
            ):
                status = gr.HTML(
                    _status_html(False)
                )

                restart_button = gr.Button(
                    "Restart",
                    elem_classes=["comfy-restart-button"]
                )

        logs = gr.Textbox(
            value="Ready.",
            lines=20,
            max_lines=20,
            interactive=False,
            show_label=False,
            container=False,
            elem_id="comfy-logs"
        )

        provider.change(
            fn=_toggle_token,
            inputs=provider,
            outputs=token,
            queue=False
        )

        start_button.click(
            fn=toggle_comfy,
            inputs=[
                provider,
                token,
                start_command
            ],
            outputs=[
                logs,
                public_url,
                status,
                start_button
            ],
            js="""(...args) => {
                const setupLogScroll = () => {
                    const textarea =
                        document.querySelector('#comfy-logs textarea');

                    if (!textarea) return false;

                    if (!textarea.dataset.smartScrollReady) {
                        textarea.dataset.smartScrollReady = '1';
                        textarea.dataset.followLogs = '1';

                        textarea.addEventListener('scroll', () => {
                            const distance =
                                textarea.scrollHeight -
                                textarea.scrollTop -
                                textarea.clientHeight;

                            textarea.dataset.followLogs =
                                distance <= 40 ? '1' : '0';
                        });
                    }

                    textarea.dataset.followLogs = '1';
                    textarea.scrollTop = textarea.scrollHeight;

                    return true;
                };

                if (window.comfyLogAutoScroll) {
                    clearInterval(window.comfyLogAutoScroll);
                }

                setupLogScroll();

                window.comfyLogAutoScroll = setInterval(() => {
                    const textarea =
                        document.querySelector('#comfy-logs textarea');

                    if (!textarea) return;

                    if (!textarea.dataset.smartScrollReady) {
                        setupLogScroll();
                        return;
                    }

                    if (textarea.dataset.followLogs === '1') {
                        textarea.scrollTop = textarea.scrollHeight;
                    }
                }, 250);

                return args;
            }"""
        )

        restart_button.click(
            fn=restart_comfy,
            inputs=[
                provider,
                token,
                start_command
            ],
            outputs=[
                logs,
                public_url,
                status,
                start_button
            ]
        )

    return page