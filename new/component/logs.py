import gradio as gr


def create_logs(
    visible=False
):

    with gr.Column(
        visible=visible,
        elem_classes=[
            "page",
            "logs-page"
        ]
    ) as page:


        gr.HTML("""
        <div class="page-head">

            <div>

                <div class="eyebrow">
                    SYSTEM
                </div>

                <h1>
                    Logs
                </h1>

                <p>
                    Runtime output
                </p>

            </div>

        </div>


        <div class="placeholder">
            Logs page
        </div>
        """)


    return page