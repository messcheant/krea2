import os
import gradio as gr

from component.dashboard import create_dashboard
from component.comfyui import create_comfyui
from component.download import create_download
from component.file_manager import create_file_manager
from component.terminal import create_terminal, register_terminal_routes


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_DIR = os.path.join(BASE_DIR, "css")

FILE_ROOT = os.path.abspath(
    os.getenv(
        "FILE_ROOT",
        "/workspace" if os.path.isdir("/workspace") else BASE_DIR
    )
)


CSS_FILES = [
    "global.css",
    "dashboard.css",
    "comfyui.css",
    "download.css",
    "file_manager.css",
    "terminal.css",
]


def load_css():
    css = []

    for filename in CSS_FILES:
        path = os.path.join(CSS_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                css.append(f.read())

        except FileNotFoundError:
            print(f"[CSS] File tidak ditemukan: {path}")

    return "\n".join(css)


CUSTOM_CSS = load_css()


def switch_page(target):
    return [
        gr.update(visible=target == "dashboard"),
        gr.update(visible=target == "comfyui"),
        gr.update(visible=target == "download"),
        gr.update(visible=target == "files"),
        gr.update(visible=target == "terminal"),
    ]


with gr.Blocks() as demo:

    with gr.Row(elem_id="shell"):

        # =====================================================
        # SIDEBAR
        # =====================================================

        with gr.Column(
            elem_id="sidebar",
            scale=0
        ):

            gr.HTML("""
            <div class="brand" style="display: flex; justify-content: center; align-items: center; padding: 15px 0;">
                <img src="https://files.catbox.moe/lfw2hv.jpg" alt="Brand" style="width: 100px; height: 100px; object-fit: cover; border-radius: 16px; display: block; margin: 0 auto;">
            </div>
            """)
            
            btn_dashboard = gr.Button(
                "▦   Dashboard",
                elem_classes="nav-btn"
            )

            btn_comfyui = gr.Button(
                "◇   ComfyUI",
                elem_classes="nav-btn"
            )

            btn_download = gr.Button(
                "↓   Download",
                elem_classes="nav-btn"
            )

            btn_files = gr.Button(
                "▤   File Manager",
                elem_classes="nav-btn"
            )

            btn_terminal = gr.Button(
                ">_   Terminal",
                elem_classes="nav-btn"
            )

        # =====================================================
        # CONTENT
        # =====================================================

        with gr.Column(
            elem_id="content",
            scale=1
        ):

            page_dashboard = create_dashboard(
                file_root=FILE_ROOT,
                visible=True
            )

            page_comfyui = create_comfyui(
                visible=False
            )

            page_download = create_download(
                visible=False
            )

            page_files = create_file_manager(
                file_root=FILE_ROOT,
                visible=False
            )

            page_terminal = create_terminal(
                visible=False
            )

    # =========================================================
    # NAVIGATION
    # =========================================================

    pages = [
        page_dashboard,
        page_comfyui,
        page_download,
        page_files,
        page_terminal
    ]


    btn_dashboard.click(
        fn=lambda: switch_page("dashboard"),
        inputs=[],
        outputs=pages,
        show_progress="hidden"
    )


    btn_comfyui.click(
        fn=lambda: switch_page("comfyui"),
        inputs=[],
        outputs=pages,
        show_progress="hidden"
    )


    btn_download.click(
        fn=lambda: switch_page("download"),
        inputs=[],
        outputs=pages,
        show_progress="hidden"
    )


    btn_files.click(
        fn=lambda: switch_page("files"),
        inputs=[],
        outputs=pages,
        show_progress="hidden"
    )


    btn_terminal.click(
        fn=lambda: switch_page("terminal"),
        inputs=[],
        outputs=pages,
        show_progress="hidden"
    )


if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI()
    register_terminal_routes(app, cwd=FILE_ROOT)

    app = gr.mount_gradio_app(
        app,
        demo,
        path="/",
        theme=gr.themes.Base(),
        css=CUSTOM_CSS
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860
    )