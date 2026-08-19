#!/usr/bin/env python3
"""The PDF's own embedded text layer, graded as if it were a parser.

    python3 adapters/run_textlayer.py --corpus real/pages --out out_real/textlayer

THIS IS THE CONTROL, AND WITHOUT IT THREE OF THE FIVE PAGES CANNOT BE READ.
A scanned page may arrive with a text layer somebody else's OCR put there
years ago. The three FDIC pages do: FRASER scanned the 1956 annual report and
embedded its OCR output in the PDF. A parser handed that PDF can return the
embedded text without looking at the pixels at all, and on this corpus two of
them substantially do -- Marker finishes those pages in 0.4 seconds using
`tables_pdftext` and never starts its vision model, and Docling's figures are
a 99-100% subset of the embedded layer.

SO WHAT IS BEING MEASURED, ON THOSE PAGES, IS FRASER'S 1956-SCAN OCR, NOT THE
PARSER. That is not a criticism of either tool: relaying an existing text
layer is fast, cheap and often right, and a production system should probably
do exactly that. But it means "Docling scored 50% on the earnings table" and
"Docling read the earnings table" are different claims, and only this control
tells them apart. A parser that beats the control is reading the page. A
parser that ties it is forwarding somebody else's answer.

IT IS ALSO THE FLOOR, NOT A COMPETITOR. It has no layout model and no
recovery: on a page with no text layer at all -- the two 1929 census
schedules, which are photographs of paper -- it returns nothing and scores
zero, which is the correct result and the reason the corpus needs pages of
both kinds.

WHY pdftotext RATHER THAN A LIBRARY. The point is to extract the layer with
as little interpretation as possible, from a tool with no stake in the
comparison. -layout preserves the column positions the page was printed with,
which is the most generous reading of a table's text layer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import run                                          # noqa: E402


def version() -> str:
    out = subprocess.run(["pdftotext", "-v"], capture_output=True,
                         text=True).stderr
    m = re.search(r"pdftotext version ([\d.]+)", out)
    return f"poppler pdftotext {m.group(1) if m else '?'} -layout"


def extract(job) -> str:
    r = subprocess.run(["pdftotext", "-layout", str(job["pdf"]), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pdftotext exit {r.returncode}: {r.stderr[:200]}")
    return r.stdout


if __name__ == "__main__":
    raise SystemExit(run("textlayer", version(), extract, source="pdf"))
