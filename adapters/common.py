"""Shared plumbing for the parser adapters. Pure standard library.

Each parser runs in its OWN virtualenv, so this module is imported by three
different interpreters and must not depend on anything any of them installed.

The contract every adapter honors, and the reason there is a contract at all:
the exercise is a comparison of parsers, and a comparison where each parser
was invoked slightly differently measures the invocation. So each adapter
takes the same arguments, reads the same frozen corpus, and writes one .txt of
whatever text the parser produced plus one record with the wall-clock time and
the version of the thing that produced it.

Text is the common denominator on purpose. Docling emits Markdown, Unstructured
emits a list of typed elements, Marker emits Markdown, Tesseract emits plain
text. Grading whichever structured form each one prefers would grade four
different things. Grading the text they all can produce asks the one question
that is the same for all of them: did the characters on the page come back.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def parse_args(parser_name: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog=f"run_{parser_name}")
    ap.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / parser_name)
    ap.add_argument("--dpi", type=int, action="append", default=None,
                    help="repeatable; default 150 and 300")
    ap.add_argument("--only", default=None, help="one doc_id, for a smoke test")
    # A parser that wedges on one document must not cost you the other nine.
    # Marker hangs on PO00003. The request times out, the server keeps burning
    # CPU, and nothing after it in the job list ever runs. Skipping the
    # known-bad document and attempting it separately under a timeout is the
    # difference between nine graded pages and none.
    ap.add_argument("--skip", action="append", default=[],
                    help="doc_id to leave out; repeatable")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    return a


def pages(args) -> list[dict]:
    """Every (doc, dpi) job the adapter should run, in a stable order.

    THE DEFAULT DPIs come from the corpus, not from a constant. They used to
    default to [150, 300], which were the two the synthetic corpus happens to
    render. The real corpus renders 300 only. The 150 DPI cliff is already
    measured and re-measuring it on scans of a 1956 report answers nothing,
    so every documented command in the status file died on `KeyError: '150'`
    before parsing a single page. A corpus states which renderings it has in
    index.json and that is the answer to the question.

    An explicitly requested DPI that is missing still fails, but it now says
    what it wanted and what exists, rather than raising a bare KeyError from
    inside a dict lookup two frames down.
    """
    index = json.loads((args.corpus / "index.json").read_text())
    dpis = args.dpi or index.get("dpis") or [150, 300]
    jobs = []
    for entry in index["documents"]:
        if args.only and entry["doc_id"] != args.only:
            continue
        if entry["doc_id"] in args.skip:
            continue
        for dpi in dpis:
            f = entry["files"].get(str(dpi))
            if f is None:
                raise SystemExit(
                    f"{entry['doc_id']} has no {dpi} DPI rendering in "
                    f"{args.corpus / 'index.json'} (it has "
                    f"{', '.join(sorted(entry['files']))})")
            jobs.append({
                "doc_id": entry["doc_id"], "dpi": dpi,
                "png": args.corpus / f["png"], "pdf": args.corpus / f["pdf"],
            })
    if args.limit:
        jobs = jobs[:args.limit]
    return jobs


def run(parser_name: str, version: str, extract, *, source: str = "pdf"):
    """Drive `extract(job) -> str` over the corpus and record the results.

    A parser that raises on one page is recorded as an error on THAT page and
    the run continues. Losing nine good pages because the tenth crashed would
    be a worse outcome than the crash, and "it failed on 1 of 10" is itself a
    result worth reporting.
    """
    args = parse_args(parser_name)
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = pages(args)
    records = []
    t_all = time.time()

    for job in jobs:
        stem = f"{job['doc_id']}_{job['dpi']}"
        t0 = time.time()
        try:
            text = extract(job)
            err = None
        except Exception as e:                                   # noqa: BLE001
            text, err = "", f"{type(e).__name__}: {e}"
            (args.out / f"{stem}.traceback.txt").write_text(
                traceback.format_exc())
        dt = time.time() - t0
        (args.out / f"{stem}.txt").write_text(text)
        records.append({"doc_id": job["doc_id"], "dpi": job["dpi"],
                        "seconds": round(dt, 2), "chars": len(text),
                        "error": err, "text_file": f"{stem}.txt"})
        print(f"  {stem:<18} {dt:6.1f}s  {len(text):6d} chars"
              f"{'  ERROR ' + err if err else ''}", flush=True)
        # The manifest is written after every page, not at the end. A parser
        # that hangs has to be killed from outside, and a kill lands between
        # pages, so an end-of-run write loses every page the run completed.
        # Marker hangs often enough on this hardware that the difference is
        # the whole corpus.
        _write_manifest(args, parser_name, version, source, records, t_all)

    manifest = _write_manifest(args, parser_name, version, source, records,
                               t_all)
    print(f"\n{parser_name}: {len(records)} pages in "
          f"{manifest['total_seconds']}s -> {args.out}")
    return 0

def _write_manifest(args, parser_name, version, source, records, t_all):
    """Write the manifest, MERGING with whatever is already on disk.

    A run merges rather than replaces so a corpus can be finished in pieces.
    Without this, running the six good documents and then the awkward one
    leaves a manifest describing only the awkward one, and the twelve pages on
    disk beside it are invisible to the grader. Records are keyed by
    (doc_id, dpi), so re-running a page replaces its record rather than
    duplicating it.
    """
    kept = []
    path = args.out / "manifest.json"
    if path.exists():
        fresh = {(r["doc_id"], r["dpi"]) for r in records}
        kept = [r for r in json.loads(path.read_text()).get("records", [])
                if (r["doc_id"], r["dpi"]) not in fresh]
    manifest = {
        "parser": parser_name,
        "version": version,
        "source": source,
        "note": "Wall-clock seconds are on a 12-core CPU with no GPU, and "
                "include model load on the first page of the run.",
        "total_seconds": round(time.time() - t_all, 1),
        "records": sorted(kept + records,
                          key=lambda r: (r["doc_id"], r["dpi"])),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
