"""Re-derive every published number in the summary documents from out_real/*.json.

Prose drifts; out_real/*.json is evidence and does not. This script rebuilds
each figure from the JSON and asserts the exact string is present in the
document that quotes it, so a re-run that shifts a figure fails loudly instead
of leaving the document silently wrong.

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
are not a claim about anything. The one exception is captured command output in
SAMPLE_RUN.md, which claims to be what a command printed: the rows of its score,
reconcile, coherence and cost tables are compared as whole lines, unnormalized.

The per-page table is the one that matters most, and it is derived cell by cell.
The corpus row hides both findings this repository exists to report: the control
ties the hosted models on the born-digital page and scores zero on the two
handwritten ones, and a table checked only at its total row would let either of
those move without a sound.

What is NOT derived, said here rather than left to be discovered:

  - The test count. Counting `def test_` undercounts, because the suite
    parametrizes; the real figure needs pytest, and this file is stdlib-only so
    that a reader can re-check the arithmetic with an interpreter and nothing
    else. tests/test_corpus.py owns that claim instead.
    README.md states it as 130.
  - Wall-clock seconds in SAMPLE_RUN's captured blocks, which cannot reproduce
    between two runs and say nothing about whether the text came back right.
  - Numbers that name something rather than measure it: the years 1929, 1956
    and 2023, page 134 and Table 114 of the source documents, the 150 DPI
    render, and the 5.0 tolerance a mutation description quotes.

The McNemar p-values are derived from the per-field verdicts in scores.json,
because they are the most tempting figure here to type by hand. They decide the repository's headline: "loses to the control"
and "is not distinguishable from the control" are different claims about the
same three tools, and only the paired test separates them. A figure that
decides a headline is the last one that should be a constant in a document.

The count is printed whether OR NOT anything is missing, so a version of this
script that silently stopped deriving half of them is visible rather than clean.
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

#: Tag prefix for a row that must appear as a whole line, unnormalized. Used
#: for captured command output, where the column layout is part of what
#: "this is what the command printed" asserts.
EXACT = "samplerun:exact:"


def recovered(b):
    """Percent recovered, from the counts, for a by_dpi summary.

    One formula for every percentage. scores.json also stores `recovery`, but
    that is round(ok / fields, 4), and a percentage printed from an already
    rounded ratio can land on the other side of a half: 313 of 425 is 73.647%,
    which prints as 73.6, while 100 * 0.7365 prints as 73.7. score.py prints
    ok / fields, so every figure here is computed the same way.
    """
    return 100.0 * b["ok"] / b["fields"]


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
    rec = ["%.1f%%" % recovered(scores[t]["by_dpi"][DPI]) for t in TOOLS]
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

    This is the split that decides whether a surviving misread is silent or
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

    Returns (total, loud, silent, tolerance_backed). A SURVIVES is a rule that
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
    which is what the test is for: 425 values where both tools agree say
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
        rec = recovered(scores[tool]["by_dpi"][DPI])
        out[tool] = {"control_only": c_only, "tool_only": t_only, "p": p,
                     "recovered_pct": rec,
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
         "Hosted models produced %s: %d broken sums, %d "
         "survived. The control breaks %s at all."
         % ("no quiet failures" if hosted_survived == 0 else
            "%s quiet %s" % (_word(hosted_survived),
                             _verb(hosted_survived, "failure", "failures")),
            hosted_broken, hosted_survived,
            "none" if rec[CONTROL]["BROKEN"] == 0 else
            str(rec[CONTROL]["BROKEN"]))),
        (README, "prose:structure",
         "Tesseract finds %d of %d rows, more than any other local tool, and "
         "still recovers only %.1f%%."
         % (tess["rows_anchored"], tess["rows"], recovered(tess))),
        (README, "prose:misplaced",
         "Docling recovers less and put %d character-perfect values in the "
         "wrong row" % doc["misplaced"]),

        # The silent-failure inventory, derived rather than described. This is
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
        (README, "prose:headline", _headline_sentence("doing nothing", ", and ")),
        (README, "prose:mcnemar_loses", _loses_sentence()),
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


def _verb(n, singular, plural):
    """Agreement for a derived count. A template that hard-wires "loses" and
    "draw" comes out ungrammatical when a re-score changes how many parsers
    lose and how many draw."""
    return singular if n == 1 else plural


def _headline_sentence(control_phrase, joiner):
    cmp_, loses, draws = _headline_counts()
    return ("%s of six parsers %s to %s%s%s more only %s with it."
            % (_word(len(loses)).capitalize(),
               _verb(len(loses), "loses", "lose"), control_phrase, joiner,
               _word(len(draws)), _verb(len(draws), "draws", "draw")))


def _loses_sentence():
    """Every parser that loses to the control, with its figure and p-value."""
    scores = load("scores.json")
    cmp_, loses, draws = _headline_counts()
    parts = ["%s recovers %.1f%%" % (t.capitalize(), cmp_[t]["recovered_pct"])
             for t in loses]
    ps = " and ".join("p = %.3f" % cmp_[t]["p"] for t in loses)
    gap = ("that gap is real" if len(loses) == 1
           else "both gaps are real" if len(loses) == 2 else "every gap is real")
    return ("%s, and %s (McNemar exact, paired over the same %d values, %s)."
            % (" and ".join(parts) if len(parts) < 3 else ", ".join(parts),
               gap, scores[CONTROL]["by_dpi"][DPI]["fields"], ps))


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
    pct = [cmp_[t]["recovered_pct"] for t in draws]
    names = " and ".join(t.capitalize() for t in draws)
    if len(draws) == 1:
        return ("%s lands on %.1f%% and is not distinguishable from doing "
                "nothing at all (p = %.3f)" % (names, pct[0], cmp_[draws[0]]["p"]))
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
                                  " ".join("%.1f" % recovered(
                                      scores[t]["by_dpi"][DPI])
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
         "%s OF THE SIX PARSERS %s TO DOING NOTHING, AND %s MORE ONLY %s "
         "WITH IT" % (_word(len(loses)).upper(),
                      _verb(len(loses), "LOSES", "LOSE"),
                      _word(len(draws)).upper(),
                      _verb(len(draws), "DRAWS", "DRAW"))),
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
        # Both counts are derived. A literal here would check a figure the
        # row wrote itself, and stay "derived" when a re-score moved it.
        (FINDINGS, "findings:sec4:hosted",
         "Between them %s sums broke and %s survived"
         % (_word(rec["gpt"]["BROKEN"] + rec["claude"]["BROKEN"]),
            _word(rec["gpt"]["SURVIVES"] + rec["claude"]["SURVIVES"]))),
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

    The price table is imported from cloud_cost.py. A second copy of a dated
    price list is a second thing to forget to re-verify, and the dates are the
    only reason those figures are auditable at all.
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

    That is a reproducibility claim, so it gets checked like one. The rows of
    the score table, the reconcile table and the coherence table are rebuilt
    here BY THE FUNCTIONS THE COMMANDS PRINT THEM WITH, and tagged EXACT: each
    must appear as a whole line of SAMPLE_RUN.md, character for character,
    so a row retyped with its columns collapsed fails even when every figure
    in it is right. The block that quotes wall-clock seconds is not derived,
    and the docstring says why.
    """
    import reconcile
    import score

    scores = load("scores.json")
    data = load("reconcile.json")
    out = []

    for tool in scores:
        b = scores[tool]["by_dpi"][DPI]
        out.append((SAMPLE_RUN, EXACT + "score:" + tool,
                    score.format_row(tool, DPI, b)))

    # The per-page rows the document actually prints: the first two, then the
    # last five after an explicit elision marker.
    rows = [(tool, page) for tool in sorted(data)
            for page in sorted(p for p in data[tool] if p != "cross_page")]
    shown = rows[:2] + rows[-5:]
    for tool, page in shown:
        c = data[tool][page]["counts"]
        out.append((SAMPLE_RUN, EXACT + "reconcile:%s:%s" % (tool, page),
                    reconcile.format_counts(tool, c, page)))
    # The elision marker is a derived count too: the rows the command printed
    # less the rows shown.
    out.append((SAMPLE_RUN, "samplerun:reconcile:elided",
                "(%d more per-page rows)" % (len(rows) - len(shown))))

    for tool in sorted(data):
        c = data[tool]["cross_page"]["counts"]
        out.append((SAMPLE_RUN, EXACT + "coherence:" + tool,
                    reconcile.format_counts(tool, c)))

    out.append((SAMPLE_RUN, "samplerun:headline",
                _headline_sentence("doing nothing", ", and ")))
    out.append((SAMPLE_RUN, "samplerun:rowfallback", _fallback_sentence()))

    # The control's re-run block: page, seconds as the manifest records them,
    # and the character count of the text layer it returned.
    for r in load("textlayer/manifest.json")["records"]:
        out.append((SAMPLE_RUN, "samplerun:textlayer:%s" % r["doc_id"],
                    "%s_%d %.1fs %d chars"
                    % (r["doc_id"], r["dpi"], r["seconds"], r["chars"])))
    out += samplerun_cost_block()
    return out


