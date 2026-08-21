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

log_lock = threading.Lock()
tunnel_logs = ["Ready."]
comfy_logs = ["Ready."]
active_log_view = "Logs B - ComfyUI"


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


def _reset_logs(provider):
    global tunnel_logs
    global comfy_logs

    with log_lock:
        tunnel_logs = []
        comfy_logs = []

        if provider == "Platform Proxy":
            tunnel_logs.append("[INFO] Platform Proxy selected - tunnel process disabled")


def _append_log(source, message):
    with log_lock:
        target = tunnel_logs if source == "tunnel" else comfy_logs
        target.append(message)


def _get_log_text(view):
    with log_lock:
        if view == "Logs A - Tunnel":
            return "\n".join(tunnel_logs) or "Waiting for tunnel logs..."

        return "\n".join(comfy_logs) or "Waiting for ComfyUI logs..."


def select_log(view):
    global active_log_view
    active_log_view = view or "Logs B - ComfyUI"
    return _get_log_text(active_log_view)


def _stream_comfy(process, log_queue):
    try:
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.rstrip()
            if line:
                log_queue.put(("comfy", line))
    finally:
        log_queue.put(("comfy", None))


def _stream_tunnel(process, tunnel_state, log_queue):
    try:
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue

            log_queue.put(("tunnel", line))

            url = _extract_public_url(line)
            if url:
                tunnel_state["public_url"] = url
    finally:
        tunnel_state["finished"] = True
        tunnel_state["return_code"] = process.poll()
        log_queue.put(("tunnel", None))


def _stop_all():
    global comfy_process
    global tunnel_process

    current_tunnel = tunnel_process
    current_comfy = comfy_process

    tunnel_process = None
    comfy_process = None

    _kill_process(current_tunnel)
    _kill_process(current_comfy)


def _release_processes(current_comfy, current_tunnel):
    global comfy_process
    global tunnel_process

    _kill_process(current_tunnel)
    _kill_process(current_comfy)

    if tunnel_process is current_tunnel:
        tunnel_process = None

    if comfy_process is current_comfy:
        comfy_process = None


def stop_comfy(log_view):
    was_running = (
        comfy_process is not None
        and comfy_process.poll() is None
    )

    had_tunnel = (
        tunnel_process is not None
        and tunnel_process.poll() is None
    )

    _stop_all()

    if was_running:
        _append_log("comfy", "[INFO] ComfyUI stopped")

    if had_tunnel:
        _append_log("tunnel", "[INFO] Tunnel stopped")

    return (
        _get_log_text(log_view),
        "",
        _status_html(False),
        gr.update(interactive=True, variant="primary"),
        gr.update(interactive=False, variant="stop")
    )


