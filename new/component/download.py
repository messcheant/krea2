import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import gradio as gr


BENCHMARK_CONNECTIONS = (4, 8, 16)
BENCHMARK_SECONDS = 5
AUTH_CHOICES = [
    "Without token",
    "Hugging Face token",
    "Civitai token",
    "Custom bearer token",
]
CONNECTION_CHOICES = [
    "Auto test 4/8/16",
    "4 connections",
    "8 connections",
    "16 connections",
]


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
        process = None

        try:
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
        except OSError as exc:
            results.append((connections, 0))
            logs.append(f"[TEST] {connections}: failed ({exc})")
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()
            shutil.rmtree(temp_dir, ignore_errors=True)

    valid = [item for item in results if item[1] > 0]
    if not valid:
        logs.append("[TEST] Benchmark failed, fallback to 8 connections")
        return 8, logs

    best_connections, best_speed = max(valid, key=lambda item: item[1])
    logs.append(
        f"[TEST] Best: {best_connections} connections "
        f"({_human_size(best_speed)}/s)"
    )
    return best_connections, logs


def _connection_count(connection_mode):
    match = re.search(r"\d+", connection_mode or "")
    return int(match.group()) if match else 8


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

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        yield emit("[ERROR] Download URL is invalid")
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

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        yield emit(f"[ERROR] Cannot create directory: {exc}")
        return

    if connection_mode == "Auto test 4/8/16":
        yield emit("[INFO] Testing 4, 8 and 16 connections")
        connections, benchmark_logs = _benchmark(url, token_mode, token)
        for line in benchmark_logs:
            yield emit(line)
    else:
        connections = _connection_count(connection_mode)

    yield emit(f"[INFO] Directory: {output_dir}")
    yield emit(f"[INFO] Connections: {connections}")
    yield emit(
        f"[INFO] Filename: "
        f"{filename if filename else 'Server-provided original filename'}"
    )

    cmd = _aria_command(
        url=url,
        output_dir=output_dir,
        filename=filename,
        connections=connections,
        token_mode=token_mode,
        token=token,
    )

    yield emit(f"[CMD] {_safe_log_command(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        yield emit(f"[ERROR] Failed to start aria2c: {exc}")
        return

    if process.stdout is not None:
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

    return gr.update(
        visible=enabled,
        label=label,
        placeholder=placeholder,
        value="",
    )


def _toggle_rename(mode):
    return gr.update(visible=mode == "Rename", value="")


def _toggle_download_mode(mode):
    single = mode == "Single Download"
    bulk = mode == "Bulk Download"
    return (
        gr.update(visible=single),
        gr.update(visible=bulk),
        gr.update(visible=single),
        gr.update(visible=bulk),
    )


def _parse_bulk_list(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    items = []
    errors = []

    for index in range(0, len(lines), 2):
        item_number = (index // 2) + 1
        output_dir = os.path.expanduser(lines[index])

        if index + 1 >= len(lines):
            errors.append(f"Item {item_number}: missing URL after save path")
            break

        url = lines[index + 1]
        parsed = urlparse(url)

        if not output_dir:
            errors.append(f"Item {item_number}: save path is empty")
            continue

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"Item {item_number}: invalid URL")
            continue

        items.append((output_dir, url))

    return items, errors


def _bulk_review(text):
    items, errors = _parse_bulk_list(text)
    ready = len(items)
    invalid = len(errors)

    if not (text or "").strip():
        message = "No downloads detected"
        state = "empty"
        enabled = False
    elif invalid:
        message = f"{ready} ready · {invalid} invalid"
        state = "error"
        enabled = False
    else:
        label = "download" if ready == 1 else "downloads"
        message = f"{ready} {label} detected"
        state = "ok"
        enabled = ready > 0

    html = f'<div class="bulk-status bulk-status-{state}">{message}</div>'
    return html, gr.update(interactive=enabled)


def _load_bulk_txt(file_path):
    if not file_path:
        status, button = _bulk_review("")
        return "", status, button

    path = str(getattr(file_path, "name", file_path))

    if not path.lower().endswith(".txt"):
        raise gr.Error("Only .txt files are accepted")

    try:
        content = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise gr.Error(f"Unable to read TXT file: {exc}")

    status, button = _bulk_review(content)
    return content, status, button


def bulk_download_file(list_text, token_mode, token, connection_mode):
    logs = []

    def emit(message):
        logs.append(message)
        return "\n".join(logs)

    items, errors = _parse_bulk_list(list_text)

    if not (list_text or "").strip():
        yield emit("[ERROR] Download list is empty")
        return

    if errors:
        yield emit(f"[ERROR] Bulk list contains {len(errors)} invalid item(s)")
        for error in errors:
            yield emit(f"[ERROR] {error}")
        return

    if not items:
        yield emit("[ERROR] No valid downloads detected")
        return

    if shutil.which("aria2c") is None:
        yield emit("[ERROR] aria2c is not installed or not available in PATH")
        return

    if token_mode != "Without token" and not (token or "").strip():
        yield emit("[ERROR] Token is required")
        return

    total = len(items)
    yield emit(f"[INFO] Bulk download started: {total} item(s)")

    if connection_mode == "Auto test 4/8/16":
        yield emit("[INFO] Testing 4, 8 and 16 connections using the first URL")
        connections, benchmark_logs = _benchmark(items[0][1], token_mode, token)
        for line in benchmark_logs:
            yield emit(line)
    else:
        connections = _connection_count(connection_mode)

    yield emit(f"[INFO] Connections for this batch: {connections}")

    completed = 0
    failed = 0

    for index, (output_dir, url) in enumerate(items, start=1):
        filename = _filename_from_url(url)
        display_name = filename or "Server-provided original filename"

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            failed += 1
            yield emit(
                f"[ERROR] [{index}/{total}] Cannot create directory: "
                f"{output_dir} ({exc})"
            )
            continue

        yield emit("")
        yield emit(f"[INFO] [{index}/{total}] Starting: {display_name}")
        yield emit(f"[INFO] [{index}/{total}] Directory: {output_dir}")

        cmd = _aria_command(
            url=url,
            output_dir=output_dir,
            filename=filename,
            connections=connections,
            token_mode=token_mode,
            token=token,
        )

        yield emit(f"[CMD] [{index}/{total}] {_safe_log_command(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            failed += 1
            yield emit(f"[ERROR] [{index}/{total}] Failed to start aria2c: {exc}")
            continue

        if process.stdout is not None:
            for raw_line in iter(process.stdout.readline, ""):
                line = raw_line.rstrip()
                if line:
                    yield emit(line)

        return_code = process.wait()

        if return_code == 0:
            completed += 1
            yield emit(f"[DONE] [{index}/{total}] Completed")
        else:
            failed += 1
            yield emit(f"[ERROR] [{index}/{total}] aria2c exited with code {return_code}")

    yield emit("")

    if failed:
        yield emit(
            f"[DONE] Bulk download finished: "
            f"{completed} completed, {failed} failed"
        )
    else:
        yield emit(f"[DONE] Bulk download completed: {completed}/{total} successful")


def create_download(visible=False):
    log_scroll_js = """(...args) => {
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
    }"""

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

        with gr.Column(elem_classes=["download-config"]):
            gr.HTML('<div class="download-config-header">Download Configuration</div>')

            with gr.Column(elem_classes=["download-config-body"]):
                download_mode = gr.Radio(
                    choices=["Single Download", "Bulk Download"],
                    value="Single Download",
                    show_label=False,
                    container=False,
                    elem_id="download-mode-selector",
                    elem_classes=["download-segmented"],
                )

                with gr.Column(
                    visible=True,
                    elem_id="single-download-panel",
                    elem_classes=["download-panel"],
                ) as single_panel:
                    url = gr.Textbox(
                        label="Download URL",
                        placeholder="https://huggingface.co/... / https://civitai.com/api/download/...",
                        elem_classes=["download-field"],
                    )

                    with gr.Row(elem_classes=["download-row"]):
                        output_dir = gr.Textbox(
                            label="Save path",
                            value="/workspace",
                            placeholder="/workspace/ComfyUI/models/...",
                            elem_classes=["download-field"],
                        )

                        rename_mode = gr.Radio(
                            label="Filename",
                            choices=["Original name", "Rename"],
                            value="Original name",
                            elem_classes=["filename-radio"],
                        )

                    filename = gr.Textbox(
                        label="New filename",
                        placeholder="model.safetensors",
                        visible=False,
                        elem_classes=["download-field"],
                    )

                    with gr.Row(elem_classes=["download-row"]):
                        token_mode = gr.Dropdown(
                            label="Authentication",
                            choices=AUTH_CHOICES,
                            value="Without token",
                            allow_custom_value=False,
                            filterable=False,
                            elem_classes=["download-select"],
                        )

                        connection_mode = gr.Dropdown(
                            label="aria2c connections",
                            choices=CONNECTION_CHOICES,
                            value="Auto test 4/8/16",
                            allow_custom_value=False,
                            filterable=False,
                            elem_classes=["download-select"],
                        )

                    token = gr.Textbox(
                        label="Token",
                        type="password",
                        visible=False,
                        elem_classes=["download-field"],
                    )

                with gr.Column(
                    visible=False,
                    elem_id="bulk-download-panel",
                    elem_classes=["download-panel"],
                ) as bulk_panel:
                    bulk_file = gr.File(
                        label="Import TXT",
                        file_types=[".txt"],
                        file_count="single",
                        type="filepath",
                        elem_id="bulk-download-file",
                    )

                    bulk_editor = gr.Textbox(
                        label="Download List",
                        placeholder=(
                            "/workspace/ComfyUI/models/loras\n"
                            "https://huggingface.co/...\n\n"
                            "/workspace/ComfyUI/models/checkpoints\n"
                            "https://civitai.com/api/download/..."
                        ),
                        lines=12,
                        max_lines=12,
                        interactive=True,
                        elem_id="bulk-download-list",
                    )

                    initial_status, _ = _bulk_review("")
                    bulk_status = gr.HTML(
                        value=initial_status,
                        elem_id="bulk-download-status",
                    )

                    with gr.Row(elem_classes=["download-row"]):
                        bulk_token_mode = gr.Dropdown(
                            label="Authentication",
                            choices=AUTH_CHOICES,
                            value="Without token",
                            allow_custom_value=False,
                            filterable=False,
                            elem_classes=["download-select"],
                        )

                        bulk_connection_mode = gr.Dropdown(
                            label="aria2c connections",
                            choices=CONNECTION_CHOICES,
                            value="Auto test 4/8/16",
                            allow_custom_value=False,
                            filterable=False,
                            elem_classes=["download-select"],
                        )

                    bulk_token = gr.Textbox(
                        label="Token",
                        type="password",
                        visible=False,
                        elem_classes=["download-field"],
                    )

        with gr.Row(
            visible=True,
            elem_classes=["download-actions"],
        ) as single_action:
            download_button = gr.Button(
                "Download",
                variant="primary",
                elem_classes=["download-button"],
            )

        with gr.Row(
            visible=False,
            elem_classes=["download-actions"],
        ) as bulk_action:
            bulk_download_button = gr.Button(
                "Download All",
                variant="primary",
                interactive=False,
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

        download_mode.change(
            fn=_toggle_download_mode,
            inputs=download_mode,
            outputs=[single_panel, bulk_panel, single_action, bulk_action],
            queue=False,
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

        bulk_token_mode.change(
            fn=_toggle_token,
            inputs=bulk_token_mode,
            outputs=bulk_token,
            queue=False,
        )

        bulk_file.upload(
            fn=_load_bulk_txt,
            inputs=bulk_file,
            outputs=[bulk_editor, bulk_status, bulk_download_button],
            queue=False,
        )

        bulk_editor.input(
            fn=_bulk_review,
            inputs=bulk_editor,
            outputs=[bulk_status, bulk_download_button],
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
            js=log_scroll_js,
        )

        bulk_download_button.click(
            fn=bulk_download_file,
            inputs=[
                bulk_editor,
                bulk_token_mode,
                bulk_token,
                bulk_connection_mode,
            ],
            outputs=logs,
            js=log_scroll_js,
        )

    return page