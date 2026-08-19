#!/usr/bin/env python3
"""What the cloud runs actually cost, from the responses' own token counts.

    python3 cloud_cost.py out_real/claude out_real/gpt
    python3 cloud_cost.py --all

PRICES ARE DATED AND NOT FROM MEMORY. Both tables below were verified on
2026-08-11 against the providers' own published pricing pages, and the date is
recorded beside them because it is the only thing that makes them auditable.

A PRICE THAT WAS RIGHT WHEN IT WAS WRITTEN CAN STOP BEING TRUE WITH NOTHING IN
THE CODE CHANGING, and it fails silently: every number downstream stays
plausible. A scheduled increase for one model has been announced and then
CANCELED, which leaves code "helpfully" updated to the announced figure wrong
by 50% while looking freshly maintained. IF THIS SCRIPT IS BEING READ MORE THAN A FEW WEEKS
AFTER THE DATE ABOVE, RE-VERIFY AGAINST THE PROVIDERS BEFORE QUOTING ITS
OUTPUT. Do not update these tables from memory; read the pricing page.

WHY COST PER PAGE AND NOT COST PER TOKEN. The two providers tokenize text
differently and count visual tokens differently, so the same page is a
different number of tokens on each. Price per token is not price per page, and
the only sound cross-provider comparison is cost per document, measured on one
corpus. That is what this prints.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# USD per million tokens. (input, output)
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-5.6-sol": (5.00, 30.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.4": (2.50, 15.00),
}
PRICES_VERIFIED = "2026-08-11"


def price_for(model: str) -> tuple[float, float] | None:
    """Exact match first, then the longest prefix that matches.

    Responses come back with a dated id -- "gpt-5.6-sol-2026-xx-xx" -- and a
    lookup that only did exact matches would silently price those at zero. A
    model with no entry returns None and is REPORTED AS UNPRICED rather than
    counted as free.
    """
    if model in PRICES:
        return PRICES[model]
    hits = [k for k in PRICES if model.startswith(k)]
    return PRICES[max(hits, key=len)] if hits else None


def report(out_dir: Path) -> dict | None:
    usage_file = out_dir / "usage.json"
    if not usage_file.exists():
        return None
    rows = json.loads(usage_file.read_text())
    if not rows:
        return None

    total_in = total_out = 0.0
    cost = 0.0
    unpriced = set()
    print(f"\n{out_dir}")
    print(f"  {'page':<20}{'in':>9}{'out':>9}{'cost':>10}")
    for r in rows:
        p = price_for(r["model"])
        c = (r["input_tokens"] * p[0] + r["output_tokens"] * p[1]) / 1e6 if p else 0.0
        if not p:
            unpriced.add(r["model"])
        total_in += r["input_tokens"]
        total_out += r["output_tokens"]
        cost += c
        stem = f"{r['doc_id']}_{r['dpi']}"
        print(f"  {stem:<20}{r['input_tokens']:>9}{r['output_tokens']:>9}"
              f"{('$%.4f' % c) if p else 'UNPRICED':>10}")
    n = len(rows)
    print(f"  {'-' * 47}")
    print(f"  {n} page(s){int(total_in):>15}{int(total_out):>9}{'$%.4f' % cost:>10}")
    print(f"  per page: {int(total_in / n):>6} in {int(total_out / n):>6} out"
          f"   ${cost / n:.4f}")
    for m in sorted(unpriced):
        print(f"  WARNING: no price on file for {m!r}; counted as $0.00")
    return {"dir": str(out_dir), "pages": n, "input_tokens": int(total_in),
            "output_tokens": int(total_out), "cost_usd": round(cost, 4),
            "unpriced": sorted(unpriced)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", type=Path)
    ap.add_argument("--all", action="store_true",
                    help="every directory under out*/ that has a usage.json")
    args = ap.parse_args()

    dirs = list(args.dirs)
    if args.all or not dirs:
        dirs = sorted(p.parent for p in HERE.glob("out*/*/usage.json"))

    print(f"prices verified {PRICES_VERIFIED}; re-verify before quoting these "
          f"if that date is stale")
    totals = [r for d in dirs if (r := report(d))]
    if len(totals) > 1:
        grand = sum(t["cost_usd"] for t in totals)
        print(f"\n{'=' * 49}\n  ALL RUNS: ${grand:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
