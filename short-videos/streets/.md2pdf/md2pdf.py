#!/usr/bin/env python3
"""Minimal Markdown -> HTML -> PDF (Chrome headless) converter, stdlib only."""
import html
import os
import re
import subprocess
import sys

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 13mm 11mm; }
* { box-sizing: border-box; }
body {
  font-family: "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", Arial, sans-serif;
  font-size: 12.5px; line-height: 1.6; color: #1a1a1a; margin: 0;
  -webkit-print-color-adjust: exact;
}
h1 { font-size: 21px; margin: 0 0 14px; padding-bottom: 8px; border-bottom: 2px solid #d8d8d8; }
h2 { font-size: 16px; margin: 22px 0 10px; padding-left: 8px; border-left: 4px solid #4a7ebb; }
h3 { font-size: 13.5px; margin: 16px 0 8px; color: #2b4c73; }
h4, h5, h6 { font-size: 12.5px; margin: 12px 0 6px; }
p { margin: 7px 0; text-align: justify; }
ul, ol { margin: 7px 0; padding-left: 22px; }
li { margin: 3px 0; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 0.88em;
  background: #f2f3f5; padding: 1px 4px; border-radius: 3px;
}
pre {
  background: #f6f7f9; border: 1px solid #e2e4e8; border-radius: 5px;
  padding: 9px 11px; overflow: hidden; break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 11px; line-height: 1.45; white-space: pre-wrap; }
table {
  width: 100%; border-collapse: collapse; margin: 9px 0 14px;
  font-size: 9.6px; line-height: 1.42;
}
th, td {
  border: 1px solid #d3d6db; padding: 4px 5px; vertical-align: top;
  word-break: break-word;
}
th { background: #eef2f7; font-weight: 600; text-align: left; }
tbody tr:nth-child(even) { background: #fafbfc; }
tr { break-inside: avoid; }
img { max-width: 100%; break-inside: avoid; display: block; margin: 8px 0; }
a { color: #1a5fb4; text-decoration: none; }
blockquote {
  margin: 9px 0; padding: 6px 12px; border-left: 3px solid #c9ced6;
  background: #f7f8fa; color: #444;
}
hr { border: none; border-top: 1px solid #dcdcdc; margin: 16px 0; }
h1, h2, h3, h4 { break-after: avoid; }
"""


def inline(text):
    codes = []

    def grab(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", grab, text)
    text = html.escape(text, quote=False)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: '<img src="%s" alt="%s">' % (m.group(2), m.group(1)),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        r'<a href="\2">\1</a>',
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<!~)~~(.+?)~~(?!~)", r"<del>\1</del>", text)

    for i, code in enumerate(codes):
        text = text.replace(
            "\x00%d\x00" % i,
            "<code>%s</code>" % html.escape(code, quote=False),
        )
    return text


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_align_row(line):
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def convert(md_text):
    lines = md_text.split("\n")
    out = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # drop raw <video> block (non-printable in PDF)
        if stripped.startswith("<video"):
            while i < n and "</video>" not in lines[i]:
                i += 1
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # fenced code
        fence = re.match(r"^(```|~~~)(.*)$", stripped)
        if fence:
            marker = fence.group(1)
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith(marker):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(buf), quote=False))
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append("<hr>")
            i += 1
            continue

        # table
        if stripped.startswith("|") and i + 1 < n and is_align_row(lines[i + 1]):
            header = split_row(stripped)
            i += 2
            body_rows = []
            while i < n and lines[i].strip().startswith("|"):
                body_rows.append(split_row(lines[i].strip()))
                i += 1
            t = ["<table>", "<thead><tr>"]
            for c in header:
                t.append("<th>%s</th>" % inline(c))
            t.append("</tr></thead><tbody>")
            for row in body_rows:
                t.append("<tr>")
                for j in range(len(header)):
                    cell = row[j] if j < len(row) else ""
                    t.append("<td>%s</td>" % inline(cell))
                t.append("</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % convert("\n".join(buf)))
            continue

        # lists
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            list_open = re.match(r"^\s*(\d+)[.)]\s+", line)
            out.append("<ol>" if list_open else "<ul>")
            stack = []
            items = []
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    break
                m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", cur)
                if not m:
                    if items:
                        items[-1] += " " + inline(cur.strip())
                        i += 1
                        continue
                    break
                indent = len(m.group(1))
                tag = "ol" if m.group(2)[0].isdigit() else "ul"
                if not stack:
                    stack.append((indent, tag))
                    items.append("<li>%s" % inline(m.group(3)))
                else:
                    if indent > stack[-1][0]:
                        items[-1] += "<%s>" % tag
                        stack.append((indent, tag))
                    elif indent < stack[-1][0]:
                        while len(stack) > 1 and indent < stack[-1][0]:
                            items[-1] += "</li></%s>" % stack[-1][1]
                            stack.pop()
                        items[-1] += "</li>"
                    else:
                        items[-1] += "</li>"
                    items.append("<li>%s" % inline(m.group(3)))
                i += 1
            if items:
                items[-1] += "</li>"
                while stack:
                    items[-1] += "</%s>" % stack[-1][1]
                    stack.pop()
            out.append("\n".join(items))
            continue

        # paragraph
        buf = [inline(stripped)]
        i += 1
        while i < n:
            nxt = lines[i]
            s = nxt.strip()
            if (
                not s
                or s.startswith("#")
                or s.startswith("|")
                or s.startswith(">")
                or s.startswith("```")
                or s.startswith("<video")
                or re.match(r"^(\s*)([-*+]|\d+[.)])\s+", nxt)
                or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s)
            ):
                break
            buf.append(inline(s))
            i += 1
        out.append("<p>%s</p>" % "<br>".join(buf))

    return "\n".join(out)


def build(md_path):
    md_path = os.path.abspath(md_path)
    base = os.path.dirname(md_path)
    name = os.path.splitext(os.path.basename(md_path))[0]
    pdf_path = os.path.join(base, name + ".pdf")
    html_path = os.path.join(base, ".%s.__tmp.html" % name)

    with open(md_path, encoding="utf-8") as f:
        body = convert(f.read())

    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        "<title>%s</title><style>%s</style></head><body>%s</body></html>"
        % (html.escape(name), CSS, body)
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)

    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--no-sandbox",
        "--virtual-time-budget=8000",
        "--print-to-pdf=" + pdf_path,
        "file://" + html_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(html_path)
    if not os.path.exists(pdf_path):
        sys.stderr.write(proc.stderr)
        raise SystemExit("PDF generation failed: %s" % md_path)
    return pdf_path, os.path.getsize(pdf_path)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        out, size = build(p)
        print("%8.1f KB  %s" % (size / 1024.0, out))
