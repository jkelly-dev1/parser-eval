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


def test_both_hosted_adapters_record_usage_then_refuse_a_stop_that_is_not_a_page():
    """One output handler for both providers. A refused or truncated page was
    billed, so its usage is recorded before the page is refused."""
    import cloud
    cloud.USAGE.clear()
    job = {"doc_id": "d", "dpi": 300}
    assert cloud.finish(job, "m", 10, 5, "end_turn", "text",
                        refused=False, truncated=False) == "text"
    with pytest.raises(RuntimeError, match="refusal"):
        cloud.finish(job, "m", 11, 0, "refusal", "", refused=True,
                     truncated=False)
    with pytest.raises(RuntimeError, match="truncated"):
        cloud.finish(job, "m", 12, 99, "max_tokens", "half a pa",
                     refused=False, truncated=True)
    assert [u["input_tokens"] for u in cloud.USAGE] == [10, 11, 12]
    cloud.USAGE.clear()


def test_a_partial_rerun_merges_usage_instead_of_erasing_it(tmp_path):
    """A --only run covers one page; the cost of the others must survive."""
    import cloud
    path = tmp_path / "usage.json"
    old = [{"doc_id": "a", "dpi": 300, "input_tokens": 1},
           {"doc_id": "b", "dpi": 300, "input_tokens": 2}]
    path.write_text(json.dumps(old))
    merged = cloud.merge_usage(path, [{"doc_id": "b", "dpi": 300,
                                       "input_tokens": 5}])
    assert [(r["doc_id"], r["input_tokens"]) for r in merged] == [("a", 1),
                                                                  ("b", 5)]
    path.write_text(json.dumps({"rows": old}))
    with pytest.raises(ValueError, match="list of usage rows"):
        cloud.merge_usage(path, [])


def test_the_driver_writes_the_merged_usage_and_returns_the_run_exit_code(
        tmp_path, monkeypatch):
    """drive() is what run_claude and run_gpt call: its exit code is the
    run's, and the usage it writes keeps the pages this run did not cover."""
    import argparse
    import cloud
    (tmp_path / "usage.json").write_text(json.dumps(
        [{"doc_id": "a", "dpi": 300, "input_tokens": 1, "output_tokens": 1}]))

    def run(parser_name, version, extract, *, source):
        assert source == "png"
        cloud.USAGE.append({"doc_id": "b", "dpi": 300, "input_tokens": 2,
                            "output_tokens": 2})
        return 1
    monkeypatch.setattr(cloud, "parse_args",
                        lambda name: argparse.Namespace(out=tmp_path))
    monkeypatch.setattr(cloud, "run", run)
    cloud.USAGE.clear()
    assert cloud.drive("claude", "v", None) == 1
    rows = json.loads((tmp_path / "usage.json").read_text())
    assert [r["doc_id"] for r in rows] == ["a", "b"]
    cloud.USAGE.clear()


def test_the_claude_adapter_refuses_a_page_cut_off_by_the_token_limit(monkeypatch):
    """max_tokens is a truncated page, as GPT's `incomplete` is."""
    import types
    import cloud
    import run_claude             # anthropic is imported only inside client()
    resp = types.SimpleNamespace(
        stop_reason="max_tokens", model="claude-opus-5",
        usage=types.SimpleNamespace(input_tokens=7, output_tokens=8),
        content=[types.SimpleNamespace(type="text", text="half")],
        stop_details=None)
    fake = types.SimpleNamespace(messages=types.SimpleNamespace(
        create=lambda **k: resp))
    monkeypatch.setattr(run_claude, "client", lambda: fake)
    monkeypatch.setattr(run_claude, "page_bytes", lambda job: b"png")
    cloud.USAGE.clear()
    with pytest.raises(RuntimeError, match="truncated"):
        run_claude.extract({"doc_id": "d", "dpi": 300})
    assert cloud.USAGE[-1]["output_tokens"] == 8
    cloud.USAGE.clear()


def test_the_gpt_adapter_records_a_truncated_page_then_refuses_it(monkeypatch):
    import types
    import cloud
    import run_gpt                # openai is imported only inside client()
    resp = types.SimpleNamespace(
        status="incomplete", model="gpt-5.6-sol", output_text="half",
        usage=types.SimpleNamespace(input_tokens=3, output_tokens=4),
        incomplete_details="max_output_tokens")
    fake = types.SimpleNamespace(responses=types.SimpleNamespace(
        create=lambda **k: resp))
    monkeypatch.setattr(run_gpt, "client", lambda: fake)
    monkeypatch.setattr(run_gpt, "page_bytes", lambda job: b"png")
    cloud.USAGE.clear()
    with pytest.raises(RuntimeError, match="truncated"):
        run_gpt.extract({"doc_id": "d", "dpi": 300})
    assert cloud.USAGE[-1]["input_tokens"] == 3
    cloud.USAGE.clear()


def test_a_run_in_which_every_page_failed_exits_non_zero(tmp_path, monkeypatch):
    """One failed page leaves the run at 0; a run with nothing to grade is 1."""
    def extract(job):
        raise RuntimeError("nothing works")
    assert _run(monkeypatch, _corpus(tmp_path), tmp_path / "out", extract) == 1
