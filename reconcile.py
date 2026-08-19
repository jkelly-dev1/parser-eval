#!/usr/bin/env python3
"""Ask whether each parser's errors survive the document's own arithmetic.

    python3 reconcile.py

This is the question a payload-only check cannot answer; score.py splits a
parser's misses into ABSENT (a hole, loud) and CORRUPT (a same-shape
look-alike, quiet). But "quiet" there means quiet to a reader comparing text.
The check that actually runs in production is arithmetic: something downstream
adds up the line items and compares them with the printed total. So for every
corrupted value, there is a further question:

    Does the corruption break a sum the document asserts about itself?

    BROKEN    it does. The error is loud after all: a cross-field rule
              rejects the extraction and nothing wrong reaches the database.
    SURVIVES  it does not. The figures still add up and one of them is wrong.
              This is the error class the whole exercise is looking for, and
              it is invisible to every check that does not leave the payload.
    INCOMPLETE a value in the sum is missing entirely, so the check cannot
              run. Loud, for the same reason ABSENT is loud.

WHY IT REUSES scores.json rather than re-parsing. The per-field verdicts are
already computed, already reviewed, and already carry the exact token each
parser returned in place of the right one. Re-extracting the numbers here
would introduce a second, differently-buggy reader of the same output.

It also checks the ground truth first. Every sum is verified against the
hand-labeled values before any parser is judged by it. A label typed wrong
would otherwise show up as every parser failing the same sum, which reads
exactly like a finding.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def num(s: str) -> float:
    """Parse a printed figure. Spaces, commas and currency signs are noise.

    A figure wholly wrapped in parentheses is negative. That is how every
    financial statement prints a loss, and stripping the parentheses as
    punctuation turned the FDIC's 2023 unrealized loss of (29,569) into
    +29,569, which made the fund balance miss by twice the figure. The rule
    could have been dodged by writing the sums in absolute values, the way the
    1956 income statement writes its deductions, but a balance sheet that
    prints both signs in the same column cannot be rearranged into one.

    The test is deliberately narrow, and the counter-examples are already in
    the corpus. Note 4 of the 1956 income statement states two amounts inside
    prose parentheses, "($1,157,700,000)" and "($657,500,000)", and the 1956
    balance sheet states a third, "($2,562,146)". All three are positive
    figures in a sentence, not losses. So the parentheses must WRAP the whole
    token, contain nothing but a number, and "(Note 3)" is not a figure at all.

    And the parenthetical must not carry a currency sign. That is what
    separates the two conventions, and the corpus is unanimous on it: every
    accounting negative on the 2023 balance sheet is bare, (29,569), (19,228),
    (2,985,415), (2,958,199), because the column header carries the units,
    while every prose parenthetical repeats the dollar sign because a sentence
    has no column header to inherit from. The truth files encode the same
    split: the negatives are labeled "(29,569)" WITH the parentheses and the
    prose figures are labeled "1,157,700,000" without them.

    Relying on the trailing period instead is relying on an accident of
    sentence position: of the three prose figures only "($657,500,000)." ends
    a sentence, so a period-based rule spares that one and negates the other
    two: fourteen sums broken across seven parsers, all reading the page
    correctly.
    """
    t = s.strip()
    inner = t[1:-1].strip() if t.startswith("(") and t.endswith(")") else None
    neg = inner is not None and re.fullmatch(r"\s*[\d,. ]*\d[\d,. ]*", inner)
    body = inner if neg else t
    # A figure contains no letters, and saying so is not pedantry. The line
    # below deletes every character that is not a digit, a point or a minus,
    # which means ANY string with a digit somewhere in it used to yield a
    # number: "(Note 3)" parsed as 3.0. The paragraph above says that is not a
    # figure at all, and until this guard existed the code did not agree, so a
    # caller that guards num() with try/except never saw the failure it was
    # guarding against, it saw a plausible wrong value instead.
    if re.search(r"[A-Za-z]", body):
        raise ValueError(f"not a number: {s!r}")
    t2 = re.sub(r"[^\d.\-]", "", body.replace(" ", ""))
    if t2 in ("", "-", "."):
        raise ValueError(f"not a number: {s!r}")
    v = float(t2)
    return -abs(v) if neg else v


def cell_lookup(truth: dict) -> dict[str, tuple[int, str]]:
    """'Capital.y2016' -> (row index, cell name), for the sum definitions.

    A row may carry an explicit `key` AND SOME MUST. The reference name is
    normally the anchor, because the anchor is the row's printed label and a
    sum that names it reads like the page. But a printed label is not always
    unique: the FDIC earnings table prints "All other", "Recoveries" and
    "Transfers to reserve accounts" TWICE each, once under securities and once
    under loans. Building this map from anchors alone let the second row
    quietly overwrite the first, so a sum naming "All other.us" resolved to
    whichever row was labeled last and checked the wrong cell, while reporting
    HOLDS. `key` disambiguates those rows for reference purposes only;
    score.py still matches parser output on `anchor`, which is what the page
    actually prints. A table that needs `key` for one row is better off giving
    one to every row: mixing short keys and long label fragments across 36 sum
    definitions is how a reference gets pointed at the wrong row by hand.

    A collision now raises. Silently keeping the last writer is the failure
    shape this project keeps rediscovering: a lookup that answers confidently
    where it should refuse.
    """
    out = {}
    for i, r in enumerate(truth.get("rows", [])):
        ref = r.get("key", r["anchor"])
        for name in r["cells"]:
            full = f"{ref}.{name}"
            if full in out:
                raise ValueError(
                    f"duplicate cell reference {full!r} (rows {out[full][0]} "
                    f"and {i}) -- give one of them a distinct \"key\"")
            out[full] = (i, name)
    return out


def tolerance_of(spec: dict) -> float:
    """How far a sum may miss before it is BROKEN. Exact unless declared.

    The default is exact and should stay that way. Every sum on the FDIC
    balance sheet, the income statement and the 1929 census schedules closes
    to the unit, and that is what makes them worth checking: a rule that only
    has to be nearly right cannot tell a misread digit from a rounding
    artifact.

    A tolerance is for a page that rounds its own arithmetic. Table 114 of the
    FDIC report prints amounts in THOUSANDS of dollars, each rounded on its
    own, so the eight earnings components do not add to the printed earnings
    total; they miss by up to 4 in the US column, and 19 of its 36 column sums
    are off by 1 to 4. That is the page being internally consistent in dollars
    and inconsistent in the thousands it prints. Refusing a tolerance there
    does not buy strictness, it just throws away 36 checks.

    What the tolerance costs, stated plainly: a sum with tolerance 5 cannot
    see an error smaller than 5. A parser that reads 10,008 as 10,003 passes
    it. Most misreads are not that kind, they hit a leading digit, drop a
    digit, or merge two cells, and move the sum by thousands, but "verified
    by arithmetic" means something weaker for these sums than for the exact
    ones, and any write-up must say so. On the earnings page the exact claim
    belongs to the 33 row identities instead, which close to the unit.
    """
    return float(spec.get("tolerance", 0.005))


def value_seen(fields: dict, key: str, printed: str) -> tuple[str, str | None]:
    """(status, value the parser effectively returned) for one graded cell."""
    v = fields.get(key)
    if v is None:
        return "MISSING_FROM_GRADE", None
    if v["status"] == "OK":
        return "OK", printed
    if v["status"] == "MISPLACED":
        # The right characters, attached to the wrong row. For an arithmetic
        # check the value is present and correct in isolation, so the sum
        # cannot see it; the row it landed in is the defect.
        return "MISPLACED", printed
    if v["status"] == "CORRUPT" and v.get("got"):
        return "CORRUPT", v["got"]
    return "ABSENT", None



def resolve_ref(truth: dict, key: str) -> tuple[str, str]:
    """(graded field key, printed value) for one field name within a document.

    Shared by the within-page sums and the cross-page identities, so a name
    means the same thing in both. A name is either a table cell, "Capital.
    y2016", the anchor and the cell, or a scalar printed field.
    """
    lut = cell_lookup(truth)
    if key in lut:
        i, name = lut[key]
        return f"rows[{i}].{name}", truth["rows"][i]["cells"][name]
    if key in truth["printed"]:
        return key, truth["printed"][key]
    raise KeyError(f"{key} is neither a row cell nor a printed field")


def check_identities(spec_file: Path, truths: dict,
                     graded: dict | None) -> list[dict]:
    """Evaluate identities that span two documents.

    Why this exists. A page's own arithmetic catches a parser that misreads a
    figure inside that page. It cannot catch a parser that reads two pages
    each self-consistently but disagrees with itself across them, and real
    documents assert across pages constantly. The FDIC statements do it six
    times: the income statement's closing fund IS the balance sheet's deposit
    insurance fund, note 1's two credit figures ARE the balance sheet's
    assessment-credit lines, and three more figures appear in the notes of one
    page and the columns of the other.

    That is a stronger test than it looks. Reading 1,690,818,394 correctly on
    one page and 1,690,818,894 on the other leaves BOTH pages internally
    consistent; only the identity between them fails.

    Every term must come from the SAME PARSER: this grades one tool's
    coherence across a document set, not agreement between tools.

    Rule form, in cross_checks.json beside the truth files:

        {"name": "fund_ties_to_balance_sheet",
         "of":   ["fdic_income.fund_closing_1956"],
         "equals": "fdic_balance.insurance losses and related expenses.total"}

    `equals` may name a field the same way, or be a literal figure. `of` sums
    its terms, so a cross-page identity and a cross-page sum are one rule
    form: one term makes it an identity, several make it a sum.
    """
    if not spec_file.exists():
        return []
    spec = json.loads(spec_file.read_text())
    out = []

    def pull(ref: str) -> tuple[float, str, str | None]:
        """(value, status, note) for a 'doc_id.field' reference."""
        doc, _, field = ref.partition(".")
        if doc not in truths:
            raise KeyError(f"{ref}: no truth file for {doc!r}")
        field_key, printed = resolve_ref(truths[doc], field)
        if graded is None:
            return num(printed), "OK", None
        if doc not in graded:
            return 0.0, "MISSING", f"{doc} not graded"
        st, got = value_seen(graded[doc]["fields"], field_key, printed)
        if got is None:
            return 0.0, "MISSING", f"{ref} {st}"
        try:
            return num(got), st, (f"{ref} read as {got!r} (printed "
                                  f"{printed!r})" if st == "CORRUPT" else None)
        except ValueError:
            return 0.0, "MISSING", f"{ref} unparseable {got!r}"

    for rule in spec.get("identities", []):
        terms, status, notes = [], "HOLDS", []
        for ref in rule["of"]:
            val, st, note = pull(ref)
            if st == "MISSING":
                status = "INCOMPLETE"
                notes.append(note)
                continue
            terms.append(val)
            if note:
                notes.append(note)
        # Field first, literal second: same reason as in check_sums.
        want_ref = rule["equals"]
        try:
            val, st, note = pull(want_ref)
        except KeyError:
            val, st, note = num(want_ref), "OK", None
        if True:
            if st == "MISSING":
                status = "INCOMPLETE"
                notes.append(note)
                want = 0.0
            else:
                want = val
                if note:
                    notes.append(note)
        if status != "INCOMPLETE":
            got_sum = sum(terms)
            if abs(got_sum - want) > 0.005:
                status = "BROKEN"
            elif any("read as" in n for n in notes):
                status = "SURVIVES"
            notes.append(f"{got_sum:,.2f} vs {want:,.2f}")
        out.append({"name": rule["name"], "status": status, "notes": notes})
    return out

def check_sums(truth: dict, fields: dict | None) -> list[dict]:
    """Evaluate every sum the truth file declares. fields=None checks truth."""
    recon = truth.get("reconciliation")
    if not recon:
        return []
    lut = cell_lookup(truth)
    rows = truth["rows"]
    out = []

    def resolve(key: str) -> tuple[str, str]:
        """(graded field key, printed value) for a name used in a sum.

        A sum may name a table cell ("Capital.y2016") or a scalar field on the
        page ("beginning_balance"). The bank statement's summary block is the
        second kind: it is not a table, it is six labeled amounts that must
        add up to a seventh.
        """
        if key in lut:
            i, name = lut[key]
            return f"rows[{i}].{name}", rows[i]["cells"][name]
        if key in truth["printed"]:
            return key, truth["printed"][key]
        raise KeyError(f"{key} is neither a row cell nor a printed field")

    for spec in recon.get("sums", []):
        terms, status, notes = [], "HOLDS", []
        # `Minus` is for a relation with two terms on each side. Subtraction is
        # normally written here as addition (the income statement deducts
        # 87,741,613 from 155,141,790 to reach 67,400,177, and the rule adds
        # the remainder back to the deduction) because a - b = c rearranges to
        # c + b = a, which has one term on the right and fits `equals`.
        #
        # That rearrangement runs out at four terms. Table 114's bottom line is
        # net current operating earnings plus recoveries minus losses equals
        # net profits before income taxes. Every rearrangement of it leaves two
        # terms on one side, and no field on the page holds their subtotal, so
        # there is nothing for `equals` to name. Inventing a truth-file
        # constant for the missing subtotal would be labeling a figure the page
        # does not print. `minus` states the relation as the page states it.
        signed = ([(k, 1.0) for k in spec["of"]]
                  + [(k, -1.0) for k in spec.get("minus", [])])
        for key, sign in signed:
            field_key, printed = resolve(key)
            if fields is None:
                terms.append(sign * num(printed))
                continue
            st, got = value_seen(fields, field_key, printed)
            if got is None:
                status = "INCOMPLETE"
                notes.append(f"{key} {st}")
                continue
            try:
                terms.append(sign * num(got))
            except ValueError:
                status = "INCOMPLETE"
                notes.append(f"{key} unparseable {got!r}")
                continue
            if st == "CORRUPT":
                notes.append(f"{key} read as {got!r} (printed {printed!r})")
            elif st == "MISPLACED":
                notes.append(f"{key} landed in another row")
        # `Equals` may name a field rather than a literal, and naming the
        # field is better. A literal total written into the truth file is a
        # second copy of a number that is already labeled somewhere on the
        # page, and the two copies can disagree without anything noticing: the
        # sum checks its terms against the literal while the labeled field
        # sits unverified beside it. A reference removes the duplicate.
        #
        # A field name is tried first, and the order is not arbitrary. Field
        # names here contain digits, fund_closing_1956, note4_face_value, and
        # num() strips everything that is not a digit, so asking "does it
        # parse as a number?" First says YES to those and silently compares
        # the sum against 1,956 and 4. Resolving as a field first and falling
        # back to a literal cannot make that mistake: a name that is not a
        # field raises, and a literal is not a field.
        want_ref = spec["equals"]
        try:
            want_key, want_printed = resolve(want_ref)
        except KeyError:
            want_key = None
            want = num(want_ref)
        if want_key is not None:
            if fields is None:
                want = num(want_printed)
            else:
                st, got = value_seen(fields, want_key, want_printed)
                if got is None:
                    status = "INCOMPLETE"
                    notes.append(f"{want_ref} {st}")
                    want = 0.0
                else:
                    # The target needs the same guard as the terms, and did
                    # not have it. A term that comes back unparseable is
                    # recorded as INCOMPLETE and the run continues; the same
                    # value in `equals` went straight into num() and took the
                    # whole reconciliation down. Tesseract returns the census
                    # schedule's handwritten total as "11311-", trailing dash
                    # and all, which is a perfectly ordinary thing for an OCR
                    # engine to do with a struck-through pencil figure.
                    #
                    # A crash here is the worst available outcome. The parser
                    # being graded is the only thing in this program expected
                    # to return garbage, and garbage in one cell of one
                    # document threw away the results for four others.
                    try:
                        want = num(got)
                    except ValueError:
                        status = "INCOMPLETE"
                        notes.append(f"{want_ref} unparseable {got!r}")
                        want = 0.0
                    else:
                        if st == "CORRUPT":
                            notes.append(f"{want_ref} read as {got!r} "
                                         f"(printed {want_printed!r})")
        if status != "INCOMPLETE":
            got_sum = sum(terms)
            if abs(got_sum - want) > tolerance_of(spec):
                status = "BROKEN"
            elif notes and any("read as" in n for n in notes):
                status = "SURVIVES"
            notes.append(f"sum {got_sum:,.2f} vs printed {want:,.2f}"
                         + (f" (tolerance {spec['tolerance']:,})"
                            if "tolerance" in spec else ""))
        out.append({"name": spec["name"], "status": status, "notes": notes})

    for spec in recon.get("row_rules", []):
        # A per-row rule, evaluated once for every row that carries the cells.
        #
        # Two forms. The original takes `cells`: three names, and asserts that
        # the first two differ by the third. The second takes `of` and
        # `equals`, cell names within the same row, and asserts that the terms
        # add to the total, which is the same shape as a `sums` entry turned
        # sideways.
        #
        # A sideways form is what a wide table needs. Table 114 asserts, on
        # every one of its 33 rows, that the U.S. Column equals Alaska plus
        # Puerto Rico plus Other plus the Continental U.S. Written as 33
        # entries in `sums` that is 33 near-identical blocks of JSON; written
        # here it is one rule that the checker applies row by row, and adding
        # a row to the table adds a check for free. All 33 close to the unit,
        # so this form takes no tolerance on that page.
        if "of" in spec:
            for i, r in enumerate(rows):
                # A cell the truth omits contributes nothing, it does not
                # cancel the row. Table 114 prints leader dots where a state
                # reported nothing, and those cells are deliberately unlabeled.
                # Requiring every named cell to be present skipped 7 of the 33
                # rows. Including "Recoveries" under securities, where the
                # identity is at its most informative because three of the four
                # terms are blank and the fourth must equal the total. The
                # checker reported 62 rules where the page asserts 69 and said
                # nothing about the 7 it dropped, which is the failure this
                # project keeps meeting: a check that quietly declines.
                #
                # `equals` MUST be present, with no total there is nothing to
                # check against, and at least one term must be present, so a
                # wholly blank row is skipped rather than asserting 0 = 0.
                if spec["equals"] not in r["cells"]:
                    continue
                have = [c for c in spec["of"] if c in r["cells"]]
                if not have:
                    continue
                names = have + [spec["equals"]]
                vals, status, notes = {}, "HOLDS", []
                for name in names:
                    printed = r["cells"][name]
                    if fields is None:
                        vals[name] = num(printed)
                        continue
                    st, got = value_seen(fields, f"rows[{i}].{name}", printed)
                    if got is None:
                        status = "INCOMPLETE"
                        notes.append(f"{name} {st}")
                        continue
                    try:
                        vals[name] = num(got)
                    except ValueError:
                        status = "INCOMPLETE"
                        notes.append(f"{name} unparseable {got!r}")
                        continue
                    if st == "CORRUPT":
                        notes.append(f"{name} read as {got!r} "
                                     f"(printed {printed!r})")
                    elif st == "MISPLACED":
                        notes.append(f"{name} landed in another row")
                if status != "INCOMPLETE":
                    got_sum = sum(vals[c] for c in have)
                    want = vals[spec["equals"]]
                    if abs(got_sum - want) > tolerance_of(spec):
                        status = "BROKEN"
                    elif any("read as" in n for n in notes):
                        status = "SURVIVES"
                    notes.append(f"sum {got_sum:,.2f} vs printed {want:,.2f}")
                out.append({"name": f"{spec['name']}[{r['anchor']}]",
                            "status": status, "notes": notes})
            continue
        for i, r in enumerate(rows):
            if not all(c in r["cells"] for c in spec["cells"]):
                continue
            vals, status, notes = [], "HOLDS", []
            for name in spec["cells"]:
                printed = r["cells"][name]
                if fields is None:
                    vals.append(num(printed))
                    continue
                st, got = value_seen(fields, f"rows[{i}].{name}", printed)
                if got is None:
                    status = "INCOMPLETE"
                    notes.append(f"{name} {st}")
                    continue
                try:
                    vals.append(num(got))
                except ValueError:
                    status = "INCOMPLETE"
                    notes.append(f"{name} unparseable {got!r}")
                    continue
                if st == "CORRUPT":
                    notes.append(f"{name} read as {got!r} "
                                 f"(printed {printed!r})")
            if status != "INCOMPLETE":
                a, b, d = vals
                ok = abs(abs(a - b) - abs(d)) <= 0.005
                if not ok:
                    status = "BROKEN"
                elif any("read as" in n for n in notes):
                    status = "SURVIVES"
            out.append({"name": f"{spec['name']}[{r['anchor']}]",
                        "status": status, "notes": notes})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=HERE / "real" / "pages")
    ap.add_argument("--scores", type=Path, default=HERE / "out_real" / "scores.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    truths = {p.name.split(".")[0]: json.loads(p.read_text())
              for p in sorted(args.corpus.glob("*.truth.json"))}
    # Verifying the labels does not require having run a parser, and insisting
    # on it puts the checks in the wrong order. Hand labels are checked against
    # the document's own arithmetic while they are being written, before any
    # parser exists to grade. With no scores file this runs that check alone
    # and stops.
    scores = (json.loads(args.scores.read_text())
              if args.scores.exists() else None)

    print("GROUND TRUTH FIRST. Every sum evaluated against the hand-labeled "
          "values.\n")
    bad = 0
    for doc, truth in truths.items():
        for res in check_sums(truth, None):
            mark = "ok " if res["status"] == "HOLDS" else "FAIL"
            if res["status"] != "HOLDS":
                bad += 1
                print(f"  {mark} {doc:<14} {res['name']:<40} {res['notes']}")
    # The cross-page identities are part of the label check too: a figure
    # mistyped on one page and read correctly on the other shows up here and
    # nowhere else.
    xfile = args.corpus / "cross_checks.json"
    for res in check_identities(xfile, truths, None):
        if res["status"] != "HOLDS":
            bad += 1
            print(f"  FAIL cross-page   {res['name']:<40} {res['notes']}")
    print(f"  {len(truths)} documents checked, {bad} label errors found.\n")
    if bad:
        print("REFUSING TO GRADE PARSERS AGAINST A BROKEN LABEL SET.")
        return 2
    if scores is None:
        print(f"No scores at {args.scores} -- label check only, nothing "
              f"graded.")
        return 0

    print("PARSERS. For each sum: does the parser's version still add up?\n")
    hdr = f"{'parser':<14}{'page':<14}{'holds':>7}{'survives':>10}{'broken':>8}{'incomplete':>12}"
    print(hdr)
    print("-" * len(hdr))
    report = {}
    for parser, r in scores.items():
        for page_key, graded in r["pages"].items():
            doc = page_key.rsplit("_", 1)[0]
            truth = truths.get(doc)
            if not truth or not truth.get("reconciliation"):
                continue
            res = check_sums(truth, graded["fields"])
            c = {k: sum(1 for x in res if x["status"] == k)
                 for k in ("HOLDS", "SURVIVES", "BROKEN", "INCOMPLETE")}
            report.setdefault(parser, {})[doc] = {"counts": c, "detail": res}
            print(f"{parser:<14}{doc:<14}{c['HOLDS']:>7}{c['SURVIVES']:>10}"
                  f"{c['BROKEN']:>8}{c['INCOMPLETE']:>12}")
            if args.verbose:
                for x in res:
                    if x["status"] != "HOLDS":
                        print(f"    {x['status']:<11}{x['name']}")
                        for n in x["notes"]:
                            print(f"      {n}")

    # The cross-page identities were never run against a parser. They were
    # written, documented and mutation-tested against the LABELS, where they
    # belong, since a mistyped label must not be blamed on a tool, and then
    # main() only ever called them with graded=None. The one check in this
    # program that no single page can perform was, in the parser-facing half,
    # dead code. It went unnoticed because it was added in the same session
    # that discarded the corpus, so no parser had yet been run for it to grade.
    print("\nCOHERENCE ACROSS PAGES. Every term from the SAME parser.\n")
    hdr2 = f"{'parser':<14}{'holds':>7}{'survives':>10}{'broken':>8}{'incomplete':>12}"
    print(hdr2)
    print("-" * len(hdr2))
    for parser, r in scores.items():
        by_doc = {g["doc_id"]: g for g in r["pages"].values()}
        res = check_identities(xfile, truths, by_doc)
        if not res:
            continue
        c = {k: sum(1 for x in res if x["status"] == k)
             for k in ("HOLDS", "SURVIVES", "BROKEN", "INCOMPLETE")}
        report.setdefault(parser, {})["cross_page"] = {"counts": c,
                                                       "detail": res}
        print(f"{parser:<14}{c['HOLDS']:>7}{c['SURVIVES']:>10}"
              f"{c['BROKEN']:>8}{c['INCOMPLETE']:>12}")
        if args.verbose:
            for x in res:
                if x["status"] != "HOLDS":
                    print(f"    {x['status']:<11}{x['name']}")
                    for n in x["notes"]:
                        print(f"      {n}")

    print("\nHOLDS       every figure in the sum came back right")
    print("SURVIVES    a figure came back WRONG and the sum still balances")
    print("BROKEN      a wrong figure breaks the sum: a cross-field rule "
          "catches it")
    print("INCOMPLETE  a figure is missing, so the check cannot run at all")

    out = args.scores.parent / "reconcile.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
