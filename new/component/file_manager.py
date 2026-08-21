import os
import html
import shutil
from datetime import datetime

import gradio as gr

EDITABLE_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".sh", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".css", ".js", ".html",
    ".htm", ".xml", ".csv", ".env", ".log"
}

EDITABLE_TEXT_NAMES = {
    "Dockerfile", "Makefile", "LICENSE", "README",
    ".gitignore", ".dockerignore"
}

MAX_EDITOR_SIZE = 2 * 1024 * 1024



def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def is_editable_text_file(path):
    if not os.path.isfile(path):
        return False

    name = os.path.basename(path)
    if name in EDITABLE_TEXT_NAMES:
        return True

    return os.path.splitext(name)[1].lower() in EDITABLE_TEXT_EXTENSIONS


def read_text_file(path):
    if not is_editable_text_file(path):
        return None

    try:
        if os.path.getsize(path) > MAX_EDITOR_SIZE:
            return None

        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, PermissionError, UnicodeDecodeError):
        return None


def create_file_manager(file_root, visible=False):
    file_root = os.path.abspath(file_root)
    root_name = os.path.basename(file_root.rstrip(os.sep)) or file_root

    def safe_path(path):
        path = os.path.abspath(path or file_root)
        try:
            if os.path.commonpath([file_root, path]) != file_root:
                return file_root
        except ValueError:
            return file_root
        return path

    def action_attr(payload, confirm_message=None):
        attrs = [
            f'data-fm-type="{html.escape(str(payload.get("type", "")), quote=True)}"'
        ]

        if "target" in payload:
            attrs.append(
                f'data-fm-target="{html.escape(str(payload["target"]), quote=True)}"'
            )

        if "name" in payload:
            attrs.append(
                f'data-fm-name="{html.escape(str(payload["name"]), quote=True)}"'
            )

        if confirm_message:
            attrs.append(
                f'data-fm-confirm="{html.escape(confirm_message, quote=True)}"'
            )

        return " ".join(attrs)


    html_click_js = """
    element.addEventListener("click", async (event) => {
        const copyTarget = event.target.closest("[data-fm-copy]");
        if (copyTarget && element.contains(copyTarget)) {
            event.preventDefault();
            event.stopPropagation();

            const text = copyTarget.dataset.fmCopy || "";
            try {
                await navigator.clipboard.writeText(text);
            } catch (_) {
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                textarea.remove();
            }
            return;
        }

        const target = event.target.closest("[data-fm-type]");
        if (!target || !element.contains(target)) return;

        event.preventDefault();
        event.stopPropagation();

        const type = target.dataset.fmType;
        const confirmMessage = target.dataset.fmConfirm;

        if (confirmMessage && !window.confirm(confirmMessage)) return;

        const payload = { type };

        if (target.dataset.fmTarget !== undefined) {
            payload.target = target.dataset.fmTarget;
        }

        if (target.dataset.fmName !== undefined) {
            payload.name = target.dataset.fmName;
        }

        trigger("click", payload);
    });
    """


    def copy_button(path, extra_class=""):
        copy_icon = (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="9" y="9" width="11" height="11" rx="2"/>'
            '<path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>'
            '</svg>'
        )
        escaped_path = html.escape(path, quote=True)
        classes = "fm-copy" + (f" {extra_class}" if extra_class else "")
        return (
            f'<button type="button" class="{classes}" data-fm-copy="{escaped_path}" '
            f'aria-label="Copy path" title="Copy path">{copy_icon}</button>'
        )


    def render_breadcrumb(path):
        path = safe_path(path)
        rel = os.path.relpath(path, file_root)
        parts = [] if rel == "." else rel.split(os.sep)

        items = [
            f'<button type="button" class="fm-crumb" '
            f'{action_attr({"type": "crumb", "target": ""})}>'
            f'{html.escape(root_name)}</button>'
        ]

        current_parts = []

        for part in parts:
            current_parts.append(part)
            rel_target = "/".join(current_parts)

            items.append('<span class="fm-crumb-sep">/</span>')
            items.append(
                f'<button type="button" class="fm-crumb" '
                f'{action_attr({"type": "crumb", "target": rel_target})}>'
                f'{html.escape(part)}</button>'
            )

        items.append('<span class="fm-crumb-sep">/</span>')
        return '<div class="fm-breadcrumb-inner">' + copy_button(path, 'fm-copy-breadcrumb') + ''.join(items) + '</div>'


    def render_file_breadcrumb(path, filename):
        path = safe_path(path)
        rel = os.path.relpath(path, file_root)
        parts = [] if rel == "." else rel.split(os.sep)

        items = [
            f'<button type="button" class="fm-crumb" '
            f'{action_attr({"type": "crumb", "target": ""})}>'
            f'{html.escape(root_name)}</button>'
        ]

        current_parts = []

        for part in parts:
            current_parts.append(part)
            rel_target = "/".join(current_parts)
            items.append('<span class="fm-crumb-sep">/</span>')
            items.append(
                f'<button type="button" class="fm-crumb" '
                f'{action_attr({"type": "crumb", "target": rel_target})}>'
                f'{html.escape(part)}</button>'
            )

        items.append('<span class="fm-crumb-sep">/</span>')
        items.append(
            f'<span class="fm-crumb fm-crumb-current">{html.escape(filename)}</span>'
        )

        return '<div class="fm-breadcrumb-inner">' + copy_button(safe_path(os.path.join(path, filename)), 'fm-copy-breadcrumb') + ''.join(items) + '</div>'

    def read_entries(path):
        path = safe_path(path)
        entries = []

        try:
            with os.scandir(path) as scan:
                for entry in scan:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        stat = entry.stat(follow_symlinks=False)
                        entries.append({
                            "name": entry.name,
                            "is_dir": is_dir,
                            "type": "Folder" if is_dir else "File",
                            "size": "--" if is_dir else human_size(stat.st_size),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                            "mtime": stat.st_mtime,
                        })
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            return []

        entries.sort(key=lambda item: item["mtime"], reverse=True)
        return entries

    def render_table(path):
        path = safe_path(path)
        entries = read_entries(path)

        rows = []
        for item in entries:
            escaped_name = html.escape(item["name"])
            if item["is_dir"]:
                icon = (
                    '<svg viewBox="0 0 24 24" aria-hidden="true">'
                    '<path d="M3 6.5h6l2 2H21v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6.5Z"/>'
                    '</svg>'
                )
                open_action = action_attr({"type": "open", "name": item["name"]})
                icon_html = (
                    f'<button type="button" class="fm-icon-btn fm-folder-open" {open_action} '
                    f'aria-label="Open {escaped_name}"><span class="fm-file-icon">{icon}</span></button>'
                )
                name_html = (
                    f'<button type="button" class="fm-name fm-folder-name" {open_action}>'
                    f'{escaped_name}/</button>'
                )
            else:
                icon = (
                    '<svg viewBox="0 0 24 24" aria-hidden="true">'
                    '<path d="M6 2h8l4 4v16H6V2Zm8 1.8V8h4.2"/>'
                    '</svg>'
                )
                icon_html = f'<span class="fm-file-icon">{icon}</span>'

                target_path = safe_path(os.path.join(path, item["name"]))
                if is_editable_text_file(target_path):
                    edit_action = action_attr({"type": "edit", "name": item["name"]})
                    name_html = (
                        f'<button type="button" class="fm-name fm-text-file" {edit_action}>'
                        f'{escaped_name}</button>'
                    )
                else:
                    name_html = f'<span class="fm-name">{escaped_name}</span>'

            item_path = safe_path(os.path.join(path, item["name"]))
            copy_html = copy_button(item_path)

            move_icon = (
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M3 7h7l2 2h9v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>'
                '<path d="M9 14h6M12 11l3 3-3 3"/>'
                '</svg>'
            )
            move_action = action_attr({"type": "move", "name": item["name"]})
            move_html = (
                f'<button type="button" class="fm-move" {move_action} '
                f'aria-label="Move {escaped_name}" title="Move">{move_icon}</button>'
            )

            delete_icon = (
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>'
                '</svg>'
            )
            delete_action = action_attr(
                {"type": "delete", "name": item["name"]},
                f'Hapus {item["name"]}?'
            )
            delete_html = (
                f'<button type="button" class="fm-delete" {delete_action} '
                f'aria-label="Delete {escaped_name}" title="Delete">{delete_icon}</button>'
            )

            rows.append(
                '<div class="fm-table-row">'
                f'<div class="fm-cell fm-cell-icon">{icon_html}</div>'
                f'<div class="fm-cell fm-cell-name">{name_html}</div>'
                f'<div class="fm-cell fm-cell-type">{html.escape(item["type"])}</div>'
                f'<div class="fm-cell fm-cell-size">{html.escape(item["size"])}</div>'
                f'<div class="fm-cell fm-cell-modified">{html.escape(item["modified"])}</div>'
                f'<div class="fm-cell fm-cell-actions">{copy_html}{move_html}{delete_html}</div>'
                '</div>'
            )

        if not rows:
            rows.append('<div class="fm-empty">Folder ini kosong</div>')

        return (
            '<div class="fm-table-shell">'
            '<div class="fm-table-head">'
            '<div></div>'
            '<div>Objects</div>'
            '<div>Type</div>'
            '<div>Size</div>'
            '<div>Modified</div>'
            '<div></div>'
            '</div>'
            '<div class="fm-table-body">' + ''.join(rows) + '</div>'
            '</div>'
        )

    def render(path):
        path = safe_path(path)
        return path, render_breadcrumb(path), render_table(path)

    def handle_action(current_path, current_file, evt: gr.EventData):
        current_path = safe_path(current_path)
        action = getattr(evt, "_data", {}) or {}
        action_type = action.get("type")

        def browser_view(path):
            path, crumb, table = render(path)
            return (
                path,
                crumb,
                table,
                "",
                "",
                "",
                "",
                gr.update(visible=True),
                gr.update(visible=False),
                "",
                current_path,
                gr.update(visible=False),
            )

        if action_type == "open":
            name = str(action.get("name") or "")

            if (
                name
                and name not in {".", ".."}
                and os.path.basename(name) == name
            ):
                target = safe_path(os.path.join(current_path, name))

                if os.path.isdir(target):
                    return browser_view(target)

            return browser_view(current_path)

        if action_type == "crumb":
            rel_target = str(action.get("target") or "").strip("/")

            if rel_target:
                target = safe_path(
                    os.path.join(file_root, *rel_target.split("/"))
                )
            else:
                target = file_root

            if os.path.isdir(target):
                return browser_view(target)

            return browser_view(current_path)

        if action_type == "edit":
            name = str(action.get("name") or "")
            target = safe_path(os.path.join(current_path, name))

            valid = (
                name
                and name not in {".", ".."}
                and os.path.basename(name) == name
                and os.path.dirname(target) == current_path
                and is_editable_text_file(target)
            )

            if valid:
                content = read_text_file(target)

                if content is not None:
                    return (
                        current_path,
                        render_file_breadcrumb(current_path, name),
                        render_table(current_path),
                        name,
                        html.escape(name),
                        content,
                        content,
                        gr.update(visible=False),
                        gr.update(visible=True),
                        "",
                        current_path,
                        gr.update(visible=False),
                    )

            return browser_view(current_path)

        if action_type == "move":
            name = str(action.get("name") or "")
            target = safe_path(os.path.join(current_path, name))

            valid = (
                name
                and name not in {".", ".."}
                and os.path.basename(name) == name
                and os.path.dirname(target) == current_path
                and target != file_root
                and (os.path.exists(target) or os.path.islink(target))
            )

            if valid:
                return (
                    current_path,
                    render_breadcrumb(current_path),
                    render_table(current_path),
                    "",
                    "",
                    "",
                    "",
                    gr.update(visible=True),
                    gr.update(visible=False),
                    name,
                    current_path,
                    gr.update(visible=True),
                )

            return browser_view(current_path)

        if action_type == "delete":
            name = str(action.get("name") or "")
            target = safe_path(os.path.join(current_path, name))

            if (
                name
                and name not in {".", ".."}
                and os.path.basename(name) == name
                and os.path.dirname(target) == current_path
                and target != file_root
            ):
                try:
                    if os.path.isdir(target) and not os.path.islink(target):
                        shutil.rmtree(target)
                    elif os.path.exists(target) or os.path.islink(target):
                        os.remove(target)
                except (OSError, PermissionError):
                    pass

            return browser_view(current_path)

        return browser_view(current_path)

    def refresh(current_path):
        return render(current_path)

    def upload_files(current_path, files):
        current_path = safe_path(current_path)
        files = files or []
        if not isinstance(files, list):
            files = [files]

        for file_path in files:
            if not file_path:
                continue
            source = file_path.name if hasattr(file_path, "name") else str(file_path)
            if not os.path.isfile(source):
                continue
            destination = safe_path(os.path.join(current_path, os.path.basename(source)))
            if os.path.dirname(destination) == current_path:
                shutil.copy2(source, destination)

        return render(current_path)

    def create_folder(current_path, folder_name):
        current_path = safe_path(current_path)
        folder_name = (folder_name or "").strip()

        valid = (
            folder_name
            and folder_name not in {".", ".."}
            and os.path.basename(folder_name) == folder_name
            and os.sep not in folder_name
            and not (os.altsep and os.altsep in folder_name)
        )

        if valid:
            target = safe_path(os.path.join(current_path, folder_name))
            if os.path.dirname(target) == current_path:
                try:
                    os.makedirs(target, exist_ok=False)
                    folder_name = ""
                except (FileExistsError, OSError, PermissionError):
                    pass

        path, crumb, table = render(current_path)
        return path, crumb, table, folder_name, gr.update(visible=False)

    def save_text_file(current_path, current_file, content):
        current_path = safe_path(current_path)
        name = str(current_file or "")
        target = safe_path(os.path.join(current_path, name))
        text = "" if content is None else str(content)

        valid = (
            name
            and name not in {".", ".."}
            and os.path.basename(name) == name
            and os.path.dirname(target) == current_path
            and is_editable_text_file(target)
        )

        if not valid:
            return text, gr.update(value="Unsaved")

        try:
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())

            with open(target, "r", encoding="utf-8") as f:
                saved = f.read()

            if saved != text:
                return saved, gr.update(value="Unsaved")

            return saved, gr.update(value="Saved")

        except (OSError, PermissionError, UnicodeError):
            return text, gr.update(value="Unsaved")

    def editor_changed(content, baseline):
        content = "" if content is None else str(content)
        baseline = "" if baseline is None else str(baseline)

        if content == baseline:
            return gr.update(value="")

        return gr.update(value="Unsaved")

    def close_editor(current_path):
        current_path = safe_path(current_path)
        path, crumb, table = render(current_path)

        return (
            path,
            crumb,
            table,
            "",
            "",
            gr.update(value=""),
            gr.update(visible=True),
            gr.update(visible=False),
            "",
            current_path,
            gr.update(visible=False),
        )

    def move_item(current_path, move_name, destination):
        current_path = safe_path(current_path)
        name = str(move_name or "")
        destination = os.path.abspath((destination or "").strip())

        source = safe_path(os.path.join(current_path, name))
        destination = safe_path(destination)

        valid = (
            name
            and name not in {".", ".."}
            and os.path.basename(name) == name
            and os.path.dirname(source) == current_path
            and source != file_root
            and (os.path.exists(source) or os.path.islink(source))
            and os.path.isdir(destination)
        )

        if valid:
            target = safe_path(os.path.join(destination, name))
            inside_self = os.path.isdir(source) and (
                destination == source or destination.startswith(source + os.sep)
            )

            if not inside_self and target != source and not os.path.exists(target):
                try:
                    shutil.move(source, target)
                except (OSError, PermissionError, shutil.Error):
                    pass

        path, crumb, table = render(current_path)
        return path, crumb, table, "", current_path, gr.update(visible=False)

    initial_path, initial_breadcrumb, initial_table = render(file_root)

    with gr.Column(visible=visible, elem_classes=["page", "file-manager-page"]) as page:
        current_path = gr.State(initial_path)
        current_file = gr.State("")
        saved_content = gr.State("")
        move_name = gr.State("")

        with gr.Row(elem_classes="fm-topbar"):
            breadcrumb_html = gr.HTML(
                initial_breadcrumb,
                elem_classes="fm-breadcrumb",
                scale=1,
                js_on_load=html_click_js,
            )

            with gr.Row(elem_classes="fm-actions", scale=0):
                btn_upload = gr.UploadButton(
                    "Upload",
                    file_count="multiple",
                    type="filepath",
                    elem_classes=["fm-btn", "fm-upload"],
                    min_width=96,
                    scale=0,
                )
                btn_add_folder = gr.Button(
                    "+ Add folder",
                    elem_classes=["fm-btn", "fm-primary"],
                    min_width=116,
                    scale=0,
                )
                btn_refresh = gr.Button(
                    "↻",
                    elem_classes=["fm-btn", "fm-refresh"],
                    min_width=42,
                    scale=0,
                )

        with gr.Row(visible=False, elem_classes="fm-folder-panel") as folder_panel:
            folder_name = gr.Textbox(
                placeholder="Folder name",
                show_label=False,
                container=False,
                elem_classes="fm-folder-input",
                scale=1,
            )
            btn_create = gr.Button(
                "Create",
                elem_classes=["fm-btn", "fm-primary"],
                min_width=90,
                scale=0,
            )

        with gr.Column(visible=False, elem_classes="fm-move-overlay") as move_panel:
            with gr.Column(elem_classes="fm-move-popup"):
                gr.HTML("<div class='fm-move-title'>Move item</div>")
                move_destination = gr.Textbox(
                    label="Destination",
                    value=initial_path,
                    elem_classes="fm-move-input",
                )
                with gr.Row(elem_classes="fm-move-actions"):
                    btn_cancel_move = gr.Button(
                        "Cancel",
                        elem_classes="fm-btn",
                        min_width=82,
                        scale=0,
                    )
                    btn_move = gr.Button(
                        "Move",
                        elem_classes=["fm-btn", "fm-primary"],
                        min_width=82,
                        scale=0,
                    )

        with gr.Column(visible=True, elem_classes="fm-browser-panel") as browser_panel:
            table_html = gr.HTML(
                initial_table,
                elem_id="fm-table",
                js_on_load=html_click_js,
            )

        with gr.Column(visible=False, elem_classes="fm-editor-panel") as editor_panel:
            with gr.Row(elem_classes="fm-editor-head"):
                editor_title = gr.HTML(
                    "",
                    elem_classes="fm-editor-title",
                    scale=1,
                )

                save_status = gr.HTML(
                    "",
                    elem_classes="fm-save-status",
                    scale=0,
                )

                btn_save = gr.Button(
                    "Save",
                    elem_classes=["fm-btn", "fm-primary"],
                    min_width=82,
                    scale=0,
                )

                btn_close_editor = gr.Button(
                    "Close",
                    elem_classes="fm-btn",
                    min_width=82,
                    scale=0,
                )

            editor_content = gr.Code(
                value="",
                language=None,
                interactive=True,
                show_label=False,
                elem_classes="fm-editor",
            )

        breadcrumb_html.click(
            fn=handle_action,
            inputs=[current_path, current_file],
            outputs=[
                current_path,
                breadcrumb_html,
                table_html,
                current_file,
                editor_title,
                editor_content,
                saved_content,
                browser_panel,
                editor_panel,
                move_name,
                move_destination,
                move_panel,
            ],
            show_progress="hidden",
        )

        table_html.click(
            fn=handle_action,
            inputs=[current_path, current_file],
            outputs=[
                current_path,
                breadcrumb_html,
                table_html,
                current_file,
                editor_title,
                editor_content,
                saved_content,
                browser_panel,
                editor_panel,
                move_name,
                move_destination,
                move_panel,
            ],
            show_progress="hidden",
        )

        btn_refresh.click(
            fn=refresh,
            inputs=current_path,
            outputs=[current_path, breadcrumb_html, table_html],
            show_progress="hidden",
        )

        btn_upload.upload(
            fn=upload_files,
            inputs=[current_path, btn_upload],
            outputs=[current_path, breadcrumb_html, table_html],
            show_progress="hidden",
        )

        btn_add_folder.click(
            fn=lambda: gr.update(visible=True),
            outputs=folder_panel,
            show_progress="hidden",
        )

        btn_create.click(
            fn=create_folder,
            inputs=[current_path, folder_name],
            outputs=[current_path, breadcrumb_html, table_html, folder_name, folder_panel],
            show_progress="hidden",
        )

        folder_name.submit(
            fn=create_folder,
            inputs=[current_path, folder_name],
            outputs=[current_path, breadcrumb_html, table_html, folder_name, folder_panel],
            show_progress="hidden",
        )

        btn_save.click(
            fn=save_text_file,
            inputs=[current_path, current_file, editor_content],
            outputs=[saved_content, save_status],
            show_progress="hidden",
        )

        editor_content.change(
            fn=editor_changed,
            inputs=[editor_content, saved_content],
            outputs=save_status,
            show_progress="hidden",
        )

        btn_close_editor.click(
            fn=close_editor,
            inputs=current_path,
            outputs=[
                current_path,
                breadcrumb_html,
                table_html,
                current_file,
                saved_content,
                save_status,
                browser_panel,
                editor_panel,
                move_name,
                move_destination,
                move_panel,
            ],
            show_progress="hidden",
        )

        btn_cancel_move.click(
            fn=lambda current: ("", current, gr.update(visible=False)),
            inputs=current_path,
            outputs=[move_name, move_destination, move_panel],
            show_progress="hidden",
        )

        btn_move.click(
            fn=move_item,
            inputs=[current_path, move_name, move_destination],
            outputs=[current_path, breadcrumb_html, table_html, move_name, move_destination, move_panel],
            show_progress="hidden",
        )

        move_destination.submit(
            fn=move_item,
            inputs=[current_path, move_name, move_destination],
            outputs=[current_path, breadcrumb_html, table_html, move_name, move_destination, move_panel],
            show_progress="hidden",
        )


    return page