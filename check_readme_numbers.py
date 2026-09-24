"""Re-derive every published number in the summary documents from out_real/*.json.

Prose drifts; out_real/*.json is evidence and does not. This script rebuilds
each figure from the JSON and asserts the exact string is present in the
document that quotes it, so a re-run that shifts a figure fails loudly instead
of leaving the document quietly wrong.

    python3 check_readme_numbers.py            check
    python3 check_readme_numbers.py --emit     print what it derives

It reads five surfaces, not one, and the name is narrower than the job.
README.md is not the only document here that quotes these artifacts:
FINDINGS.txt carries five tables built from them, SAMPLE_RUN.md presents
command output as captured, and GITHUB_DESCRIPTION.txt states the headline.
A deriver that covers one of the four teaches a reader that the numbers are
checked, which is worse for them than not checking at all: the three it
skips are exactly where a figure can go stale without a sound.

    README.md               the table, and the prose figures around it
    FINDINGS.txt            five tables and the claims drawn from them
    SAMPLE_RUN.md           captured output, which must still be what the
                            commands print
    GITHUB_DESCRIPTION.txt  one sentence, the one most often read
    SECURITY.md             what the repository contains, stated to the reader
                            most likely to check whether it does

At the repository root, NOT IN scripts/. Every other tool here lives at the
root, and adding a one-file scripts/ directory to match another repository's
layout would be tidier for the checker and wrong for the reader.

Whitespace AND emphasis are normalized on both sides, so a reflowed paragraph or
a re-widened table column is not a false alarm that trains a reader to ignore the
script. That is deliberate: these tables are fixed-width and their column widths
are not a claim about anything.

The per-page table is the one that matters most, and it is derived cell by cell.
The corpus row hides both findings this repository exists to report: the control
ties the hosted models on the born-digital page and scores zero on the two
handwritten ones, and a table checked only at the bottom line would let either of
those move without a sound.

What is NOT derived, said here rather than left to be discovered:

  - The test count ("56 tests"). Counting `def test_` gives 34, because the
    suite parametrizes; getting 56 needs pytest, and this file is stdlib-only so
    that a reader can re-check the arithmetic with an interpreter and nothing
    else. tests/test_corpus.py owns that claim instead.
  - Wall-clock seconds in SAMPLE_RUN's captured blocks, which cannot reproduce
    between two runs and say nothing about whether the text came back right.

The McNemar p-values are derived from the per-field verdicts in scores.json,
because they are the most tempting figure here to type by hand. They decide the repository's headline: "loses to the control"
and "is not distinguishable from the control" are different claims about the
same three tools, and only the paired test separates them. A figure that
decides a headline is the last one that should be a constant in a document.

The count is printed whether OR NOT anything is missing, so a version of this
script that quietly stopped deriving half of them is visible rather than clean.
"""

import glob
import json
import math
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

#: The four FDIC pages. fdic_balance, the one FDIC page Marker spent 52
#: seconds on, is the counterexample in the timing argument.
FDIC = ["fdic2023_balance", "fdic_balance", "fdic_income", "fdic_earnings"]

#: The control. Every "loses to doing nothing" claim is measured against it.
CONTROL = "textlayer"

DPI = "300"

README = "README.md"
FINDINGS = "FINDINGS.txt"
SAMPLE_RUN = "SAMPLE_RUN.md"
GH_DESC = "GITHUB_DESCRIPTION.txt"
SECURITY = "SECURITY.md"


def load(name):
    with open(os.path.join(ROOT, "out_real", name), encoding="utf-8") as fh:
        return json.load(fh)


