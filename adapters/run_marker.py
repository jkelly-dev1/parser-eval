#!/usr/bin/env python3
"""Marker (marker-pdf 2.0.0) over the corpus.

    TORCH_DEVICE=cpu envs/marker/bin/python adapters/run_marker.py

THE LICENSE IS NOT A FOOTNOTE HERE, AND IT IS NOT WHAT IT USED TO BE. Marker
was GPL-3.0 with a revenue condition on commercial use, which is what the plan
for this evening assumed. The installed 2.0.0 wheel ships an Apache-2.0
LICENSE and declares Apache-2.0 in its metadata; the restriction now sits on
the WEIGHTS instead. surya-2 is released under the AI Pubs OpenRAIL-M license,
which carries use restrictions rather than copyleft. For a firm whose clients
will not put regulated documents in a hosted API, the on-premises parser is
the whole point, so which artifact carries the restriction -- code or weights
-- is a legal question before it is a technical one, and it belongs beside the
accuracy number rather than under it. Checked against the installed package,
not from memory: see FINDINGS.txt section 7.

MARKER WANTS A GPU AND THIS MACHINE HAS NONE. It is run here on CPU anyway,
because "not run, and why" is a weaker answer than a measured one, and because
the per-page time on CPU is itself a deployment fact worth recording. If it
turns out to be unusably slow on this hardware, that is the result.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("TORCH_DEVICE", "cpu")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import run                                          # noqa: E402

from marker.converters.pdf import PdfConverter                  # noqa: E402
from marker.models import create_model_dict                     # noqa: E402
from marker.output import text_from_rendered                    # noqa: E402

CONV = PdfConverter(artifact_dict=create_model_dict())


def version() -> str:
    from importlib.metadata import version as v
    return f"marker-pdf {v('marker-pdf')} (surya-ocr {v('surya-ocr')}), CPU"


def extract(job) -> str:
    rendered = CONV(str(job["pdf"]))
    text, _, _ = text_from_rendered(rendered)
    return text


if __name__ == "__main__":
    raise SystemExit(run("marker", version(), extract, source="pdf"))
