"""The adapter driver: what a run records, and what its manifest says.

Every published timing comes out of these manifests, so the driver that
writes them is tested like the grader is. These tests build a two-page corpus
in a temporary directory and drive `common.run` with a fake extractor; no
parser is installed or started.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "adapters"))
import common                                                   # noqa: E402


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    docs = []
    for doc in ("A", "B"):
        docs.append({"doc_id": doc,
                     "files": {"300": {"png": f"{doc}.png", "pdf": f"{doc}.pdf"}}})
    (corpus / "index.json").write_text(json.dumps(
        {"dpis": [300], "documents": docs}))
    return corpus


def _run(monkeypatch, corpus, out, extract):
    monkeypatch.setattr(sys, "argv", ["run_fake", "--corpus", str(corpus),
                                      "--out", str(out)])
    return common.run("fake", "fake 1.0", extract)


def test_a_page_that_raises_is_recorded_and_the_run_continues(tmp_path,
                                                              monkeypatch):
    def extract(job):
        if job["doc_id"] == "A":
            raise RuntimeError("wedged")
        return "text of B"

    out = tmp_path / "out"
    assert _run(monkeypatch, _corpus(tmp_path), out, extract) == 0
    manifest = json.loads((out / "manifest.json").read_text())
    by_doc = {r["doc_id"]: r for r in manifest["records"]}
    assert by_doc["A"]["error"] == "RuntimeError: wedged"
    assert by_doc["B"]["error"] is None
    assert (out / "B_300.txt").read_text() == "text of B"
    assert (out / "A_300.traceback.txt").exists()


def test_a_successful_rerun_removes_the_old_traceback(tmp_path, monkeypatch):
    corpus, out = _corpus(tmp_path), tmp_path / "out"

    def failing(job):
        raise RuntimeError("wedged")

    _run(monkeypatch, corpus, out, failing)
    assert (out / "A_300.traceback.txt").exists()
    _run(monkeypatch, corpus, out, lambda job: "ok")
    assert not (out / "A_300.traceback.txt").exists()
    records = json.loads((out / "manifest.json").read_text())["records"]
    assert [r["error"] for r in records] == [None, None]


def test_the_manifest_merges_and_totals_its_own_records(tmp_path):
    out = tmp_path / "out"
    out.mkdir()

    class Args:
        pass

    args = Args()
    args.out = out
    first = [{"doc_id": "A", "dpi": 300, "seconds": 400.0},
             {"doc_id": "B", "dpi": 300, "seconds": 5.5}]
    common._write_manifest(args, "fake", "1.0", "pdf", first, 0.0)
    # A later one-page run replaces B's record and keeps A's.
    second = [{"doc_id": "B", "dpi": 300, "seconds": 0.25}]
    got = common._write_manifest(args, "fake", "1.0", "pdf", second, 0.0)
    on_disk = json.loads((out / "manifest.json").read_text())
    assert got == on_disk
    assert [(r["doc_id"], r["seconds"]) for r in on_disk["records"]] == [
        ("A", 400.0), ("B", 0.25)]
    # The total is the records' sum, not the duration of the last run.
    assert on_disk["total_seconds"] == pytest.approx(400.25)


def test_every_shipped_manifest_totals_its_own_records():
    manifests = sorted(ROOT.glob("out*/*/manifest.json"))
    assert len(manifests) == 13, [str(m) for m in manifests]
    for path in manifests:
        m = json.loads(path.read_text())
        total = round(sum(r["seconds"] for r in m["records"]), 2)
        assert m["total_seconds"] == pytest.approx(total), path
