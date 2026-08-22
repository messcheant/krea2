import os
import re
import shutil
import signal
import subprocess
import threading
from collections import deque

import gradio as gr


COMFY_DIR = "/workspace/ComfyUI"

comfy_process = None
tunnel_process = None

log_lock = threading.Lock()
LOG_LIMIT = 2000
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

tunnel_logs = deque(["Ready."], maxlen=LOG_LIMIT)
comfy_logs = deque(["Ready."], maxlen=LOG_LIMIT)
active_log_view = "ComfyUI"
state_lock = threading.Lock()
app_state = "stopped"
current_public_url = ""
current_provider = "Platform Proxy"
session_id = 0


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


def _status_html(state):
    labels = {
        "stopped": ("stopped", "Stopped"),
        "starting": ("starting", "Starting"),
        "running": ("running", "Running"),
        "shutting_down": ("shutting-down", "Shutting Down"),
        "restarting": ("restarting", "Restarting"),
        "error": ("error", "Error"),
    }

    css_class, label = labels.get(state, labels["stopped"])

    return f"""
    <div class="comfy-status {css_class}">
        <span></span>
        {label}
    </div>
    """


def _set_state(state):
    global app_state
    with state_lock:
        app_state = state


def _get_state():
    with state_lock:
        return app_state


def _button_updates(state):
    if state == "stopped" or state == "error":
        return (
            gr.update(interactive=True, variant="primary"),
            gr.update(interactive=False, variant="stop"),
            gr.update(interactive=False)
        )

    if state == "running":
        return (
            gr.update(interactive=False, variant="primary"),
            gr.update(interactive=True, variant="stop"),
            gr.update(interactive=True)
        )

    return (
        gr.update(interactive=False, variant="primary"),
        gr.update(interactive=False, variant="stop"),
        gr.update(interactive=False)
    )


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
        r"(?:https?://)?[a-zA-Z0-9.-]+\.shares\.zrok\.io",
        r"(?:https?://)?[a-zA-Z0-9.-]+\.share\.zrok\.io",
    ]

    for pattern in patterns:
        match = re.search(pattern, line)

        if match:
            url = match.group(0)
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            return url

    return None


