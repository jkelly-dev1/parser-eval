"""Invariants about the corpus and the published evidence.

These are the tests that make the repository's central claim checkable: the
numbers in README.md and FINDINGS.txt come from the files committed beside
them, and the documents those numbers were measured on ship too.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import score                                                    # noqa: E402

PAGES = ROOT / "real" / "pages"
DOCS = ["fdic_balance", "fdic_income", "fdic_earnings",
        "census29_wages", "census29_sales", "fdic2023_balance"]


def truth(doc_id):
    return json.loads((PAGES / f"{doc_id}.truth.json").read_text())


@pytest.mark.parametrize("doc_id", DOCS)
def test_every_page_ships_its_document_its_render_and_its_labels(doc_id):
    # A benchmark whose documents exist only as URLs stops being reproducible
    # the moment a link moves. This is the claim the whole repository rests on.
    assert (PAGES / f"{doc_id}.pdf").exists()
    assert (PAGES / f"{doc_id}_300.png").exists()
    assert (PAGES / f"{doc_id}.truth.json").exists()


def test_every_source_document_has_a_statement_of_rights():
    # PROVENANCE.txt once documented four files while the folder held eight,
    # and the four it omitted included both hand-filled census schedules --
    # the only handwriting in the corpus. README.md's claim that it "states
    # the basis for every document" was false, in the file whose subject is
    # not shipping what you cannot justify.
    prov = (ROOT / "Sample_Documents" / "PROVENANCE.txt").read_text()
    docs = sorted(p for p in (ROOT / "Sample_Documents").iterdir()
                  if p.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"})
    assert docs, "no source documents found"
    for d in docs:
        # Sheets of one archival item are documented under a family heading,
        # so match on the name up to the sheet number.
        stem = d.name.split("-000")[0]
        assert stem in prov, f"{d.name} has no entry in PROVENANCE.txt"


def test_the_control_recovers_nothing_where_there_is_no_text_layer():
    # THE FLOOR. The two 1929 schedules are photographs of paper with no text
    # layer, so the control has nothing to return and scores zero. Without a
    # page like this the comparison collapses into "everything works".
    for doc_id in ["census29_wages", "census29_sales"]:
        out = ROOT / "out_real" / "textlayer" / f"{doc_id}_300.txt"
        assert out.read_text().strip() == "", f"{doc_id} unexpectedly had text"


def test_the_control_does_recover_text_where_there_is_a_layer():
    # The other half: a zero everywhere would pass the test above for the
    # wrong reason.
    out = ROOT / "out_real" / "textlayer" / "fdic2023_balance_300.txt"
    assert len(out.read_text().strip()) > 1000


@pytest.mark.parametrize("tool", ["claude", "gpt", "docling", "unstructured",
                                  "marker", "tesseract", "textlayer"])
def test_published_scores_regenerate_from_the_published_parser_output(tool):
    # The numbers quoted in the prose are re-derived here from the raw text
    # committed beside them. If a future edit changes the grader without
    # regenerating scores.json, or edits scores.json by hand, this fails.
    stored = json.loads((ROOT / "out_real" / "scores.json").read_text())[tool]
    manifest = json.loads(
        (ROOT / "out_real" / tool / "manifest.json").read_text())
    for rec in manifest["records"]:
        if rec.get("error"):
            continue
        key = f"{rec['doc_id']}_{rec['dpi']}"
        if key not in stored["pages"]:
            continue
        text = (ROOT / "out_real" / tool / rec["text_file"]).read_text()
        graded = score.grade_page(truth(rec["doc_id"]), text)
        assert graded["ok"] == stored["pages"][key]["ok"], (
            f"{tool} {key}: regenerated {graded['ok']} ok, "
            f"scores.json says {stored['pages'][key]['ok']}")


def test_the_corpus_is_six_pages_and_425_labeled_values():
    # The headline count, asserted rather than described, because every
    # percentage in the README has it as a denominator. Counted the way the
    # grader counts it: standalone labels PLUS the cells of the row tables,
    # which is where 256 of the 425 live.
    assert len(DOCS) == 6
    total = sum(score.grade_page(truth(d), "")["n_fields"] for d in DOCS)
    assert total == 425, f"corpus holds {total} labeled values, prose says 425"
