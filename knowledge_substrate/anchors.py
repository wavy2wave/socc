"""Source line-anchor + hyperlink builder.

A wiki claim must be traceable to the exact source line. We emit two forms:
- markdown link `[label](abs_path#Lnn)` for editors/viewers that resolve file links
- a plain `abs_path:line` reference (clickable in most terminals/IDEs)
"""

from pathlib import Path


def anchor(abs_path, line):
    return f"#L{int(line)}"


def file_line_ref(abs_path, line):
    return f"{abs_path}:{int(line)}"


def md_link(abs_path, line, label=None):
    label = label or f"{Path(abs_path).name}:{int(line)}"
    return f"[{label}]({abs_path}#L{int(line)})"


def source_link_record(sha16, abs_path, line):
    return {
        "sha16": sha16,
        "abs_path": abs_path,
        "line": int(line),
        "anchor": anchor(abs_path, line),
        "ref": file_line_ref(abs_path, line),
        "md_link": md_link(abs_path, line),
    }
