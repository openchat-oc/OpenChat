"""Markdown mínimo y SEGURO → HTML para QLabel. Todo se escapa primero: el modelo no puede inyectar HTML."""
from __future__ import annotations

import html
import re

_FENCE = re.compile(r"```([\w+#.\-]*)[ \t]*\n(.*?)(?:\n```|\Z)", re.S)
_CODE_STYLE = "font-family:'JetBrains Mono','DejaVu Sans Mono',monospace;background:#101117;color:#d9d4ff"
_URL = re.compile(r"(https?://[^\s<>\"')\]]+)")


def split_blocks(text: str) -> list[tuple[str, str, str]]:
    """[("text", "", cuerpo) | ("code", lenguaje, código)]. Un bloque sin cerrar (streaming) cuenta como código."""
    out: list[tuple[str, str, str]] = []
    pos = 0
    for m in _FENCE.finditer(text):
        if m.start() > pos:
            out.append(("text", "", text[pos:m.start()]))
        out.append(("code", m.group(1), m.group(2)))
        pos = m.end()
    if pos < len(text):
        out.append(("text", "", text[pos:]))
    return [b for b in out if b[2].strip() or b[0] == "code"]


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`\n]+)`", lambda m: f'<span style="{_CODE_STYLE}">&nbsp;{m.group(1)}&nbsp;</span>', s)
    s = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", r'<a href="\2" style="color:#a092ff">\1</a>', s)
    s = re.sub(r"(?<![\"'>=])(https?://[^\s<>\"')\]]+)", lambda m: f'<a href="{m.group(1)}" style="color:#a092ff">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    return s


def md_to_html(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    in_list: str | None = None

    def flush_para() -> None:
        if para:
            out.append("<p style='margin:0 0 6px 0'>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    for line in lines:
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        ul = re.match(r"^\s*[-*•]\s+(.*)$", line)
        ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if h:
            flush_para(); close_list()
            size = {1: 20, 2: 17, 3: 15, 4: 14}[len(h.group(1))]
            out.append(f"<p style='margin:8px 0 4px 0;font-size:{size}px;font-weight:700'>{_inline(h.group(2))}</p>")
        elif ul or ol:
            flush_para()
            kind = "ul" if ul else "ol"
            if in_list != kind:
                close_list(); out.append(f"<{kind} style='margin:2px 0 6px 0'>"); in_list = kind
            out.append(f"<li>{_inline((ul or ol).group(1))}</li>")
        elif not line.strip():
            flush_para(); close_list()
        else:
            close_list(); para.append(line)
    flush_para(); close_list()
    return "".join(out) or "&nbsp;"
