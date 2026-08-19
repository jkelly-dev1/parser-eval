"""Re-derive every published number in README.md from out_real/*.json.

A README is prose and drifts; out_real/*.json is evidence and does not. This
script rebuilds each figure from the JSON and asserts the exact string is
present in the README, so a re-run that shifts a figure fails loudly instead of
leaving the document quietly wrong.

    python3 check_readme_numbers.py            check
    python3 check_readme_numbers.py --emit     print what it derives

At the repository root, NOT IN scripts/. Every other tool here lives at the
root, and adding a one-file scripts/ directory to match another repository's
layout would be tidier for the checker and wrong for the reader.

Whitespace AND emphasis are normalized on both sides, so a reflowed paragraph
is not a false alarm that trains a reader to ignore the script.

The per-page table is the one that matters here, and it is derived cell
by cell.
The corpus row hides both findings this repository exists to report: the
control ties the hosted models on the born-digital page and scores zero on the
two handwritten ones, and a table checked only at the bottom line would let
either of those move without a sound.

What is NOT derived, said here rather than left to be discovered: the McNemar
p-values, which come from a paired test this file does not run, and the two
worked examples in prose, which quote cell values rather than a computed
figure. A deriver that encoded a guess at either would pass and certify the
guess.

The count is printed whether OR NOT anything is missing, so a version of this
script that quietly stopped deriving half of them is visible rather than clean.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

#: Column order as the README prints it, best first. Held here because the
#: order is an editorial choice and the JSON is a dict keyed by tool.
TOOLS = ["gpt", "claude", "marker", "textlayer", "unstructured", "docling",
         "tesseract"]

#: Row order as the README prints it. The first page is born-digital and every
#: other one is a photograph of paper, which is the distinction the table
#: exists to show.
PAGES = ["fdic2023_balance", "fdic_balance", "fdic_income", "fdic_earnings",
         "census29_wages", "census29_sales"]

DPI = "300"


def load(name):
    with open(os.path.join(ROOT, "out_real", name), encoding="utf-8") as fh:
        return json.load(fh)


def rows_per_page():
    """One row per page: what each tool recovered, in the right row."""
    scores = load("scores.json")
    out = []
    for page in PAGES:
        key = "%s_%s" % (page, DPI)
        cells, fields = [], None
        for tool in TOOLS:
            p = scores[tool]["pages"][key]
            fields = p["n_fields"]
            cells.append("%.1f%%" % (100.0 * p["ok"] / p["n_fields"]))
        out.append(("page:" + page,
                    "%s | %d | %s |" % (page, fields, " | ".join(cells))))
    return out


def rows_corpus():
    scores = load("scores.json")
    rec = ["%.1f%%" % (100.0 * scores[t]["by_dpi"][DPI]["recovery"])
           for t in TOOLS]
    secs = ["%.1f" % scores[t]["by_dpi"][DPI]["seconds_per_page"]
            for t in TOOLS]
    fields = scores[TOOLS[0]]["by_dpi"][DPI]["fields"]
    return [("corpus:recovery",
             "corpus | %d | %s |" % (fields, " | ".join(rec))),
            ("corpus:seconds",
             "seconds/page | | %s |" % " | ".join(secs))]


def _reconcile_totals():
    out = {}
    for tool, pages in load("reconcile.json").items():
        tot = {}
        for page in pages.values():
            for k, n in page["counts"].items():
                tot[k] = tot.get(k, 0) + n
        out[tool] = tot
    return out


def prose_figures():
    scores = load("scores.json")
    rec = _reconcile_totals()
    hosted_broken = rec["gpt"]["BROKEN"] + rec["claude"]["BROKEN"]
    hosted_survived = rec["gpt"]["SURVIVES"] + rec["claude"]["SURVIVES"]
    tess = scores["tesseract"]["by_dpi"][DPI]
    doc = scores["docling"]["by_dpi"][DPI]
    return [
        # The control breaking no sum belongs to the same sentence and is
        # derived with it, because "hosted models produced no quiet failures"
        # only means something beside a control that also produced none.
        ("prose:quiet",
         "Hosted models produced no quiet failures: %d broken sums, %d "
         "survived. The control breaks %s at all."
         % (hosted_broken, hosted_survived,
            "none" if rec["textlayer"]["BROKEN"] == 0 else
            str(rec["textlayer"]["BROKEN"]))),
        ("prose:structure",
         "Tesseract finds %d of %d rows, more than any other local tool, and "
         "still recovers only %.1f%%."
         % (tess["rows_anchored"], tess["rows"], 100.0 * tess["recovery"])),
        ("prose:misplaced",
         "Docling recovers less and put %d character-perfect values in the "
         "wrong row" % doc["misplaced"]),
    ]


def emit():
    return rows_per_page() + rows_corpus() + prose_figures()


def squash(text):
    text = text.replace("**", "").replace("`", "").replace("*", "")
    return re.sub(r"\s+", " ", text)


def main():
    derived = emit()
    if "--emit" in sys.argv:
        for tag, row in derived:
            print("%s\n%s" % (tag, row))
        return 0
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = squash(fh.read())
    missing = [(t, r) for t, r in derived if squash(r) not in readme]
    for tag, row in missing:
        print("MISSING [%s]\n  %s" % (tag, row))
    tables = sum(1 for t, _ in derived if not t.startswith("prose:"))
    print("\n%d of %d derived figures found verbatim in README.md "
          "(%d table rows, %d in prose)"
          % (len(derived) - len(missing), len(derived), tables,
             len(derived) - tables))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
