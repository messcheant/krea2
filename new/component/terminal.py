import asyncio
import json
import os
import pty
import signal
import struct
import fcntl
import termios

import gradio as gr
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


TERMINAL_HTML = r"""
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css">
    <style>
        html, body {
            width: 100%;
            height: 100%;
            margin: 0;
            overflow: hidden;
            background: #090b10;
        }

        #terminal {
            width: 100%;
            height: calc(100% - 24px);
            padding: 14px;
            box-sizing: border-box;
        }

        .xterm .xterm-viewport {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }

        .xterm .xterm-viewport::-webkit-scrollbar {
            width: 0 !important;
            height: 0 !important;
            display: none !important;
        }
    </style>
</head>
<body>
    <div id="terminal"></div>

    <script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js"></script>

    <script>
        const term = new Terminal({
            cursorBlink: true,
            convertEol: true,
            fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", monospace',
            fontSize: 13,
            lineHeight: 1.2,
            scrollback: 5000,
            theme: {
                background: '#090b10',
                foreground: '#d7dde8',
                cursor: '#8ab4ff',
                selectionBackground: '#2a3b59'
            }
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
        fitAddon.fit();

        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProtocol}//${location.host}/terminal/ws`);

        function sendResize() {
            if (ws.readyState !== WebSocket.OPEN) return;

            ws.send(JSON.stringify({
                type: 'resize',
                cols: term.cols,
                rows: term.rows
            }));
        }

        ws.addEventListener('open', () => {
            fitAddon.fit();
            sendResize();
            term.focus();
        });

        const viewport = () =>
            document.querySelector('#terminal .xterm-viewport');

        let followOutput = true;

        function updateFollowState() {
            const el = viewport();
            if (!el) return;

            const distance =
                el.scrollHeight - el.scrollTop - el.clientHeight;

            followOutput = distance <= 40;
        }

        function bindSmartScroll() {
            const el = viewport();
            if (!el || el.dataset.smartScrollReady) return;

            el.dataset.smartScrollReady = '1';
            el.addEventListener('scroll', updateFollowState, {
                passive: true
            });
        }

        bindSmartScroll();

        ws.addEventListener('message', event => {
            bindSmartScroll();

            term.write(event.data, () => {
                if (followOutput) {
                    term.scrollToBottom();
                }
            });
        });

        ws.addEventListener('close', () => {
            term.write('\r\n\x1b[31m[terminal disconnected]\x1b[0m\r\n');
        });

        ws.addEventListener('error', () => {
            term.write('\r\n\x1b[31m[terminal connection error]\x1b[0m\r\n');
        });

        term.onData(data => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'input',
                    data: data
                }));
            }
        });

        const observer = new ResizeObserver(() => {
            fitAddon.fit();
            sendResize();
            bindSmartScroll();
        });

        observer.observe(document.getElementById('terminal'));

        window.addEventListener('resize', () => {
            fitAddon.fit();
            sendResize();
            bindSmartScroll();
        });

        document.addEventListener('click', () => term.focus());
    </script>
</body>
</html>
"""


def create_terminal(visible=False):
    with gr.Column(
        visible=visible,
        elem_classes=["page", "terminal-page"]
    ) as page:

        gr.HTML("""
        <div class="page-head">
            <div>
                <div class="eyebrow">CONSOLE</div>
                <h1>Terminal</h1>
                <p>Interactive shell inside the container.</p>
            </div>
        </div>
        """)

        gr.HTML(
            '<iframe id="terminal-frame" src="/terminal" '
            'allow="clipboard-read; clipboard-write"></iframe>'
        )

    return page


def _set_terminal_size(fd, rows, cols):
    rows = max(2, int(rows))
    cols = max(2, int(cols))
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


def register_terminal_routes(app, cwd="/workspace"):
    shell_cwd = os.path.abspath(cwd)

    @app.get("/terminal", response_class=HTMLResponse)
    async def terminal_page():
        return TERMINAL_HTML

    @app.websocket("/terminal/ws")
    async def terminal_socket(websocket: WebSocket):
        await websocket.accept()

        pid, fd = pty.fork()

        if pid == 0:
            os.chdir(shell_cwd)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env.setdefault("COLORTERM", "truecolor")

            shell = (
                env.get("SHELL")
                or ("/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh")
            )

            args = [shell]
            if shell.endswith("bash"):
                args.append("-l")

            os.execvpe(shell, args, env)

        async def read_pty():
            while True:
                try:
                    data = await asyncio.to_thread(os.read, fd, 4096)
                except OSError:
                    break

                if not data:
                    break

                await websocket.send_text(
                    data.decode("utf-8", errors="replace")
                )

        async def read_websocket():
            while True:
                message = await websocket.receive_text()

                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue

                message_type = payload.get("type")

                if message_type == "input":
                    data = payload.get("data", "")
                    if data:
                        os.write(fd, data.encode("utf-8"))

                elif message_type == "resize":
                    _set_terminal_size(
                        fd,
                        payload.get("rows", 24),
                        payload.get("cols", 80)
                    )

        output_task = asyncio.create_task(read_pty())
        input_task = asyncio.create_task(read_websocket())

        try:
            done, pending = await asyncio.wait(
                [output_task, input_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

        except WebSocketDisconnect:
            pass

        finally:
            for task in (output_task, input_task):
                if not task.done():
                    task.cancel()

            try:
                os.kill(pid, signal.SIGHUP)
            except ProcessLookupError:
                pass

            try:
                os.close(fd)
            except OSError:
                pass

            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass