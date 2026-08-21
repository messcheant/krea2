import os
import re
import time
import shutil
import tempfile
import subprocess
from urllib.parse import urlparse, unquote

import gradio as gr


BENCHMARK_CONNECTIONS = (4, 8, 16)
BENCHMARK_SECONDS = 5


def _filename_from_url(url):
    parsed = urlparse(url)
    name = unquote(os.path.basename(parsed.path)).strip()

    if parsed.netloc.lower() in {"huggingface.co", "www.huggingface.co"}:
        if "/resolve/" in parsed.path and name:
            return name

    if name and "." in name and not name.isdigit():
        return name

    return None


def _human_size(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024



def _aria_command(url, output_dir, connections, token_mode, token, filename=None):
    cmd = [
        "aria2c",
        "-c",
        "-x", str(connections),
        "-s", str(connections),
        "-k", "1M",
        "--file-allocation=none",
        "--console-log-level=notice",
        "--summary-interval=1",
        "--content-disposition=true",
        "--content-disposition-default-utf8=true",
        "-d", output_dir,
    ]

    if filename:
        cmd += ["-o", filename]

    token = (token or "").strip()
    if token_mode != "Without token" and token:
        cmd += ["--header", f"Authorization: Bearer {token}"]

    cmd.append(url.strip())
    return cmd


def _safe_log_command(cmd):
    safe = []
    hide_next = False
    for item in cmd:
        if hide_next:
            safe.append("Authorization: Bearer ********")
            hide_next = False
            continue
        safe.append(item)
        if item == "--header":
            hide_next = True
    return " ".join(safe)


def _benchmark(url, token_mode, token):
    results = []
    logs = []

    for connections in BENCHMARK_CONNECTIONS:
        temp_dir = tempfile.mkdtemp(prefix="aria2-bench-")
        filename = "benchmark.part"
        target = os.path.join(temp_dir, filename)
        cmd = _aria_command(
            url=url,
            output_dir=temp_dir,
            filename=filename,
            connections=connections,
            token_mode=token_mode,
            token=token,
        )

        logs.append(f"[TEST] {connections} connections for {BENCHMARK_SECONDS}s")
        started = time.monotonic()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            process.wait(timeout=BENCHMARK_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        elapsed = max(time.monotonic() - started, 0.001)
        downloaded = os.path.getsize(target) if os.path.exists(target) else 0
        speed = downloaded / elapsed
        results.append((connections, speed))
        logs.append(f"[TEST] {connections}: {_human_size(speed)}/s")
        shutil.rmtree(temp_dir, ignore_errors=True)

    valid = [item for item in results if item[1] > 0]
    if not valid:
        logs.append("[TEST] Benchmark failed, fallback to 8 connections")
        return 8, logs

    best_connections, best_speed = max(valid, key=lambda item: item[1])
    logs.append(f"[TEST] Best: {best_connections} connections ({_human_size(best_speed)}/s)")
    return best_connections, logs


def download_file(url, output_dir, rename_mode, filename, token_mode, token, connection_mode):
    logs = []

    def emit(message):
        logs.append(message)
        return "\n".join(logs)

    url = (url or "").strip()
    output_dir = os.path.expanduser((output_dir or "").strip())
    filename = (filename or "").strip()

    if not url:
        yield emit("[ERROR] Download URL is required")
        return

    if shutil.which("aria2c") is None:
        yield emit("[ERROR] aria2c is not installed or not available in PATH")
        return

    if not output_dir:
        yield emit("[ERROR] Save path is required")
        return

    if token_mode != "Without token" and not (token or "").strip():
        yield emit("[ERROR] Token is required")
        return

    if rename_mode == "Rename":
        if not filename:
            yield emit("[ERROR] New filename is required")
            return
        if os.path.basename(filename) != filename or filename in (".", ".."):
            yield emit("[ERROR] Filename must not contain a directory path")
            return
    else:
        filename = _filename_from_url(url)

    os.makedirs(output_dir, exist_ok=True)

    if connection_mode == "Auto test 4/8/16":
        yield emit("[INFO] Testing 4, 8 and 16 connections")
        connections, benchmark_logs = _benchmark(url, token_mode, token)
        for line in benchmark_logs:
            yield emit(line)
    else:
        connections = int(re.search(r"\d+", connection_mode).group())

    yield emit(f"[INFO] Directory: {output_dir}")
    yield emit(f"[INFO] Connections: {connections}")
    yield emit(f"[INFO] Filename: {filename if filename else 'Server-provided original filename'}")

    cmd = _aria_command(
        url=url,
        output_dir=output_dir,
        filename=filename,
        connections=connections,
        token_mode=token_mode,
        token=token,
    )

    yield emit(f"[CMD] {_safe_log_command(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for raw_line in iter(process.stdout.readline, ""):
        line = raw_line.rstrip()
        if line:
            yield emit(line)

    return_code = process.wait()
    if return_code == 0:
        yield emit(f"[DONE] Download completed in {output_dir}")
    else:
        yield emit(f"[ERROR] aria2c exited with code {return_code}")


def _toggle_token(mode):
    enabled = mode != "Without token"
    if mode == "Hugging Face token":
        label = "Hugging Face token"
        placeholder = "hf_..."
    elif mode == "Civitai token":
        label = "Civitai API token"
        placeholder = "Enter Civitai token"
    else:
        label = "Token"
        placeholder = "Bearer token"
    return gr.update(visible=enabled, label=label, placeholder=placeholder, value="")



def _toggle_rename(mode):
    return gr.update(visible=mode == "Rename", value="")


def create_download(visible=False):
    with gr.Column(
        visible=visible,
        elem_classes=["page", "download-page"],
    ) as page:
        gr.HTML("""
        <div class="page-head">
            <div>
                <div class="eyebrow">TRANSFER</div>
                <h1>Download</h1>
                <p>Download models and assets with aria2c</p>
            </div>
        </div>
        """)

        with gr.Column(elem_classes=["download-card"]):
            url = gr.Textbox(
                label="Download URL",
                placeholder="https://huggingface.co/... / https://civitai.com/api/download/...",
            )

            with gr.Row(elem_classes=["download-row"]):
                output_dir = gr.Textbox(
                    label="Save path",
                    value="/workspace",
                    placeholder="/workspace/ComfyUI/models/...",
                    scale=1,
                )
                rename_mode = gr.Radio(
                    label="Filename",
                    choices=["Original name", "Rename"],
                    value="Original name",
                    scale=1,
                )

            filename = gr.Textbox(
                label="New filename",
                placeholder="model.safetensors",
                visible=False,
            )

            with gr.Row(elem_classes=["download-row"]):
                token_mode = gr.Dropdown(
                    label="Authentication",
                    choices=[
                        "Without token",
                        "Hugging Face token",
                        "Civitai token",
                        "Custom bearer token",
                    ],
                    value="Without token",
                    allow_custom_value=False,
                    filterable=False,
                    scale=1,
                )
                connection_mode = gr.Dropdown(
                    label="aria2c connections",
                    choices=[
                        "Auto test 4/8/16",
                        "4 connections",
                        "8 connections",
                        "16 connections",
                    ],
                    value="Auto test 4/8/16",
                    allow_custom_value=False,
                    filterable=False,
                    scale=1,
                )

            token = gr.Textbox(
                label="Token",
                type="password",
                visible=False,
            )

            download_button = gr.Button(
                "Start Download",
                variant="primary",
                elem_classes=["download-button"],
            )

        gr.HTML('<div class="download-log-title">LOGS</div>')

        logs = gr.Textbox(
            value="Ready.",
            lines=20,
            max_lines=20,
            interactive=False,
            show_label=False,
            container=False,
            elem_id="download-logs",
        )

        rename_mode.change(
            fn=_toggle_rename,
            inputs=rename_mode,
            outputs=filename,
            queue=False,
        )

        token_mode.change(
            fn=_toggle_token,
            inputs=token_mode,
            outputs=token,
            queue=False,
        )

        download_button.click(
            fn=download_file,
            inputs=[
                url,
                output_dir,
                rename_mode,
                filename,
                token_mode,
                token,
                connection_mode,
            ],
            outputs=logs,
            js="""(...args) => {
                const setupLogScroll = () => {
                    const textarea = document.querySelector('#download-logs textarea');
                    if (!textarea) return false;

                    if (!textarea.dataset.smartScrollReady) {
                        textarea.dataset.smartScrollReady = '1';
                        textarea.dataset.followLogs = '1';

                        textarea.addEventListener('scroll', () => {
                            const distance = textarea.scrollHeight - textarea.scrollTop - textarea.clientHeight;
                            textarea.dataset.followLogs = distance <= 40 ? '1' : '0';
                        });
                    }

                    textarea.dataset.followLogs = '1';
                    textarea.scrollTop = textarea.scrollHeight;
                    return true;
                };

                if (window.downloadLogAutoScroll) {
                    clearInterval(window.downloadLogAutoScroll);
                }

                setupLogScroll();

                window.downloadLogAutoScroll = setInterval(() => {
                    const textarea = document.querySelector('#download-logs textarea');
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
            }""",
        )

    return page