def _zrok_environment_enabled():
    try:
        result = subprocess.run(
            ["zrok2", "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def _ensure_zrok_enabled(token):
    if _zrok_environment_enabled():
        return

    subprocess.run(
        ["zrok2", "enable", token],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )


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

        _ensure_zrok_enabled(token)

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
        tunnel_logs = deque(maxlen=LOG_LIMIT)
        comfy_logs = deque(maxlen=LOG_LIMIT)

        if provider == "Platform Proxy":
            tunnel_logs.append("[INFO] Platform Proxy selected - tunnel process disabled")


def _clean_log_line(message):
    if message is None:
        return ""
    return ANSI_ESCAPE.sub("", str(message)).replace("\r", "").rstrip()


def _append_log(source, message):
    line = _clean_log_line(message)
    if not line:
        return

    with log_lock:
        target = tunnel_logs if source == "tunnel" else comfy_logs
        target.append(line)


def _get_log_text(view):
    with log_lock:
        if view == "Tunnel":
            return "\n".join(tunnel_logs) or "Waiting for tunnel logs..."

        return "\n".join(comfy_logs) or "Waiting for ComfyUI logs..."


def select_log(view):
    global active_log_view
    active_log_view = view or "ComfyUI"
    return _get_log_text(active_log_view)


def _is_alive(process):
    return process is not None and process.poll() is None


def _invalidate_session():
    global session_id
    session_id += 1
    return session_id


def _kill_process(process, term_timeout=3):
    if not process:
        return

    try:
        if process.poll() is not None:
            return

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            process.wait(timeout=term_timeout)
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            return

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    except Exception:
        pass


def _stop_all(zrok_graceful=False):
    global comfy_process
    global tunnel_process
    global current_public_url

    _invalidate_session()

    current_tunnel = tunnel_process
    current_comfy = comfy_process

    tunnel_process = None
    comfy_process = None
    current_public_url = ""

    if zrok_graceful:
        _kill_process(current_tunnel, term_timeout=8)
    else:
        _kill_process(current_tunnel)

    _kill_process(current_comfy)


def _stream_comfy(process, this_session):
    global comfy_process
    global tunnel_process

    try:
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.rstrip()
            if line:
                _append_log("comfy", line)
    finally:
        return_code = process.poll()

        if this_session != session_id:
            return

        if comfy_process is process:
            comfy_process = None

            current_tunnel = tunnel_process
            tunnel_process = None
            _kill_process(current_tunnel)

            _append_log(
                "comfy",
                f"[INFO] ComfyUI exited with code {return_code}"
            )

            state = _get_state()
            if state not in ("shutting_down", "restarting"):
                _set_state("stopped")


def _stream_tunnel(process, this_session):
    global tunnel_process
    global current_public_url

    try:
        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue

            _append_log("tunnel", line)

            url = _extract_public_url(line)
            if url and this_session == session_id:
                current_public_url = url
    finally:
        if this_session != session_id:
            return

        if tunnel_process is process:
            tunnel_process = None

        return_code = process.poll()
        if _get_state() == "running":
            _append_log(
                "tunnel",
                f"[INFO] Tunnel exited with code {return_code}"
            )


def _recover_stale_state():
    state = _get_state()

    if state == "running" and not _is_alive(comfy_process):
        _set_state("stopped")
        return "stopped"

    if state in ("starting", "shutting_down", "restarting"):
        if not _is_alive(comfy_process) and not _is_alive(tunnel_process):
            _set_state("stopped")
            return "stopped"

    return state


def _spawn_session(provider, token, start_command):
    global comfy_process
    global tunnel_process
    global current_public_url
    global current_provider

    provider = provider or "Platform Proxy"
    current_provider = provider
    start_command = (start_command or "").strip()

    if not start_command:
        _append_log("comfy", "[ERROR] Start command is required")
        _set_state("error")
        return False

    try:
        tunnel_cmd = _build_tunnel(provider, token)
    except Exception as error:
        _append_log("tunnel", f"[ERROR] {error}")
        _set_state("error")
        return False

    this_session = _invalidate_session()
    current_public_url = ""

    _append_log("comfy", "[INFO] Starting ComfyUI")
    _append_log("comfy", f"[CMD] {start_command}")

    try:
        process = subprocess.Popen(
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
        _set_state("error")
        return False

    comfy_process = process

    threading.Thread(
        target=_stream_comfy,
        args=(process, this_session),
        daemon=True
    ).start()

    if provider == "Platform Proxy":
        current_public_url = _runpod_url()
        _append_log(
            "tunnel",
            "[INFO] Platform Proxy selected - tunnel process disabled"
        )
    else:
        _append_log("tunnel", f"[INFO] Starting {provider}")

        try:
            tunnel = subprocess.Popen(
                tunnel_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid
            )
        except Exception as error:
            _append_log("tunnel", f"[ERROR] Failed to start tunnel: {error}")
            comfy_process = None
            _kill_process(process)
            _set_state("error")
            return False

        tunnel_process = tunnel

        threading.Thread(
            target=_stream_tunnel,
            args=(tunnel, this_session),
            daemon=True
        ).start()

    _set_state("running")
    return True


def _ui_snapshot(log_view):
    state = _recover_stale_state()
    start_update, stop_update, restart_update = _button_updates(state)

    return (
        _get_log_text(log_view or active_log_view),
        current_public_url,
        _status_html(state),
        start_update,
        stop_update,
        restart_update
    )


def refresh_comfy_ui(log_view):
    return _ui_snapshot(log_view)


def start_comfy(provider, token, start_command, log_view):
    state = _recover_stale_state()

    if _is_alive(comfy_process):
        _set_state("running")
        yield _ui_snapshot(log_view)
        return

    if state in ("starting", "shutting_down", "restarting"):
        yield _ui_snapshot(log_view)
        return

    provider = provider or "Platform Proxy"
    _reset_logs(provider)
    _set_state("starting")

    start_update, stop_update, restart_update = _button_updates("starting")
    yield (
        _get_log_text(log_view),
        "",
        _status_html("starting"),
        start_update,
        stop_update,
        restart_update
    )

    _spawn_session(provider, token, start_command)
    yield _ui_snapshot(log_view)


def stop_comfy(log_view):
    state = _recover_stale_state()

    if state in ("starting", "shutting_down", "restarting"):
        yield _ui_snapshot(log_view)
        return

    was_running = _is_alive(comfy_process)
    had_tunnel = _is_alive(tunnel_process)

    if not was_running and not had_tunnel:
        _set_state("stopped")
        yield _ui_snapshot(log_view)
        return

    _set_state("shutting_down")
    _append_log("comfy", "[INFO] Shutting down ComfyUI...")
    if had_tunnel:
        _append_log("tunnel", "[INFO] Shutting down tunnel...")

    start_update, stop_update, restart_update = _button_updates("shutting_down")
    yield (
        _get_log_text(log_view),
        current_public_url,
        _status_html("shutting_down"),
        start_update,
        stop_update,
        restart_update
    )

    _stop_all()

    if was_running:
        _append_log("comfy", "[INFO] ComfyUI stopped")
    if had_tunnel:
        _append_log("tunnel", "[INFO] Tunnel stopped")

    _set_state("stopped")
    yield _ui_snapshot(log_view)


def restart_comfy(provider, token, start_command, log_view):
    state = _recover_stale_state()

    if state in ("starting", "shutting_down", "restarting"):
        yield _ui_snapshot(log_view)
        return

    _set_state("restarting")
    _append_log("comfy", "[INFO] Restarting ComfyUI...")
    if _is_alive(tunnel_process):
        _append_log("tunnel", "[INFO] Restarting tunnel...")

    start_update, stop_update, restart_update = _button_updates("restarting")
    yield (
        _get_log_text(log_view),
        "",
        _status_html("restarting"),
        start_update,
        stop_update,
        restart_update
    )

    provider = provider or "Platform Proxy"

    if provider == "Zrok":
        _append_log("tunnel", "[INFO] Gracefully stopping zrok share...")
        _stop_all(zrok_graceful=True)
    else:
        _stop_all()

    _reset_logs(provider)
    _append_log("comfy", "[INFO] Restart requested - starting a new ComfyUI session")
    _set_state("starting")

    _spawn_session(provider, token, start_command)
    yield _ui_snapshot(log_view)


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
            with gr.Column(
                elem_classes=["comfy-log-left"]
            ):
                gr.HTML(
                    '<div class="comfy-log-title">LOGS</div>'
                )

            with gr.Column(
                elem_classes=["comfy-log-center"]
            ):
                log_view = gr.Radio(
                    choices=[
                        "Tunnel",
                        "ComfyUI"
                    ],
                    value="ComfyUI",
                    show_label=False,
                    container=False,
                    elem_classes=["comfy-log-selector"]
                )

            with gr.Row(
                elem_classes=["comfy-log-right"]
            ):
                restart_button = gr.Button(
                    "Restart",
                    interactive=False,
                    elem_classes=["comfy-restart-button"]
                )

                status = gr.HTML(
                    _status_html("stopped")
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
            fn=start_comfy,
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
                stop_button,
                restart_button
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
                stop_button,
                restart_button
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
                stop_button,
                restart_button
            ],
            concurrency_limit=None
        )

        refresh_timer = gr.Timer(value=0.5, active=True)
        refresh_timer.tick(
            fn=refresh_comfy_ui,
            inputs=log_view,
            outputs=[
                logs,
                public_url,
                status,
                start_button,
                stop_button,
                restart_button
            ],
            show_progress="hidden"
        )

    return page
