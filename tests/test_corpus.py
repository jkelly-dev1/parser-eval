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


#: The two corpora, and where each one's labels live. out_real/ is the real
#: six-page corpus the headline table is measured on; out/ is the generated
#: purchase-order corpus behind README's resolution table. Both ship a
#: scores.json quoting figures in the README, so both are regenerated.
CORPORA = {"out_real": ROOT / "real" / "pages", "out": ROOT / "corpus"}


def truth(doc_id, labels=None):
    return json.loads(((labels or PAGES) / f"{doc_id}.truth.json").read_text())


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
# This list is the point of the test. Comparing `ok` alone leaves the rest of
# the taxonomy (absent, corrupt, misplaced, typed) free to move: the thresholds
# that decide CORRUPT, the rule that detects MISPLACED, and the alphabet check
# that decides which corruptions a downstream cast would ACCEPT can all be
# changed with the suite green, and every one of them moves a published
# column. The README calls that taxonomy "the point" and one field of it was
# checked.
GRADED_COUNTS = ("ok", "corrupt", "absent", "misplaced", "corrupt_typed",
                 "rows_anchored", "n_fields", "n_rows")


@lru_cache(maxsize=None)
def _regraded(tool, corpus="out_real"):
    """(stored_page, regenerated) per page, graded ONCE per tool and corpus.

    Two tests read this. Grading every page twice doubled the suite's runtime
    for no extra coverage, and the runtime is a documented figure.
    """
    stored = json.loads((ROOT / corpus / "scores.json").read_text())[tool]
    manifest = json.loads(
        (ROOT / corpus / tool / "manifest.json").read_text())
    labels = CORPORA[corpus]
    out = []
    for rec in manifest["records"]:
        if rec.get("error"):
            continue
        key = f"{rec['doc_id']}_{rec['dpi']}"
        if key not in stored["pages"]:
            continue
        text = (ROOT / corpus / tool / rec["text_file"]).read_text()
        out.append((key, stored["pages"][key],
                    score.grade_page(truth(rec["doc_id"], labels), text)))
    return out


#: (corpus, tool) pairs that actually ship output. The generated corpus has no
#: textlayer column: its pages are rendered image-only, so there is no layer
#: to return and the control does not appear in that table.
CORPUS_TOOLS = (
    [("out_real", t) for t in ["claude", "gpt", "docling", "unstructured",
                               "marker", "tesseract", "textlayer"]]
    + [("out", t) for t in ["claude", "gpt", "docling", "unstructured",
                            "marker", "tesseract"]])


@pytest.mark.parametrize("corpus,tool", CORPUS_TOOLS)
def test_published_scores_regenerate_from_both_published_corpora(corpus, tool):
    # The numbers quoted in the prose are re-derived here from the raw text
    # committed beside them. If a future edit changes the grader without
    # regenerating scores.json, or edits scores.json by hand, this fails.
    pages = _regraded(tool, corpus)
    assert pages, f"{corpus}/{tool}: no page compared, so this proves nothing"
    for key, page, graded in pages:
        for name in GRADED_COUNTS:
            assert graded[name] == page[name], (
                f"{corpus} {tool} {key}: regenerated {name}={graded[name]}, "
                f"scores.json says {page[name]}")


@pytest.mark.parametrize("corpus,tool", CORPUS_TOOLS)
def test_every_published_field_verdict_regenerates(corpus, tool):
    """The counts are a summary and the verdicts are the evidence.

    Two graders can agree on how many values were CORRUPT and disagree about
    WHICH ONES, and the per-field map is what the quiet-failure argument is
    actually built on. "Docling put 56 character-perfect values in the wrong
    row" is a claim about identity, not about a count. scores.json ships the
    map, so it is compared.
    """
    pages = _regraded(tool, corpus)
    assert pages, f"{corpus}/{tool}: no page compared, so this proves nothing"
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


def test_the_documented_suite_size_is_the_collected_count():
    """README.md and SAMPLE_RUN.md both state how many tests the suite has,
    and SAMPLE_RUN.md shows the run that printed it. The count is collected
    here, in a child process over the whole tests directory, so this test
    measures the same suite however it is itself invoked."""
    import re
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", str(ROOT / "tests")],
        capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    m = re.search(r"^(\d+) tests? collected", r.stdout, re.M)
    assert m, r.stdout[-2000:]
    n = int(m.group(1))
    readme = (ROOT / "README.md").read_text()
    sample = (ROOT / "SAMPLE_RUN.md").read_text()
    assert f"The suite is {n} tests," in readme
    assert f"The suite is {n} tests," in sample
    assert re.search(rf"^{n} passed in [\d.]+s$", sample, re.M)