def _start_comfy(
    provider,
    token,
    start_command,
    log_view
):
    global comfy_process
    global tunnel_process

    if (
        comfy_process is not None
        and comfy_process.poll() is None
    ):
        yield (
            _get_log_text(log_view),
            "",
            _status_html(True),
            gr.update(interactive=False, variant="primary"),
            gr.update(interactive=True, variant="stop")
        )
        return

    provider = provider or "Platform Proxy"
    start_command = (start_command or "").strip()
    log_view = log_view or "Logs B - ComfyUI"
    public_url = ""

    _reset_logs(provider)
    log_queue = queue.Queue()
    tunnel_state = {
        "public_url": "",
        "finished": False,
        "return_code": None
    }

    if not start_command:
        _append_log("comfy", "[ERROR] Start command is required")
        yield (
            _get_log_text(log_view),
            "",
            _status_html(False),
            gr.update(interactive=True, variant="primary"),
            gr.update(interactive=False, variant="stop")
        )
        return

    try:
        tunnel_cmd = _build_tunnel(provider, token)
    except Exception as error:
        _append_log("tunnel", f"[ERROR] {error}")
        yield (
            _get_log_text(log_view),
            "",
            _status_html(False),
            gr.update(interactive=True, variant="primary"),
            gr.update(interactive=False, variant="stop")
        )
        return

    _append_log("comfy", "[INFO] Starting ComfyUI")
    _append_log("comfy", f"[CMD] {start_command}")

    yield (
        _get_log_text(log_view),
        "",
        _status_html(False),
        gr.update(interactive=False, variant="primary"),
        gr.update(interactive=False, variant="stop")
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
        _append_log("comfy", f"[ERROR] Failed to start ComfyUI: {error}")
        yield (
            _get_log_text(log_view),
            "",
            _status_html(False),
            gr.update(interactive=True, variant="primary"),
            gr.update(interactive=False, variant="stop")
        )
        return

    current_comfy = comfy_process
    current_tunnel = None

    threading.Thread(
        target=_stream_comfy,
        args=(current_comfy, log_queue),
        daemon=True
    ).start()

    if provider == "Platform Proxy":
        public_url = _runpod_url()
        _append_log("comfy", "[INFO] ComfyUI listening on port 8188")
    else:
        _append_log("tunnel", f"[INFO] Starting {provider}")

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
            _append_log("tunnel", f"[ERROR] Failed to start tunnel: {error}")
            _stop_all()
            yield (
                _get_log_text(log_view),
                "",
                _status_html(False),
                gr.update(interactive=True, variant="primary"),
                gr.update(interactive=False, variant="stop")
            )
            return

        current_tunnel = tunnel_process

        threading.Thread(
            target=_stream_tunnel,
            args=(current_tunnel, tunnel_state, log_queue),
            daemon=True
        ).start()

    yield (
        _get_log_text(log_view),
        public_url,
        _status_html(True),
        gr.update(interactive=False, variant="primary"),
        gr.update(interactive=True, variant="stop")
    )

    while current_comfy.poll() is None:
        if comfy_process is not current_comfy:
            return

        tunnel_url = tunnel_state.get("public_url", "")
        url_changed = bool(tunnel_url and tunnel_url != public_url)

        if url_changed:
            public_url = tunnel_url

        try:
            source, line = log_queue.get(timeout=0.25)
        except queue.Empty:
            if url_changed:
                yield (
                    _get_log_text(active_log_view),
                    public_url,
                    _status_html(True),
                    gr.update(interactive=False, variant="primary"),
                    gr.update(interactive=True, variant="stop")
                )
            continue

        if line is not None:
            _append_log(source, line)

        yield (
            _get_log_text(active_log_view),
            public_url,
            _status_html(True),
            gr.update(interactive=False, variant="primary"),
            gr.update(interactive=True, variant="stop")
        )

    if comfy_process is not current_comfy:
        return

    return_code = current_comfy.poll()
    _append_log("comfy", f"[INFO] ComfyUI exited with code {return_code}")

    if current_tunnel is not None:
        _append_log("tunnel", "[INFO] Tunnel stopped because ComfyUI exited")

    _release_processes(current_comfy, current_tunnel)

    yield (
        _get_log_text(active_log_view),
        public_url,
        _status_html(False),
        gr.update(interactive=True, variant="primary"),
        gr.update(interactive=False, variant="stop")
    )


def restart_comfy(
    provider,
    token,
    start_command,
    log_view
):
    _stop_all()

    yield from _start_comfy(
        provider,
        token,
        start_command,
        log_view
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
                interactive=True,
                elem_classes=["comfy-start-button"]
            )

            stop_button = gr.Button(
                "Stop",
                variant="stop",
                interactive=False,
                elem_classes=["comfy-stop-button"]
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

        log_view = gr.Radio(
            choices=[
                "Logs A - Tunnel",
                "Logs B - ComfyUI"
            ],
            value="Logs B - ComfyUI",
            show_label=False,
            elem_classes=["comfy-log-selector"]
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

        log_view.change(
            fn=select_log,
            inputs=log_view,
            outputs=logs,
            queue=False
        )

        start_button.click(
            fn=_start_comfy,
            inputs=[
                provider,
                token,
                start_command,
                log_view
            ],
            outputs=[
                logs,
                public_url,
                status,
                start_button,
                stop_button
            ],
            concurrency_limit=None,
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

        stop_button.click(
            fn=stop_comfy,
            inputs=log_view,
            outputs=[
                logs,
                public_url,
                status,
                start_button,
                stop_button
            ],
            concurrency_limit=None
        )

        restart_button.click(
            fn=restart_comfy,
            inputs=[
                provider,
                token,
                start_command,
                log_view
            ],
            outputs=[
                logs,
                public_url,
                status,
                start_button,
                stop_button
            ],
            concurrency_limit=None
        )

    return page
