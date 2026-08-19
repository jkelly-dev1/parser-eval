"""Invariants about the corpus and the published evidence.

These are the tests that make the repository's central claim checkable: the
numbers in README.md and FINDINGS.txt come from the files committed beside
them, and the documents those numbers were measured on ship too.
"""
import json
import sys
from functools import lru_cache
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
    # and the four it omitted included both hand-filled census schedules:
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
    # The floor. The two 1929 schedules are photographs of paper with no text
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


# Every count grade_page produces, not just the one the headline quotes.
#
# This list is the point of the test. Comparing `ok` alone leaves the entire
# ABSENT / CORRUPT / MISPLACED / typed taxonomy free to move: the thresholds
# that decide CORRUPT, the rule that detects MISPLACED, and the alphabet check
# that decides which corruptions a downstream cast would ACCEPT can all be
# changed with the suite green, and every one of them moves a published
# column. The README calls that taxonomy "the point" and one field of it was
# checked.
GRADED_COUNTS = ("ok", "corrupt", "absent", "misplaced", "corrupt_typed",
                 "rows_anchored", "n_fields", "n_rows")


@lru_cache(maxsize=None)
def _regraded(tool):
    """(stored_page, regenerated) per page, graded ONCE per tool.

    Two tests read this. Grading every page twice doubled the suite's runtime
    for no extra coverage, and the runtime is a documented figure.
    """
    stored = json.loads((ROOT / "out_real" / "scores.json").read_text())[tool]
    manifest = json.loads(
        (ROOT / "out_real" / tool / "manifest.json").read_text())
    out = []
    for rec in manifest["records"]:
        if rec.get("error"):
            continue
        key = f"{rec['doc_id']}_{rec['dpi']}"
        if key not in stored["pages"]:
            continue
        text = (ROOT / "out_real" / tool / rec["text_file"]).read_text()
        out.append((key, stored["pages"][key],
                    score.grade_page(truth(rec["doc_id"]), text)))
    return out


@pytest.mark.parametrize("tool", ["claude", "gpt", "docling", "unstructured",
                                  "marker", "tesseract", "textlayer"])
def test_published_scores_regenerate_from_the_published_parser_output(tool):
    # The numbers quoted in the prose are re-derived here from the raw text
    # committed beside them. If a future edit changes the grader without
    # regenerating scores.json, or edits scores.json by hand, this fails.
    pages = _regraded(tool)
    assert pages, f"{tool}: no page was compared, so this proves nothing"
    for key, page, graded in pages:
        for name in GRADED_COUNTS:
            assert graded[name] == page[name], (
                f"{tool} {key}: regenerated {name}={graded[name]}, "
                f"scores.json says {page[name]}")


@pytest.mark.parametrize("tool", ["claude", "gpt", "docling", "unstructured",
                                  "marker", "tesseract", "textlayer"])
def test_every_published_field_verdict_regenerates(tool):
    """The counts are a summary and the verdicts are the evidence.

    Two graders can agree on how many values were CORRUPT and disagree about
    WHICH ONES, and the per-field map is what the quiet-failure argument is
    actually built on. "Docling put 56 character-perfect values in the wrong
    row" is a claim about identity, not about a count. scores.json ships the
    map, so it is compared.
    """
    pages = _regraded(tool)
    assert pages, f"{tool}: no page was compared, so this proves nothing"
    for key, page, graded in pages:
        want, got = page["fields"], graded["fields"]
        assert set(got) == set(want), (
            f"{tool} {key}: field set changed -- "
            f"only regenerated {sorted(set(got) - set(want))}, "
            f"only stored {sorted(set(want) - set(got))}")
        for field, verdict in want.items():
            assert got[field]["status"] == verdict["status"], (
                f"{tool} {key} {field}: regenerated "
                f"{got[field]['status']}, scores.json says {verdict['status']} "
                f"(printed {verdict['printed']!r})")


def test_the_corpus_is_six_pages_and_425_labeled_values():
    # The headline count, asserted rather than described, because every
    # percentage in the README has it as a denominator. Counted the way the
    # grader counts it: standalone labels PLUS the cells of the row tables,
    # which is where 256 of the 425 live.
    assert len(DOCS) == 6
    total = sum(score.grade_page(truth(d), "")["n_fields"] for d in DOCS)
    assert total == 425, f"corpus holds {total} labeled values, prose says 425"
