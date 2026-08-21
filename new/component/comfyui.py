import gradio as gr


def create_comfyui(
    visible=False
):

    with gr.Column(
        visible=visible,
        elem_classes=[
            "page",
            "comfyui-page"
        ]
    ) as page:


        gr.HTML("""
        <div class="page-head">

            <div>

                <div class="eyebrow">
                    APPLICATION
                </div>

                <h1>
                    ComfyUI
                </h1>

                <p>
                    Workspace integration
                </p>

            </div>

        </div>


        <div class="placeholder">
            ComfyUI page
        </div>
        """)


    return page