def samplerun_cost_block():
    """The `cloud_cost.py --all` block, by running what it runs.

    Every line of each out_real/ section and the ALL RUNS total must appear;
    the synthetic out/ sections are elided on the page, as it says.
    """
    import contextlib
    import io
    from pathlib import Path

    import cloud_cost

    dirs = sorted(p.parent for p in Path(ROOT).glob("out*/*/usage.json"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        totals = [r for d in dirs if (r := cloud_cost.report(d))]
    grand = sum(t["cost_usd"] for t in totals)
    out = []
    section = None
    for line in buf.getvalue().splitlines():
        if line.startswith(str(ROOT)):
            section = line[len(str(ROOT)):]
            continue
        if section and section.startswith("/out_real/") and line.strip():
            out.append((SAMPLE_RUN, EXACT + "cost_line:%s:%s"
                        % (section, line.split()[0]), line))
    out.append((SAMPLE_RUN, "samplerun:cost_all", "ALL RUNS: $%.4f" % grand))
    return out


# ------------------------------------------------------- GitHub description

def gh_description():
    return [(GH_DESC, "ghdesc:headline",
             _headline_sentence("the control", " and "))]


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


def _census(tool):
    """Labeled values on the two 1929 census pages: (ok, total, hw_ok, hw)."""
    pages = {k: p for k, p in load("scores.json")[tool]["pages"].items()
             if k.startswith("census29")}
    fields = [(name, f) for p in pages.values() for name, f in p["fields"].items()]
    hw = [f for name, f in fields if name.startswith("hw_")]
    return (sum(p["ok"] for p in pages.values()),
            sum(p["n_fields"] for p in pages.values()),
            sum(1 for f in hw if f["status"] == "OK"), len(hw))


def _wages(tool):
    page = load("scores.json")[tool]["pages"]["census29_wages_%s" % DPI]
    return page["ok"], page["n_fields"]


def review_figures():
    """Figures in the README prose that no table row carries."""
    scores = load("scores.json")
    full = [t for t in TOOLS if scores[t]["by_dpi"][DPI]["rows_anchored"]
            == scores[t]["by_dpi"][DPI]["rows"]]
    b = scores[full[0]]["by_dpi"][DPI] if full else None
    anchored = ("%s tool that anchors every row, %s (%d of %d at %s DPI), is "
                "judged under the strict rule throughout"
                % (_word(len(full)).capitalize(),
                   ", ".join(t.upper() if t == "gpt" else t.capitalize()
                             for t in full),
                   b["rows_anchored"], b["rows"], DPI))
    t_ok, t_n = _wages("tesseract")
    g_ok, g_n = _wages("gpt")
    tc, n, thw, hw = _census("tesseract")
    gc, _, _, _ = _census("gpt")
    printed = n - hw
    pair = ("buys the difference between %d%% and %d%% on the %d labeled "
            "values of the wages sheet. Over all %d labeled values on the "
            "1929 pages, of which %d are handwritten and %d are printed form "
            "text, the pair is %.1f%% and %.1f%%; handwriting alone, "
            "Tesseract recovers %d of %d"
            % (round(100 * t_ok / t_n), round(100 * g_ok / g_n), t_n, n, hw,
               printed, 100 * tc / n, 100 * gc / n, thw, hw))
    c_cost = _cost_totals("claude")
    g_cost = _cost_totals("gpt")
    per_page = ("Claude $%.4f/page, GPT $%.4f/page"
                % (c_cost[2] / c_cost[3], g_cost[2] / g_cost[3]))
    local = ["docling", "marker", "tesseract", "unstructured"]
    hw_reads = {t: _census(t)[2] for t in TOOLS}
    cmp_, loses, draws = _headline_counts()
    below = loses + draws
    secs = [scores[t]["by_dpi"][DPI]["seconds_per_page"] for t in below]
    hand = ("the hosted models read the most handwriting, %d and %d of %d "
            "handwritten values, against %d for Docling and %d for Marker"
            % (hw_reads["claude"], hw_reads["gpt"], hw,
               hw_reads["docling"], hw_reads["marker"]))
    return [
        (README, "review:anchored", anchored),
        (README, "review:handwritten_pair", pair),
        (README, "review:per_page_cost", per_page),
        (FINDINGS, "review:findings_anchored",
         "%s tool that anchors every row is judged strictly throughout"
         % _word(len(full))),
        (FINDINGS, "review:findings_handwriting", hand),
        (FINDINGS, "review:findings_seconds",
         "at %d to %d seconds a page against zero"
         % (int(min(secs)), int(max(secs)))),
    ] + generated_corpus()


def generated_corpus():
    """The resolution table and the sentences around it, from out/scores.json."""
    g = load_out("scores.json")
    out = []
    order = ["claude", "gpt", "docling", "marker", "unstructured", "tesseract"]
    for t in order:
        v = g[t]
        lo, hi = v["by_dpi"]["150"], v["by_dpi"]["300"]
        label = v["version"].split()[0] if t in ("claude", "gpt") else t
        part = lambda b: "[1]" if b["pages"] < 10 else ""
        q = lo["quiet_fraction_of_misses"]
        out.append((README, "gen:" + t,
                    "| %s | %.1f%%%s | %.1f%%%s | %s |"
                    % (label, recovered(lo), part(lo),
                       recovered(hi), part(hi),
                       "-- (no misses)" if q is None
                       else "%d%%" % round(100 * q))))
    mk = g["marker"]["by_dpi"]
    bad = sum(mk[d][k] for d in mk for k in ("corrupt", "absent", "misplaced"))
    tess = g["tesseract"]["by_dpi"]["150"]
    cl = g["claude"]["by_dpi"]
    gpt = g["gpt"]["by_dpi"]
    out += [
        (README, "gen:fields",
         "rendered at 150 and 300 DPI, %d graded values per run"
         % g["claude"]["by_dpi"]["300"]["fields"]),
        (README, "gen:marker_partial",
         "through %d of 10 documents at 150 DPI and %d of 10 at 300. %s "
         "content error in %d values"
         % (mk["150"]["pages"], mk["300"]["pages"], _word(bad).capitalize(),
            mk["150"]["fields"] + mk["300"]["fields"])),
        (README, "gen:tess_quiet",
         "%d of %d misses still parse as the value they replaced"
         % (tess["corrupt_typed"], tess["fields"] - tess["ok"])),
        (README, "gen:claude_both",
         "Claude scores %d of %d at both"
         % (cl["150"]["ok"], cl["150"]["fields"])
         if cl["150"]["ok"] == cl["300"]["ok"] else "Claude differs by DPI"),
        (README, "gen:gpt_errors",
         "GPT's only %s errors are all at 150"
         % _word(gpt["150"]["fields"] - gpt["150"]["ok"])
         if gpt["300"]["ok"] == gpt["300"]["fields"] else "GPT errs at 300"),
    ]
    return out


# ------------------------------------------------- figures stated a second time

def _name(tool):
    return "GPT" if tool == "gpt" else tool.capitalize()


def _short(pct):
    """A percentage as the prose writes a round one: 100, not 100.0."""
    return ("%.1f" % pct).rstrip("0").rstrip(".")


def _page_pct(scores, tool, page):
    p = scores[tool]["pages"]["%s_%s" % (page, DPI)]
    return 100.0 * p["ok"] / p["n_fields"]


def _own_label_misplaced(tool, page="fdic_earnings"):
    """Of a tool's MISPLACED values on one page, how many sit on a line that
    also carries their own row's label: (on_own_line, misplaced).

    scores.json records that a value was found in another row, not on which
    line, so this is measured from the parser's shipped output. A value counts
    when one line of that output carries both its row's anchor and the value as
    a whole token; that is the signature of two printed rows run together.
    """
    import score

    scores = load("scores.json")
    truth = json.load(open(os.path.join(ROOT, "real", "pages",
                                        "%s.truth.json" % page),
                           encoding="utf-8"))
    key = "%s_%s" % (page, DPI)
    man = load("%s/manifest.json" % tool)
    rec = [r for r in man["records"]
           if r["doc_id"] == page and r["dpi"] == int(DPI)][0]
    with open(os.path.join(ROOT, "out_real", tool, rec["text_file"]),
              encoding="utf-8") as fh:
        lines = score.lines_of(fh.read())
    own = total = 0
    for field, v in scores[tool]["pages"][key]["fields"].items():
        if v["status"] != "MISPLACED":
            continue
        total += 1
        anchor = truth["rows"][int(field.split("[")[1].split("]")[0])]["anchor"]
        want = score.canon(v["printed"])
        if any(score.substr_match(anchor, [ln])
               and any(score.canon(t) == want for t in score.tokens_of(ln))
               for ln in lines):
            own += 1
    return own, total


def _castable_survivors():
    """Misreads that survived a sum AND cast cleanly as numbers, per tool:
    {tool: {(read, printed)}}."""
    data = load("reconcile.json")
    out = {}
    for tool in data:
        for page in data[tool].values():
            for rule in page.get("detail", []):
                if rule["status"] != "SURVIVES":
                    continue
                pairs = [m.groups() for n in rule.get("notes", [])
                         for m in [_READ_AS.search(n)] if m]
                if pairs and all(_casts_as_number(r) for r, _ in pairs):
                    out.setdefault(tool, set()).update(pairs)
    return out


def _coherence_sentence():
    data = load("reconcile.json")
    order = ["claude", "marker", "docling", "unstructured", CONTROL, "gpt",
             "tesseract"]
    counts = {t: data[t]["cross_page"]["counts"] for t in order}
    n = sum(counts[order[0]].values())
    hold = [t for t in order if counts[t]["HOLDS"] == n]
    names = ["the control" if t == CONTROL else _name(t) for t in hold]
    parts = ["%s and %s hold all %d." % (", ".join(names[:-1]), names[-1], n)]
    for t in order:
        if t in hold:
            continue
        c = counts[t]
        s = "%s breaks %d" % (_name(t), c["BROKEN"])
        if c["SURVIVES"]:
            s += ", lets %d survive" % c["SURVIVES"]
        if c["INCOMPLETE"]:
            s += " and cannot run %s" % ("another" if c["INCOMPLETE"] == 1
                                         else "%d more" % c["INCOMPLETE"])
        parts.append(s + ".")
    return " ".join(parts)


def restated_figures():
    """Figures a summary states a second time, in prose, away from the table
    that carries them. Each is derived where it is written, because a copy
    that nothing compares is the copy that goes stale after a re-score."""
    scores = load("scores.json")
    cmp_, loses, draws = _headline_counts()
    n = scores[CONTROL]["by_dpi"][DPI]["fields"]
    times = _marker_fdic_times()
    slow = max(times, key=lambda d: times[d][0])
    fast = sorted((d for d in times if times[d][0] < 1.0),
                  key=lambda d: times[d][0])
    fast_s = ["%.1f" % times[d][0] for d in fast]
    earn = {t: _page_pct(scores, t, "fdic_earnings") for t in TOOLS}
    bal = {t: _page_pct(scores, t, "fdic_balance") for t in TOOLS}
    wages = {t: _page_pct(scores, t, "census29_wages") for t in TOOLS}
    tess = scores["tesseract"]["by_dpi"][DPI]
    local = ["docling", "marker", "tesseract", "unstructured"]
    most = max(local, key=lambda t: scores[t]["by_dpi"][DPI]["rows_anchored"])
    u_own, u_mis = _own_label_misplaced("unstructured")
    t_own, t_mis = _own_label_misplaced("tesseract")
    d_own, d_mis = _own_label_misplaced("docling")
    quiet = _castable_survivors()
    q_tools = sorted(quiet)
    q_same = all(quiet[t] == quiet[q_tools[0]] for t in q_tools)
    q_pairs = sorted(quiet[q_tools[0]],
                     key=lambda rp: float(rp[1].replace(",", "")))
    total, loud, n_quiet, tol = _survives_inventory()
    hosted = sorted(["gpt", "claude"], key=lambda t: earn[t])
    hand = (sorted(["gpt", "claude"], key=lambda t: -wages[t])
            + sorted(local, key=lambda t: -wages[t]))
    bd = {t: _page_pct(scores, t, "fdic2023_balance") for t in TOOLS}
    # "1000x" is an order of magnitude, the slowest census page over the
    # fastest FDIC page, and is derived as one.
    fold_ = 10 ** int(math.log10(max(_census_times()) / times[fast[0]][0]))
    within = _reconcile_totals(include_cross_page=False)
    all_rules = sum(within[TOOLS[0]].values())
    earn_rules = sum(load("reconcile.json")[TOOLS[0]]["fdic_earnings"]
                     ["counts"].values())
    top = max(TOOLS, key=lambda t: earn[t])
    low = min(TOOLS, key=lambda t: earn[t])
    return [
        (README, "restated:control_corpus",
         "It recovers %.1f%% of the corpus."
         % recovered(scores[CONTROL]["by_dpi"][DPI])),
        (README, "restated:marker_balance",
         "the page where Marker scores %.1f%% against the layer's %.1f%%"
         % (bal["marker"], bal[CONTROL])),
        (README, "restated:wages_sheet",
         "on the wages sheet, %s against %s, and the control %.1f%%"
         % (" and ".join("%s %.1f%%" % (_name(t), wages[t]) for t in hand[:2]),
            ", ".join("%s %.1f%%" % (_name(t), wages[t]) for t in hand[2:]),
            wages[CONTROL])),
        (README, "restated:earnings_spread",
         "it is where the spread is widest: %s %.1f%% down to %s %.1f%%."
         % (_name(top), earn[top], _name(low), earn[low])),
        (FINDINGS, "restated:marker_fast",
         "Marker finished %s pages in %s and %s seconds without ever starting "
         "its vision model"
         % (_word(len(fast)), ", ".join(fast_s[:-1]), fast_s[-1])),
        (FINDINGS, "restated:earnings_control",
         "On the 1956 earnings table it scores %.1f%% while Docling scores "
         "%.1f%%, Tesseract %.1f%% and Unstructured %.1f%%."
         % (earn[CONTROL], earn["docling"], earn["tesseract"],
            earn["unstructured"])),
        (FINDINGS, "restated:balance_tie",
         "On fdic_balance the control and Docling tie exactly, %.1f%% each."
         % bal[CONTROL] if round(bal[CONTROL], 1) == round(bal["docling"], 1)
         else "On fdic_balance the control scores %.1f%% and Docling %.1f%%."
         % (bal[CONTROL], bal["docling"])),
        (FINDINGS, "restated:mcnemar",
         "McNemar exact over the same %d values: %s, against %s."
         % (n, " and ".join("%s p = %.3f" % (_name(t), cmp_[t]["p"])
                            for t in loses),
            " and ".join("%s p = %.3f" % (_name(t), cmp_[t]["p"])
                         for t in draws))),
        (FINDINGS, "restated:marker_balance",
         "Marker still spent %.1f seconds on it and scored %.1f%% against "
         "that layer's %.1f%%"
         % (times[slow][0], _page_pct(scores, "marker", slow),
            _page_pct(scores, CONTROL, slow))),
        (FINDINGS, "restated:quiet_pairs",
         "%s each read %s -- %s rule instances between them"
         % (" and ".join(_name(t) for t in q_tools) if q_same else "(differ)",
            " and ".join("%s for %s" % rp for rp in q_pairs), _word(n_quiet))),
        (FINDINGS, "restated:coherence", _coherence_sentence()),
        (FINDINGS, "restated:tess_rows",
         "Tesseract finds %d of %d rows -- %s -- and still recovers only %.1f%%"
         % (tess["rows_anchored"], tess["rows"],
            "more than any other local tool" if most == "tesseract"
            else "fewer than %s" % _name(most), recovered(tess))),
        (FINDINGS, "restated:merged_rows",
         "On fdic_earnings that accounts for %d of Unstructured's %d and %d of "
         "Tesseract's %d" % (u_own, u_mis, t_own, t_mis)),
        (FINDINGS, "restated:docling_not_merged",
         "DOCLING'S %d ARE NOT THAT: %s of the %d sits on a line carrying its "
         "own row label"
         % (d_mis, "none" if d_own == 0 else str(d_own), d_mis)),
        (FINDINGS, "restated:earnings_spread",
         "Docling drops to %.1f%% while Tesseract holds %.1f%% and "
         "Unstructured %.1f%%, and the hosted models hold %.1f%% and %.1f%% "
         "against the text layer's %.1f%%. Docling's loss here is structural "
         "rather than optical: %d of the values it missed came back "
         "character-perfect in the wrong row."
         % (earn["docling"], earn["tesseract"], earn["unstructured"],
            earn[hosted[0]], earn[hosted[1]], earn[CONTROL],
            scores["docling"]["pages"]["fdic_earnings_%s" % DPI]
            ["misplaced"])),
        (README, "restated:control_borndigital",
         "the control scores %s%% and %s the hosted models"
         % (_short(bd[CONTROL]), "ties" if bd[CONTROL] == bd["gpt"]
            == bd["claude"] else "differs from")),
        (FINDINGS, "restated:control_borndigital",
         "On the born-digital page it scores %s%% and %s the hosted models"
         % (_short(bd[CONTROL]), "ties" if bd[CONTROL] == bd["gpt"]
            == bd["claude"] else "differs from")),
        (README, "restated:control_cost",
         "because the free control already scores %s%%." % _short(bd[CONTROL])),
        (FINDINGS, "restated:control_cost",
         "because the free control already scores %s%%." % _short(bd[CONTROL])),
        (README, "restated:thousandfold",
         "The same tool, %dx slower, depending on the file." % fold_),
        (FINDINGS, "restated:thousandfold",
         "The %dx is not variance" % fold_),
        (README, "restated:earnings_rules",
         "It carries %d of the %d rules on its own" % (earn_rules, all_rules)),
        (SAMPLE_RUN, "restated:mcnemar",
         "%s gaps clear the noise (p = %s) and %s does not (p = %s)"
         % (" and ".join("%s's" % _name(t) for t in loses),
            " and ".join("%.3f" % cmp_[t]["p"] for t in loses),
            " and ".join("%s's" % _name(t) for t in draws),
            " and ".join("%.3f" % cmp_[t]["p"] for t in draws))),
    ]


def emit():
    return (rows_per_page() + rows_corpus() + prose_figures() + review_figures()
            + findings_tables() + findings_prose() + findings_cost()
            + samplerun_blocks() + gh_description() + security_notes()
            + restated_figures())


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

    bodies, lines = {}, {}
    for surface in {s for s, _, _ in derived}:
        with open(os.path.join(ROOT, surface), encoding="utf-8") as fh:
            raw = fh.read()
        bodies[surface] = squash(raw)
        lines[surface] = {ln.rstrip() for ln in raw.splitlines()}

    missing = [(s, t, r) for s, t, r in derived
               if (r.rstrip() not in lines[s] if t.startswith(EXACT)
                   else squash(r) not in bodies[s])]
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
