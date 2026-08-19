#!/usr/bin/env python3
"""Turn the six real pages into scans at 150 and 300 DPI.

    envs/unstructured/bin/python build_scan.py

Why this exists and why it is a separate corpus. Real/pages/ holds the pages
exactly as they were cut out of their source documents, text layer and all,
because that is what a user actually feeds a parser. It is the right corpus
for "which parser reads my documents" and it is USELESS for asking about
resolution: four of the six pages carry a text layer, one typeset by the
publisher and three carrying somebody else's OCR, and on those pages the
parsers that lead the table are relaying that layer rather than looking at
the paper. Changing the DPI of a PNG that nothing reads changes nothing.

That is measured here, not assumed. Adapters/run_textlayer.py returns the
embedded text layer and does no work at all, and it beats several real
parsers on exactly those four pages; on the born-digital one it scores 100%,
which no local parser matches and the two hosted models only tie. The 1929
schedules have no text layer, so they are the only pages in real/pages/ where
resolution could matter, and two pages is not a resolution experiment.

This corpus deliberately destroys the text layer. Every page is rendered to an
image and wrapped back into an image-only PDF, at 150 DPI and at 300 DPI, so
that every parser sees the same pixels and nothing else varies but the
resolution. The synthetic corpus in ./corpus was frozen the same way and for
the same reason. This exists to answer one question:

    Tesseract went from 49.7% to 96.8% between 150 and 300 DPI on generated
    purchase orders, and 113 of its 172 misses at 150 DPI were values that
    still parse. Does that hold on real pages, and does it happen to the
    layout models too?

Not yet answered. Real/scan/ has not been built against this corpus, so no
result in the README or in FINDINGS.txt comes from here. The README's
resolution table is still the synthetic one, and it says so.

What this corpus cannot tell you. The 300 DPI column here is NOT the same
measurement as the 300 DPI column in out_real/. There, the four pages with a
text layer still had it and Docling, Unstructured and Marker could copy it;
here they cannot. Comparing the two is how you measure what the text layer is
worth, which is a different and also interesting question, but it is not a
resolution comparison, and the numbers must not be mixed into one table.

The ground truth is not copied: score.py --truth points back at
real/pages/*.truth.json, so there is exactly one set of hand labels for these
six pages and no chance of the two drifting apart.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "real" / "pages"
OUT = HERE / "real" / "scan"
DPIS = (150, 300)


def main() -> int:
    from PIL import Image

    # No page here is near PIL's 89.5 Mpx guard, the largest is
    # fdic_earnings at 4.9 Mpx, but the guard is a decompression-bomb
    # defense, not a correctness one, and a later page could trip it.
    Image.MAX_IMAGE_PIXELS = None
    OUT.mkdir(parents=True, exist_ok=True)
    src_index = json.loads((SRC / "index.json").read_text())
    docs = []

    for entry in src_index["documents"]:
        doc_id = entry["doc_id"]
        pdf = SRC / entry["files"]["300"]["pdf"]
        files = {}
        for dpi in DPIS:
            stem = f"{doc_id}_{dpi}"
            # pdftoppm rather than PIL for the rasterizing, so the pixels come
            # from the same renderer that produced the 300 DPI PNGs already in
            # real/pages/ and this corpus is not a second measurement of
            # poppler versus something else.
            subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-f", "1",
                            "-l", "1", "-singlefile", str(pdf),
                            str(OUT / stem)], check=True)
            png = (OUT / f"{stem}.png").read_bytes()
            with Image.open(io.BytesIO(png)) as im:
                # resolution=dpi so a parser that asks the PDF how big the page
                # is gets the physical size it was drawn at, not 72 DPI.
                im.convert("RGB").save(OUT / f"{stem}.pdf", "PDF",
                                       resolution=float(dpi))
                w, h = im.size
            files[str(dpi)] = {"png": f"{stem}.png", "pdf": f"{stem}.pdf",
                               "width": w, "height": h}
            print(f"  {stem:<18} {w:>5} x {h:<5} px   "
                  f"{len(png) / 1e6:5.1f} MB png")

        docs.append({
            "doc_id": doc_id,
            "note": entry["note"],
            "source": entry["source"],
            "source_file": entry["source_file"],
            "source_page": entry["source_page"],
            "from_page_pdf": entry["files"]["300"]["pdf"],
            "text_layer_chars": 0,
            "scanned": True,
            "files": files,
        })

    (OUT / "index.json").write_text(json.dumps({
        "n": len(docs), "dpis": list(DPIS),
        "note": "The six real pages re-rendered as image-only PDFs at two "
                "resolutions, so that resolution is the only thing that "
                "differs between the two runs. THE TEXT LAYER IS GONE ON "
                "PURPOSE -- see build_scan.py. Ground truth is not copied "
                "here; grade with score.py --truth real/pages.",
        "documents": docs,
    }, indent=2) + "\n")
    print(f"\nwrote {len(docs)} pages x {len(DPIS)} resolutions to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
