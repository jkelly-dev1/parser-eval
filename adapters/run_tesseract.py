#!/usr/bin/env python3
"""Tesseract, straight, as the floor.

    python3 adapters/run_tesseract.py

WHY A FLOOR IS PART OF THE MEASUREMENT. Every one of the purpose-built parsers
is a layout model in front of an OCR engine, and several of them run Tesseract
or a Tesseract-class recognizer underneath. Reporting Docling at 94% without
reporting what raw OCR scores on the same pages hides whether the layout model
bought anything at all. This adapter needs no virtualenv and no download: it
shells out to /usr/bin/tesseract.

It reads the PNG rather than the PDF, because handing Tesseract a PDF means
rasterizing it back to a PNG first, and the PNG is what the PDF contains.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import run                                          # noqa: E402


def version() -> str:
    out = subprocess.run(["tesseract", "--version"], capture_output=True,
                         text=True, check=True).stdout
    return out.splitlines()[0].strip()


# PAGE SEGMENTATION MODE IS LEFT AT THE DEFAULT (--psm 3, automatic), which is
# what someone gets by typing `tesseract page.png stdout`. The three plausible
# modes were compared on PO00002 at 300 DPI before choosing:
#
#     psm 3 (default)   whole page recovered, blank line between every line
#     psm 4 (column)    whole page recovered, tighter
#     psm 6 (one block) DROPPED THE "PURCHASE ORDER" TITLE ENTIRELY
#
# psm 6 is the mode most often suggested for tables, and on this page it is the
# one that silently loses content. Picking the mode that scores best would be
# tuning the floor; the default is the honest floor.
def extract(job) -> str:
    r = subprocess.run(["tesseract", str(job["png"]), "stdout"],
                       capture_output=True, text=True, check=True)
    return r.stdout


if __name__ == "__main__":
    raise SystemExit(run("tesseract", version(), extract, source="png"))
