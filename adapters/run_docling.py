#!/usr/bin/env python3
"""Docling (IBM, MIT license) over the frozen corpus.

    envs/docling/bin/python adapters/run_docling.py

DEFAULT PIPELINE, DELIBERATELY. Docling has knobs -- OCR engine, table
structure model, cell matching -- and tuning them for this corpus would answer
a question nobody asked ("how well can Docling be made to do on ten synthetic
purchase orders?") instead of the one that matters ("what does a team get when
they install it and point it at a scan?"). The only thing set explicitly is
that OCR must run, because every page here is an image with no text layer and
a silent no-OCR fallback would be recorded as a parser that returned nothing.

MARKDOWN IS THE OUTPUT because it is Docling's own primary export and it keeps
the table as a table. The grader flattens the pipes back out.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import run                                          # noqa: E402

from docling.datamodel.base_models import InputFormat            # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.document_converter import (DocumentConverter,       # noqa: E402
                                        PdfFormatOption)

opts = PdfPipelineOptions()
opts.do_ocr = True
opts.do_table_structure = True

CONV = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def version() -> str:
    from importlib.metadata import version as v
    return f"docling {v('docling')} (docling-core {v('docling-core')})"


def extract(job) -> str:
    res = CONV.convert(str(job["pdf"]))
    return res.document.export_to_markdown()


if __name__ == "__main__":
    raise SystemExit(run("docling", version(), extract, source="pdf"))
