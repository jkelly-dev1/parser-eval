#!/usr/bin/env python3
"""Unstructured (Apache-2.0 core) over the frozen corpus.

    envs/unstructured/bin/python adapters/run_unstructured.py

STRATEGY IS PINNED TO hi_res AND THAT CHOICE IS THE WHOLE COMPARISON. On a PDF
with no text layer, "fast" returns nothing at all -- it reads the text objects,
and there are none -- so the default "auto" strategy is really a switch that
picks something else on your behalf. hi_res is the one people mean when they
say they compared against Unstructured: a layout model over the page, then OCR
inside each detected region.

The elements come back typed (Title, NarrativeText, Table, ...). This adapter
writes the text of each element on its own line, and a Table element's
text_as_html when it produced one, because a parser that recovered the table
AS a table should not be graded as if it had returned loose lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import run                                          # noqa: E402

import re                                                       # noqa: E402

from unstructured.partition.pdf import partition_pdf            # noqa: E402


def version() -> str:
    from importlib.metadata import version as v
    return f"unstructured {v('unstructured')} (hi_res strategy)"


def _rows(html: str) -> str:
    """One line per <tr>, cells separated by pipes.

    THE LINE BREAKS MATTER TO THE COMPARISON, NOT JUST TO THE EYE. The grader
    decides which row a cell belongs to by which LINE it is on, exactly as it
    does for Docling's Markdown table. Emitting Unstructured's whole table as
    a single line of HTML would collapse every row into one, and each row's
    cells would then be gradeable against every other row's -- which would
    hide the misplaced-cell errors that are the most interesting thing this
    parser does on this corpus.
    """
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        line = " | ".join(re.sub(r"<[^>]+>", " ", c).strip() for c in cells)
        if line.strip(" |"):
            out.append(line)
    return "\n".join(out) if out else re.sub(r"<[^>]+>", " ", html)


def extract(job) -> str:
    els = partition_pdf(filename=str(job["pdf"]), strategy="hi_res",
                        infer_table_structure=True)
    out = []
    for e in els:
        html = getattr(getattr(e, "metadata", None), "text_as_html", None)
        out.append(_rows(html) if html else e.text)
    return "\n".join(x for x in out if x)


if __name__ == "__main__":
    raise SystemExit(run("unstructured", version(), extract, source="pdf"))
