#!/usr/bin/env python3
"""Cut the graded pages out of their source documents.

    envs/unstructured/bin/python build_real.py
    envs/unstructured/bin/python build_real.py --manifest real/sources.json

WHICH DOCUMENTS IS DATA, NOT CODE. The corpus is described by a manifest --
real/sources.json by default -- so replacing it is an edit to one small file
rather than a change to this script. That matters because a corpus can become
unusable for reasons that have nothing to do with its content: the first one
built here was set aside because its documents could not be redistributed, and
every line of machinery around it was still correct.

MANIFEST FORMAT. A list of objects, each naming one page:

    [{"doc_id":  "balance_p6",
      "file":    "financials/agency_report.pdf",
      "page":    6,
      "note":    "scanned balance sheet, figures sum to printed totals"}]

`file` is relative to this folder, so the recorded provenance names the source
directory as well as the document.

WHY SO FEW PAGES. Ground truth for a real document has to be hand-labeled, and
hand-labeling is where an evaluation quietly becomes fiction: label 200 pages
carelessly and the error bars belong to the labeler rather than to the parser.
A handful of pages labeled by reading them character for character is a small,
honest sample.

WHAT A GOOD CORPUS NEEDS, learned from the first one:
  - HANDWRITING ON A POOR SCAN. It divides the tool families completely;
    without it the comparison collapses into "everything works".
  - INTERNAL ARITHMETIC. Pages whose figures must sum to a printed total let
    the labels be VERIFIED before any parser is graded, and the same sums then
    become the loud-versus-quiet test.
  - A BORN-DIGITAL PAGE WITH A TEXT LAYER, to measure what a parser loses by
    rasterizing a page it could have read directly.
  - A DENSE MULTI-COLUMN TABLE, which is where low resolution does its damage.

PAGES ARE EXTRACTED WITH pypdf AND NOT RE-RENDERED. Running them through
Ghostscript would re-encode them, and for a born-digital page that could alter
the very text layer the ground truth was read out of.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
OUT = HERE / "real" / "pages"
MANIFEST = HERE / "real" / "sources.json"

RASTER_DPI = 300


def load_pages(manifest: Path) -> list[tuple[str, Path, int, str]]:
    """Read the corpus definition.

    THE SOURCE FILE AND PAGE ARE PART OF THE RESULT, NOT BOOKKEEPING. Every
    number produced here is a claim about one page of one document, and a
    reader who cannot walk from "balance_p6 recovered 48 of 48" back to the
    document it was cut from, and to the page inside it, has to take the
    number on trust. So the path recorded in index.json is relative to this
    folder and names the source directory as well as the file.
    """
    if not manifest.exists():
        raise SystemExit(
            f"no corpus manifest at {manifest}.\n"
            f"Write one describing the pages to grade -- see this module's "
            f"docstring for the format -- then run this again.")
    entries = json.loads(manifest.read_text())
    return [(e["doc_id"], HERE / e["file"], int(e["page"]), e.get("note", ""))
            for e in entries]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    docs = []
    for doc_id, src, page, note in load_pages(args.manifest):
        if not src.exists():
            print(f"  {doc_id:<12} MISSING {src}")
            continue
        pdf = OUT / f"{doc_id}.pdf"

        # A SOURCE MAY BE AN IMAGE RATHER THAN A PDF, and archives hand you
        # both. The National Archives serves digitized records as JPEGs, one
        # per sheet, while a report arrives as a PDF to cut a page out of.
        # Wrapping the image in a single-page PDF puts it through the identical
        # pipeline: the parsers that read PDFs get one, the OCR floor gets the
        # PNG, and nothing downstream needs to know which kind of source it
        # came from. `page` is ignored for an image, since the file IS the page.
        if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            from PIL import Image

            Image.MAX_IMAGE_PIXELS = None
            with Image.open(src) as im:
                dpi = im.info.get("dpi", (RASTER_DPI, RASTER_DPI))[0] or RASTER_DPI
                im.convert("RGB").save(pdf, "PDF", resolution=float(dpi))
        else:
            w = PdfWriter()
            w.add_page(PdfReader(str(src)).pages[page - 1])
            with pdf.open("wb") as fh:
                w.write(fh)

        # The PNG is for the OCR floor, which takes an image. Everything else
        # reads the PDF.
        subprocess.run(["pdftoppm", "-r", str(RASTER_DPI), "-png", "-f", "1",
                        "-l", "1", "-singlefile", str(pdf),
                        str(OUT / f"{doc_id}_{RASTER_DPI}")], check=True)

        chars = subprocess.run(["pdftotext", str(pdf), "-"],
                               capture_output=True, text=True).stdout

        # IS THE PAGE A SCAN? "no text layer" is the wrong test, and getting it
        # wrong matters: a scanned page carrying an OCR text layer looks
        # born-digital by character count while being a photograph of paper.
        # The FDIC report is exactly that -- one full-page JBIG2 image with an
        # accurate ABBYY layer over it. A parser that reads the layer inherits
        # someone else's OCR; a parser that reads the pixels does its own. Those
        # are different measurements and the corpus has to say which is which.
        listing = subprocess.run(["pdfimages", "-list", str(pdf)],
                                 capture_output=True, text=True).stdout
        image_rows = [r for r in listing.splitlines()[2:] if r.strip()]
        page_backed = any(int(r.split()[3]) > 1000 and int(r.split()[4]) > 1000
                          for r in image_rows if len(r.split()) > 4)
        text_len = len(chars.strip())
        layer = ("ocr" if page_backed and text_len > 100
                 else "typeset" if text_len > 100 else "none")
        docs.append({
            "doc_id": doc_id,
            "note": note,
            "source": f"{src.relative_to(HERE).as_posix()} page {page}",
            "source_file": src.relative_to(HERE).as_posix(),
            "source_page": page,
            "extracted_pdf": f"{doc_id}.pdf",
            "rasterized_png": f"{doc_id}_{RASTER_DPI}.png",
            "text_layer_chars": text_len,
            "text_layer_source": layer,
            "scanned": page_backed,
            "files": {str(RASTER_DPI): {"png": f"{doc_id}_{RASTER_DPI}.png",
                                        "pdf": f"{doc_id}.pdf"}},
        })
        kind = "SCANNED" if page_backed else "born-digital"
        print(f"  {doc_id:<16}{kind:<13} text layer {text_len:>6} chars "
              f"({layer})")

    (OUT / "index.json").write_text(json.dumps({
        "n": len(docs), "dpis": [RASTER_DPI],
        "note": "Real documents. Ground truth is hand-labeled; see the "
                "*.truth.json files beside this one. source_file and "
                "source_page name the original PDF this page was cut from, "
                "relative to the parser-eval folder; extracted_pdf and "
                "rasterized_png are what was actually parsed.",
        "documents": docs,
    }, indent=2) + "\n")
    print(f"\nwrote {len(docs)} pages to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