def load_out(name):
    """The generated corpus, which lives in out/ rather than out_real/."""
    with open(os.path.join(ROOT, "out", name), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- the README

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
        out.append((README, "page:" + page,
                    "%s | %d | %s |" % (page, fields, " | ".join(cells))))
    return out


def rows_corpus():
    scores = load("scores.json")
    rec = ["%.1f%%" % (100.0 * scores[t]["by_dpi"][DPI]["recovery"])
           for t in TOOLS]
    secs = ["%.1f" % scores[t]["by_dpi"][DPI]["seconds_per_page"]
            for t in TOOLS]
    fields = scores[TOOLS[0]]["by_dpi"][DPI]["fields"]
    return [(README, "corpus:recovery",
             "corpus | %d | %s |" % (fields, " | ".join(rec))),
            (README, "corpus:seconds",
             "seconds/page | | %s |" % " | ".join(secs))]


# ------------------------------------------------------- shared computations

def _reconcile_totals(include_cross_page=True):
    """Per-tool rule verdict totals.

    include_cross_page decides which of TWO different numbers you get, and
    conflating them is a mistake this repository has already made in print.
    The 105 within-page rules and the 7 cross-page identities are separate
    populations: FINDINGS section 4's table is the first, and the README's
    "5 broken sums" sentence is both together.
    """
    out = {}
    for tool, pages in load("reconcile.json").items():
        tot = {}
        for name, page in pages.items():
            if name == "cross_page" and not include_cross_page:
                continue
            for k, n in page["counts"].items():
                tot[k] = tot.get(k, 0) + n
        out[tool] = tot
    return out


def _casts_as_number(token):
    """Would a downstream numeric cast ACCEPT this token?

    This is the split that decides whether a surviving misread is quiet or
    merely lucky. "2,027,324!" balances the sum and still explodes the moment
    anything reads it as a number; "1,355" for a printed "1,352" does not.
    """
    try:
        float(token.replace(",", "").replace("$", "").strip())
        return True
    except ValueError:
        return False


_READ_AS = re.compile(r"read as '([^']*)' \(printed '([^']*)'\)")


def _survives_inventory():
    """Every SURVIVES instance in the shipped reconciliation.

    Returns (total, loud, quiet, tolerance_backed). A SURVIVES is a rule that
    still balances although a figure came back wrong, which is the error class
    this whole project was built to count, so what it contains is the one
    inventory a summary document must not paraphrase from memory.
    """
    data = load("reconcile.json")
    total = loud = quiet = tol = 0
    for tool in data:
        for page in data[tool].values():
            for rule in page.get("detail", []):
                if rule["status"] != "SURVIVES":
                    continue
                total += 1
                misread = [m.group(1) for n in rule.get("notes", [])
                           for m in [_READ_AS.search(n)] if m]
                clean = all(_casts_as_number(t) for t in misread) and misread
                if clean:
                    quiet += 1
                    if any("tolerance" in n for n in rule.get("notes", [])):
                        tol += 1
                else:
                    loud += 1
    return total, loud, quiet, tol


def _ok_map(scores, tool):
    """Per-value pass/fail for one tool, keyed so two tools can be paired."""
    return {(page, field): v["status"] == "OK"
            for page, pv in scores[tool]["pages"].items()
            for field, v in pv["fields"].items()}


def _mcnemar_exact(a, b):
    """Two-sided exact McNemar over paired per-value verdicts.

    Paired, because both tools were run over THE SAME 425 values: an unpaired
    test on two accuracy percentages would answer a question nobody asked and
    would call a 3.5-point gap significant on this corpus.

    Returns (a_only, b_only, p). Only the discordant pairs carry information,
    which is the whole point of the test: 425 values where both tools agree say
    nothing about which is better.
    """
    n01 = sum(1 for k in a if a[k] and not b.get(k, False))
    n10 = sum(1 for k in a if b.get(k, False) and not a[k])
    n = n01 + n10
    if n == 0:
        return n01, n10, 1.0
    k = min(n01, n10)
    p = 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return n01, n10, min(p, 1.0)


def _control_comparison():
    """Each local tool against the control, paired, with its exact p-value.

    This is the measurement behind the repository's headline sentence, and the
    reason that sentence must be derived rather than typed: "loses to" and "is
    not distinguishable from" are different claims, and three documents made
    the stronger one where the data supports the weaker.
    """
    scores = load("scores.json")
    control = _ok_map(scores, CONTROL)
    out = {}
    for tool in TOOLS:
        # EVERY PARSER, not just the four local ones. The sentence this feeds
        # says "of six parsers", and a count that says six while the loop
        # examined four is asserting about a population it did not look at,
        # even when, as here, the two hosted columns could not change the
        # answer. Their p-values come back at 0.0000 in the other direction
        # and they fall out of both lists on the `control_only > tool_only`
        # test, which is the comparison doing the work rather than a filter
        # deciding the result in advance.
        if tool == CONTROL:
            continue
        c_only, t_only, p = _mcnemar_exact(control, _ok_map(scores, tool))
        rec = scores[tool]["by_dpi"][DPI]["recovery"]
        out[tool] = {"control_only": c_only, "tool_only": t_only, "p": p,
                     "recovery": rec,
                     # "Loses" requires BOTH: the control ahead, and the gap
                     # outside the noise. Either alone is a weaker claim.
                     "loses": p < 0.05 and c_only > t_only}
    return out


def _headline_counts():
    cmp_ = _control_comparison()
    loses = sorted(t for t, v in cmp_.items() if v["loses"])
    draws = sorted(t for t, v in cmp_.items()
                   if not v["loses"] and v["control_only"] > v["tool_only"])
    return cmp_, loses, draws


def _marker_fdic_times():
    """Marker's wall-clock on each FDIC page, with whether the page has a
    text layer. The timing argument is built on this pairing and on nothing
    else, so the pairing is what gets derived."""
    man = load("marker/manifest.json")
    idx = {d["doc_id"]: d for d in
           json.load(open(os.path.join(ROOT, "real", "pages", "index.json"),
                          encoding="utf-8"))["documents"]}
    return {r["doc_id"]: (r["seconds"], idx[r["doc_id"]]["text_layer_chars"])
            for r in man["records"] if r["doc_id"] in FDIC}


def _subset_of_layer(tool):
    """Of the values this tool got right on the FDIC pages, how many did the
    embedded text layer also get right? The claim "a 99-100% subset of the
    embedded layer" is about this ratio and is false for Docling."""
    scores = load("scores.json")
    tl = scores[CONTROL]["pages"]
    hit = tot = 0
    per = {}
    for page in FDIC:
        key = "%s_%s" % (page, DPI)
        ok = [f for f, v in scores[tool]["pages"][key]["fields"].items()
              if v["status"] == "OK"]
        both = [f for f in ok if tl[key]["fields"][f]["status"] == "OK"]
        per[page] = 100.0 * len(both) / len(ok) if ok else 0.0
        hit += len(both)
        tot += len(ok)
    return hit, tot, 100.0 * hit / tot, min(per.values()), max(per.values())


# -------------------------------------------------------- the README's prose

def prose_figures():
    scores = load("scores.json")
    rec = _reconcile_totals()
    hosted_broken = rec["gpt"]["BROKEN"] + rec["claude"]["BROKEN"]
    hosted_survived = rec["gpt"]["SURVIVES"] + rec["claude"]["SURVIVES"]
    tess = scores["tesseract"]["by_dpi"][DPI]
    doc = scores["docling"]["by_dpi"][DPI]
    total, loud, quiet, tol = _survives_inventory()
    cmp_, loses, draws = _headline_counts()
    times = _marker_fdic_times()
    slow = max(times, key=lambda d: times[d][0])
    fast = sorted(d for d in times if times[d][0] < 1.0)

    out = [
        # The control breaking no sum belongs to the same sentence and is
        # derived with it, because "hosted models produced no quiet failures"
        # only means something beside a control that also produced none.
        (README, "prose:quiet",
         "Hosted models produced no quiet failures: %d broken sums, %d "
         "survived. The control breaks %s at all."
         % (hosted_broken, hosted_survived,
            "none" if rec[CONTROL]["BROKEN"] == 0 else
            str(rec[CONTROL]["BROKEN"]))),
        (README, "prose:structure",
         "Tesseract finds %d of %d rows, more than any other local tool, and "
         "still recovers only %.1f%%."
         % (tess["rows_anchored"], tess["rows"], 100.0 * tess["recovery"])),
        (README, "prose:misplaced",
         "Docling recovers less and put %d character-perfect values in the "
         "wrong row" % doc["misplaced"]),

        # The quiet-failure inventory, derived rather than described. This is
        # the showcase result of the whole project, which makes it the worst
        # sentence in the README to carry a remembered figure: a reader who
        # checks it is checking the claim the repository is built on.
        (README, "prose:survives",
         "%s rule instances survived a wrong figure. %s of them carry a token "
         "a downstream cast would REJECT, so they are loud where it counts. "
         "The other %s are genuinely quiet, and all %s walked through the "
         "same declared tolerance of 5 on the earnings column sums rather "
         "than past an exact check."
         % (_word(total).capitalize(), _word(loud).capitalize(),
            _word(quiet), _word(tol))),

        # The headline, as a count the test produces rather than a slogan.
        (README, "prose:headline",
         "%s local tool of six loses to doing nothing, and %s more only draw "
         "with it." % (_word(len(loses)).capitalize(), _word(len(draws)))),
        (README, "prose:mcnemar_loses",
         "%s recovers %.1f%% and that gap is real (McNemar exact, paired over "
         "the same %d values, p = %.3f)."
         % (loses[0].capitalize(), 100.0 * cmp_[loses[0]]["recovery"],
            scores[CONTROL]["by_dpi"][DPI]["fields"], cmp_[loses[0]]["p"])),
        (README, "prose:mcnemar_draws", _draws_sentence()),

        # The timing claim, WITH the counterexample that lives in the same
        # manifest. Marker does not stay sub-second on every page that has a
        # text layer, and a sentence that says it does is one page away from
        # being false, so the exception is derived alongside the rule.
        (README, "prose:marker_timing",
         "Marker takes under a second on three of the four FDIC pages and "
         "%.1fs on a census schedule with no text layer. It is not a clean "
         "rule: %s also carries a text layer, and Marker spent %.1f seconds "
         "on it." % (max(_census_times()), slow, times[slow][0])),

        # The born-digital sentence. Four local parsers score four different
        # figures on that page and two of them are equal, which is exactly the
        # shape that invites one tool's number being written beside another's
        # name.
        (README, "prose:borndigital", _borndigital_sentence()),

        # The metric's caption is not the whole metric: a row whose anchor
        # never appears is graded against the whole page. score.py documents
        # that in full; a summary surface that omits it is describing a
        # stricter measurement than the one the table reports.
        (README, "prose:rowfallback", _fallback_sentence()),

        # "All the same mistake" is a claim about four values, and one of the
        # four is a different mistake, so the sentence is counted.
        (README, "prose:gpt_errors", _gpt_errors_sentence()),

        # Counted from the README's own table, asserted in SAMPLE_RUN.
        (SAMPLE_RUN, "samplerun:mutations",
         "%s of those tests are mutation-checked" % _word(_mutation_count())),
    ]
    return out


_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
          "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def _word(n):
    """Small counts read better spelled out, and a spelled-out count cannot be
    mistaken for part of an adjacent figure when the string is searched for."""
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def _subsequence(small, big):
    """Is every character of `small` present in `big`, in order?

    This is what separates an INSERTED character from a dropped or substituted
    one, and the distinction is the whole content of the claim it supports.
    "PO-17733" -> "PO-117733" keeps every original character and adds one;
    "Hex bolt M10x40, zinc" -> " Hex bolt M10x40 zinc" does not, because the
    comma is gone. Length alone cannot tell those apart.
    """
    it = iter(big)
    return all(c in it for c in small)


def _draws_sentence():
    """The two tools the control cannot be distinguished from.

    Written to survive the case where both land on the same percentage, which
    they currently do: printing "74.6% and 74.6%" reads like a typo and invites
    someone to "fix" one of them.
    """
    scores = load("scores.json")
    cmp_, loses, draws = _headline_counts()
    pct = [100.0 * cmp_[t]["recovery"] for t in draws]
    names = " and ".join(t.capitalize() for t in draws)
    where = ("both land on %.1f%%" % pct[0] if len({round(x, 1) for x in pct}) == 1
             else "land on %s" % " and ".join("%.1f%%" % x for x in pct))
    return ("%s %s and neither is distinguishable from doing nothing at all "
            "(p = %s)" % (names, where,
                          " and p = ".join("%.3f" % cmp_[t]["p"]
                                           for t in draws)))

def _census_times():
    man = load("marker/manifest.json")
    return [r["seconds"] for r in man["records"]
            if r["doc_id"].startswith("census")]


def _mutation_count():
    with open(os.path.join(ROOT, README), encoding="utf-8") as fh:
        return fh.read().count("mutation-checked")


def _borndigital_sentence():
    scores = load("scores.json")
    key = "fdic2023_balance_%s" % DPI
    pct = {t: 100.0 * scores[t]["pages"][key]["ok"]
           / scores[t]["pages"][key]["n_fields"] for t in TOOLS}
    local = sorted([t for t in TOOLS if t not in ("gpt", "claude", CONTROL)],
                   key=lambda t: (-pct[t], t))
    parts = ", ".join("%s %.1f%%" % (t.capitalize(), pct[t]) for t in local)
    return ("the control scores %.1f%% there, ties both hosted models, and "
            "beats every local parser: %s." % (pct[CONTROL], parts))


def _fallback_sentence():
    """The row-fallback disclosure, with the count that makes it concrete."""
    scores = load("scores.json")
    worst = max((t for t in TOOLS),
                key=lambda t: scores[t]["by_dpi"][DPI]["rows"]
                - scores[t]["by_dpi"][DPI]["rows_anchored"])
    b = scores[worst]["by_dpi"][DPI]
    return ("A row whose anchor never appears is graded against the whole page "
            "instead, so its cells can be credited without the row being "
            "found: %s anchors only %d of the %d rows."
            % (worst.capitalize(), b["rows_anchored"], b["rows"]))


def _gpt_errors_sentence():
    """Three insertions and one dropped comma are not one mistake."""
    scores = load_out("scores.json")
    misses = []
    for page, pv in sorted(scores["gpt"]["pages"].items()):
        if not page.endswith("_150"):
            continue
        for field, v in sorted(pv["fields"].items()):
            if v["status"] != "OK":
                misses.append((v["printed"], v.get("got", "")))
    inserted = [m for m in misses
                if len(m[1]) == len(m[0]) + 1 and _subsequence(m[0], m[1])]
    return ("GPT's only %s errors are all at 150, and %s of the %s are the "
            "same mistake: an inserted character"
            % (_word(len(misses)), _word(len(inserted)), _word(len(misses))))


# -------------------------------------------------------------- FINDINGS.txt

def findings_tables():
    """Five tables, every cell rebuilt from the artifacts.

    Section 4's table was wrong in every row and section 5's in three, for the
    same reason: they were typed once, the grader was corrected twice
    afterwards, and nothing compared them to the JSON again.
    """
    scores = load("scores.json")
    out = []

    # Section 1: the same measurements as the README table, in FINDINGS' own
    # fixed-width layout. Derived independently rather than shared, because the
    # point is that the two documents agree, and a shared string cannot show it.
    for page in PAGES:
        key = "%s_%s" % (page, DPI)
        cells = " ".join("%.1f" % (100.0 * scores[t]["pages"][key]["ok"]
                                   / scores[t]["pages"][key]["n_fields"])
                         for t in TOOLS)
        out.append((FINDINGS, "findings:table1:" + page,
                    "%s %d %s" % (page, scores[TOOLS[0]]["pages"][key]
                                  ["n_fields"], cells)))
    out.append((FINDINGS, "findings:table1:corpus",
                "CORPUS %d %s" % (scores[TOOLS[0]]["by_dpi"][DPI]["fields"],
                                  " ".join("%.1f" % (100.0 * scores[t]
                                                     ["by_dpi"][DPI]
                                                     ["recovery"])
                                           for t in TOOLS))))
    out.append((FINDINGS, "findings:table1:seconds",
                "seconds per page %s"
                % " ".join("%.1f" % scores[t]["by_dpi"][DPI]
                           ["seconds_per_page"] for t in TOOLS)))

    # Section 4: the 105 within-page rules. CROSS-PAGE IS EXCLUDED, which is
    # the distinction the stale table lost.
    within = _reconcile_totals(include_cross_page=False)
    for tool in TOOLS:
        t = within[tool]
        out.append((FINDINGS, "findings:sec4:" + tool,
                    "%s %d %d %d %d" % (tool, t["HOLDS"], t["SURVIVES"],
                                        t["BROKEN"], t["INCOMPLETE"])))

    # Section 5: structure. "values missing" is the ABSENT column; the stale
    # table had it as absent+corrupt for three tools and as absent for four.
    for tool in ["gpt", "claude", "docling", CONTROL, "marker", "unstructured",
                 "tesseract"]:
        b = scores[tool]["by_dpi"][DPI]
        out.append((FINDINGS, "findings:sec5:" + tool,
                    "%s %d/%d %d %d" % (tool, b["rows_anchored"], b["rows"],
                                        b["misplaced"], b["absent"])))

    # Section 6: handwriting, in its own column order.
    hand = ["gpt", "claude", "marker", "docling", "unstructured", "tesseract",
            CONTROL]
    for page in ["census29_wages", "census29_sales"]:
        key = "%s_%s" % (page, DPI)
        out.append((FINDINGS, "findings:sec6:" + page,
                    "%s %s" % (page,
                               " ".join("%.1f" % (100.0 * scores[t]["pages"]
                                                  [key]["ok"]
                                                  / scores[t]["pages"][key]
                                                  ["n_fields"])
                                        for t in hand))))
    return out


def findings_prose():
    scores = load("scores.json")
    within = _reconcile_totals(include_cross_page=False)
    rec = _reconcile_totals()
    total, loud, quiet, tol = _survives_inventory()
    cmp_, loses, draws = _headline_counts()
    times = _marker_fdic_times()
    slow = max(times, key=lambda d: times[d][0])
    fast = sorted((d for d in times if times[d][0] < 1.0),
                  key=lambda d: times[d][0])
    return [
        (FINDINGS, "findings:headline",
         "%s OF THE SIX PARSERS LOSES TO DOING NOTHING, AND %s MORE ONLY DRAW "
         "WITH IT" % (_word(len(loses)).upper(), _word(len(draws)).upper())),
        (FINDINGS, "findings:sec2:borndigital", _borndigital_sentence()),
        (FINDINGS, "findings:sec2:subset",
         "Marker's and Docling's figures are a %.0f-100%% subset of the "
         "embedded layer" % min(_subset_of_layer("marker")[3],
                                _subset_of_layer("docling")[3])),
        (FINDINGS, "findings:sec3:marker_timing",
         "Marker took %s seconds on three of the four FDIC pages, %.1f "
         "seconds on the fourth, and %.1f and %.1f seconds on the two census "
         "schedules."
         % (", ".join("%.1f" % times[d][0] for d in fast), times[slow][0],
            max(_census_times()), min(_census_times()))),
        (FINDINGS, "findings:sec4:survives",
         "%s rule instances survived" % _word(total).capitalize()),
        (FINDINGS, "findings:sec4:hosted",
         "Between them %s sums broke and 0 survived"
         % _word(rec["gpt"]["BROKEN"] + rec["claude"]["BROKEN"])),
        (FINDINGS, "findings:sec4:tolerance",
         "%s survived because of a tolerance" % _word(tol).upper()),
        (FINDINGS, "findings:sec5:misplaced",
         "it put %d exactly-correct values in the wrong row"
         % scores["docling"]["by_dpi"][DPI]["misplaced"]),
        (FINDINGS, "findings:sec4:within",
         "%d within-page rules" % sum(within[TOOLS[0]].values())),
        (FINDINGS, "findings:rowfallback", _fallback_sentence()),
    ]


def _cost_totals(model):
    """Tokens and dollars for one hosted run.

    The price table is imported from cloud_cost.py, not copied. A second
    copy of a dated price list is a second thing to forget to re-verify, and the
    dates are the only reason those figures are auditable at all.
    """
    import cloud_cost

    rows = load("%s/usage.json" % model)
    tot_in = sum(r["input_tokens"] for r in rows)
    tot_out = sum(r["output_tokens"] for r in rows)
    cost = 0.0
    for r in rows:
        p = cloud_cost.price_for(r["model"])
        if p:
            cost += (r["input_tokens"] * p[0] + r["output_tokens"] * p[1]) / 1e6
    return tot_in, tot_out, cost, len(rows)


def findings_cost():
    """Section 7's cost block, from the same usage records cloud_cost.py reads."""
    out = []
    total = 0.0
    for model in ["claude", "gpt"]:
        tot_in, tot_out, cost, n = _cost_totals(model)
        total += cost
        out.append((FINDINGS, "findings:sec7:" + model,
                    "%s %s in %s out $%.4f $%.4f/page"
                    % (model, "{:,}".format(tot_in), "{:,}".format(tot_out),
                       cost, cost / n)))
        out.append((SAMPLE_RUN, "samplerun:cost:" + model,
                    "%d page(s) %d %d $%.4f per page: %d in %d out $%.4f"
                    % (n, tot_in, tot_out, cost, tot_in // n, tot_out // n,
                       cost / n)))
    # "$1.12 for the whole corpus" is a rounded total and appears on three
    # surfaces. Rounding it here is what keeps the three agreeing.
    for surface in (README, FINDINGS, SAMPLE_RUN):
        out.append((surface, "cost:corpus_total",
                    "$%.2f" % total))
    return out


# ------------------------------------------------------------- SAMPLE_RUN.md

def samplerun_blocks():
    """SAMPLE_RUN.md says its blocks are what the commands printed, verbatim.

    That is a reproducibility claim, so it gets checked like one. Every number
    in the score table, the reconcile blocks and the coherence table is rebuilt
    here; the block that quotes wall-clock seconds is not, and the docstring
    says why.
    """
    scores = load("scores.json")
    data = load("reconcile.json")
    out = []

    for tool in sorted(scores):
        b = scores[tool]["by_dpi"][DPI]
        q = "%.0f%%" % (b["quiet_fraction_of_misses"] * 100)
        out.append((SAMPLE_RUN, "samplerun:score:" + tool,
                    "%s %s %d %.1f%% %d %d %d %d %s %d/%d %.1f"
                    % (tool, DPI, b["fields"], 100.0 * b["ok"] / b["fields"],
                       b["absent"], b["corrupt"], b["corrupt_typed"],
                       b["misplaced"], q, b["rows_anchored"], b["rows"],
                       b["seconds_per_page"])))

    # The per-page rows the document actually prints: the first two, then the
    # last five after an explicit elision marker.
    rows = [(tool, page) for tool in sorted(data)
            for page in sorted(p for p in data[tool] if p != "cross_page")]
    shown = rows[:2] + rows[-5:]
    for tool, page in shown:
        c = data[tool][page]["counts"]
        out.append((SAMPLE_RUN, "samplerun:reconcile:%s:%s" % (tool, page),
                    "%s %s %d %d %d %d" % (tool, page, c["HOLDS"],
                                           c["SURVIVES"], c["BROKEN"],
                                           c["INCOMPLETE"])))
    # The elision marker is a derived count too: the rows the command printed
    # less the rows shown.
    out.append((SAMPLE_RUN, "samplerun:reconcile:elided",
                "(%d more per-page rows)" % (len(rows) - len(shown))))

    for tool in sorted(data):
        c = data[tool]["cross_page"]["counts"]
        out.append((SAMPLE_RUN, "samplerun:coherence:" + tool,
                    "%s %d %d %d %d" % (tool, c["HOLDS"], c["SURVIVES"],
                                        c["BROKEN"], c["INCOMPLETE"])))

    cmp_, loses, draws = _headline_counts()
    out.append((SAMPLE_RUN, "samplerun:headline",
                "%s of six parsers loses to doing nothing, and %s more only "
                "draw with it." % (_word(len(loses)).capitalize(),
                                   _word(len(draws)))))
    out.append((SAMPLE_RUN, "samplerun:rowfallback", _fallback_sentence()))
    return out


# ------------------------------------------------------- GitHub description

def gh_description():
    cmp_, loses, draws = _headline_counts()
    return [(GH_DESC, "ghdesc:headline",
             "%s of six parsers loses to the control and %s more only draw "
             "with it." % (_word(len(loses)).capitalize(),
                           _word(len(draws))))]


def security_notes():
    """SECURITY.md opens by saying what the repository contains.

    It is a short file and the temptation is to leave it alone, but its first
    sentence states the corpus size, the same 425 the headline table is
    measured over, and a security reader is exactly the reader who will
    check whether the repository contains what it says it contains.
    """
    scores = load("scores.json")
    b = scores[TOOLS[0]]["by_dpi"][DPI]
    return [(SECURITY, "security:corpus",
             "%s pages cut from four public-domain documents, %d hand-labeled "
             "values, the raw output of %s parsers over those pages"
             % (_word(b["pages"]).capitalize(), b["fields"],
                _word(len(TOOLS))))]


def emit():
    return (rows_per_page() + rows_corpus() + prose_figures()
            + findings_tables() + findings_prose() + findings_cost()
            + samplerun_blocks() + gh_description() + security_notes())


def squash(text):
    """Normalize the things that are formatting rather than claims.

    Emphasis, backticks, markdown escapes, run-length whitespace AND CASE. Case
    goes because these documents put whole sentences in capitals for emphasis
    and moving a claim into or out of a heading is an editorial choice, not a
    change to what it asserts. Every figure derived here is a number, a
    percentage or a spelled-out count, so case-folding cannot make two
    different claims compare equal.
    """
    text = text.replace("**", "").replace("`", "").replace("*", "")
    text = text.replace("\\_", "_")
    return re.sub(r"\s+", " ", text).lower()


def main():
    derived = emit()
    if "--emit" in sys.argv:
        for surface, tag, row in derived:
            print("%s  [%s]\n%s" % (tag, surface, row))
        return 0

    bodies = {}
    for surface in {s for s, _, _ in derived}:
        with open(os.path.join(ROOT, surface), encoding="utf-8") as fh:
            bodies[surface] = squash(fh.read())

    missing = [(s, t, r) for s, t, r in derived
               if squash(r) not in bodies[s]]
    for surface, tag, row in missing:
        print("MISSING [%s in %s]\n  %s" % (tag, surface, row))

    print("\n%d of %d derived figures found verbatim, across %d documents"
          % (len(derived) - len(missing), len(derived), len(bodies)))
    for surface in sorted(bodies):
        n = sum(1 for s, _, _ in derived if s == surface)
        bad = sum(1 for s, _, _ in missing if s == surface)
        print("  %-24s %d of %d" % (surface, n - bad, n))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
