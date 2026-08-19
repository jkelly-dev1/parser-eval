#!/usr/bin/env python3
"""Grade every parser's text output against what was printed on the page.

    python3 score.py                       # every parser found under out/
    python3 score.py --parser docling      # one of them

What is being measured, in one sentence: for each value printed on the page,
did the parser's text output bring that value back, and when it did not, is
what came back instead OBVIOUSLY BROKEN or QUIETLY WRONG.

The second half is the part nobody publishes. A check that only inspects the
extracted payload is blind to a value that is internally consistent and wrong,
and those are precisely the errors that reach production. A parser leaderboard
reports one number, accuracy, and by that measure a parser with half the error
rate and twice the quiet fraction looks twice as good while being MORE
dangerous. So every miss here is classified:

    ABSENT   the value is simply not in the output. A downstream extractor
             sees a hole and can refuse. Loud, and therefore cheap.
    CORRUPT  something of the right SHAPE came back with the wrong content:
             "1,159.18" read as "1,159.16", "HB-1040Z" as "HB-1O40Z". Well
             formed, in range, and wrong. This is the expensive kind.

Corrupt is split again, because half of it is not quiet. A same-length
look-alike can still be something no field could ever hold: a quantity
returned as "#" is CORRUPT by shape and LOUD in practice, since int("#")
raises. Each corrupt miss therefore carries typed=true/false. Whether the
returned characters could belong to that field at all, judged against the
printed value and not against a schema, and only the typed ones count toward
quiet%.

Corrupt is a candidate, not a verdict. Whether a corrupt value survives an
arithmetic cross-check is a question about a whole extracted payload, and this
script grades text. A misread unit price that no longer multiplies out to the
printed amount would be caught by an arithmetic cross-check; one in a field
with no arithmetic relation to anything, a SKU, a PO number, a vendor, would
not. The split reported here is the input to that question, not the answer to
it. Reconcile.py asks the arithmetic half.

The matching rules, stated so they can be argued with:
  - Single-token values (money, dates, quantities, SKUs, PO numbers, "USD")
    must come back as a WHOLE TOKEN. Substring matching would score "34" as
    recovered because "1,349.00" is on the page.
  - Multi-word values (vendor, description, terms) are matched as a substring
    of a whitespace-collapsed line, because a parser is entitled to lay out
    the spacing differently.
  - Money is compared with and without thousands separators. A parser that
    returns 4017.36 for a printed 4,017.36 has read the number correctly and
    formatted it differently, and scoring that as an error would measure
    formatting.
  - Matching is case-insensitive. Nothing in this corpus is distinguished only
    by case, so case sensitivity would only add noise from the OCR.
  - Line-item cells are looked for in that ROW's block of the output, not
    anywhere on the page, so a quantity cannot be credited to the wrong row.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent

# A truth file is two keys and this script knows nothing else about the
# document. `printed` maps a field name to the string on the page and is
# graded against the whole page. `rows` is a list of {anchor, cells}: the
# anchor is the value that identifies the row (a SKU, a check number, a line
# label) and each cell is graded inside that row's block only. A synthetic
# purchase order and a hand-labeled bank statement produce the same two keys.

MONEY_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*\.\d{2}$|^-?\d+\.\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PO_RE = re.compile(r"^PO[-\s]?\w+$", re.I)
SKU_RE = re.compile(r"^[A-Z]{2}[-\s]?\d{2,4}\w*$", re.I)
INT_RE = re.compile(r"^\d{1,4}$")

# Characters an OCR engine or a Markdown writer inserts that carry no meaning
# for this comparison. Folded rather than stripped, so a dash stays a dash.
_FOLD = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
    "•": " ", "·": " ",
}


def join_thousands(s: str) -> str:
    """Turn "132 434 809" into one token, and NOTHING ELSE into one token.

    The trailing lookahead is not decoration. Without it the pattern fires on
    "... 6in 10 115.92", where 10 is a quantity and 115.92 is the unit price
    beside it: "10" is one-to-three digits, " 115" is a group of three, and
    the match ends happily on the decimal point, silently welding two
    adjacent cells into "10115.92".

    So a run only joins when what follows it is not the start of a decimal:
    "132 434 809 " and "132 434 809." join, "10 115.92" does not.
    """
    return re.sub(r"\b(\d{1,3})((?: \d{3})+)(?![.,]?\d)",
                  lambda m: m.group(1) + m.group(2).replace(" ", ""), s)


def fold(s: str, space_thousands: bool = False) -> str:
    # "&amp;" is an ampersand that survived a trip through an HTML writer, not
    # a misread character. Docling returns the auditor's name as
    # "S.R. Batliboi &amp; Associates"; scoring that as corrupted would be
    # scoring the serializer.
    s = html.unescape(s)
    s = unicodedata.normalize("NFKC", s)
    # Accents are folded. The Slovak cash-flow page prints its auditor as
    # "RNDr. Jozef Pleska, CSc." With a hacek on the s; some parsers return
    # the hacek and some drop it, while the hand label is typed in ASCII.
    # Without folding, the parsers that read the page CORRECTLY score CORRUPT
    # and the one that loses the diacritic scores OK. Nothing in this corpus
    # is distinguished only by an accent, so folding one costs no
    # discrimination; the same argument that makes matching case-insensitive.
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if not unicodedata.combining(c))
    for k, v in _FOLD.items():
        s = s.replace(k, v)
    # Markdown backslash escapes are punctuation, not content. Marker emits
    # money as "\$7,126.11". The backslash is Markdown's escape so the dollar
    # sign is not parsed as a math delimiter. Without this the token
    # canonicalizes to "\7126.11" and never matches "7126.11", so a
    # character-perfect read scores as a corruption. A grader that punishes a
    # parser for its output format is measuring the grader.
    s = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", s)
    # HTML tags are layout and must go. Unstructured returns a recovered
    # table as text_as_html, so its cells arrive as "<td>34</td>". Splitting
    # that on whitespace yields one token with the tags welded on, which
    # matches nothing and costs the parser most of a table it actually read.
    #
    # A tag becomes a SPACE rather than nothing, so <td>a</td><td>b</td> is
    # two tokens and not "ab".
    s = re.sub(r"<[^>]+>", " ", s)
    # Space-separated thousands are one number, not three tokens: on a page
    # that uses them. The Slovak cash-flow page prints 132 434 809, and
    # splitting on whitespace would turn every figure on it into three
    # unrecognizable fragments.
    #
    # It is off by default and the page has to ask for it, because plain text
    # cannot distinguish "132 434 809" from three adjacent table cells. On a
    # columnar financial table the same rule welds a comma-grouped figure into
    # its neighbor, "1,316 738 A79" becomes "1,316738 A79", and the value is
    # destroyed before it is ever compared. Markdown output is unaffected,
    # because the pipes still separate the cells at this point, so the damage
    # falls entirely on the parsers that emit plain columns. A grader that
    # penalizes one output format and not another is measuring the grader.
    #
    # So a truth file declares "space_thousands": true when its page uses the
    # convention. No page in this corpus does; the rule stays because the
    # Slovak page in Sample_Documents needs it if it is ever labeled.
    if space_thousands:
        s = join_thousands(s)
    # Markdown table pipes and heading marks are layout, not content.
    return s.replace("|", " ").replace("*", " ").replace("#", " # ")


def lines_of(text: str, space_thousands: bool = False) -> list[str]:
    out = []
    for raw in fold(text, space_thousands).splitlines():
        s = re.sub(r"\s+", " ", raw).strip()
        if s:
            out.append(s)
    return out


def tokens_of(line: str) -> list[str]:
    """Split a line into the tokens a value could be.

    Split on the colon, not just on whitespace. Docling writes the balance
    sheet's footer as "Place:Kolkata" with no space, and a whitespace-only
    split makes that one token that matches nothing. The grader then reported
    Kolkata as an error whose closest look-alike was Kolkata, at edit distance
    zero. A field the parser read perfectly must not be scored as a miss
    because of a missing space.

    Parens around a number are not punctuation, they are the minus sign.
    Stripping them here while canon() kept them made the grader contradict
    itself: the FDIC 2023 balance sheet prints an unrealized loss as
    "(29,569)", every one of the seven tools returned exactly that, and every
    one was scored CORRUPT with `got` identical to `printed`. Twenty-eight
    rule instances across the run became "quiet failures" that never happened.
    A wholly-parenthesized figure is therefore kept intact and canon() turns
    it into a negative. Unless it carries a currency sign, which is how this
    corpus writes an amount inside prose parentheses rather than a loss in a
    column. See ACCOUNTING_NEG_RE.
    """
    out = []
    for raw in line.replace(":", " ").split():
        if ACCOUNTING_NEG_RE.fullmatch(raw):
            out.append(raw)
            continue
        out.append(raw.strip(",;()[]") or raw)
    return out


def nocomma(s: str) -> str:
    return s.replace(",", "")


def canon(s: str) -> str:
    """Strip the formatting that carries no information, and nothing else.

    Dropped: case, thousands separators, currency signs, a LEADING PLUS, a
    trailing period. A real statement prints "$7,126.11" and "+3,615.08"; a
    parser that returns 7126.11 has read the number correctly.

    NOT dropped: a leading minus. "-20.00" and "20.00" are different amounts,
    and a grader that folded the sign away would score a sign flip, the most
    expensive quiet error a financial document can carry, as a correct read.

    Accounting parentheses are that same sign and become one: "(29,569)"
    canonicalizes to "-29569". This is what lets a parser that returns the
    printed "(29,569)" and one that returns "-29,569" both count as correct,
    while a parser that returns "29,569", the loss with its sign discarded, is
    still wrong, which is the whole reason the minus is protected above.
    """
    t = join_thousands(s).strip()
    m = ACCOUNTING_NEG_RE.fullmatch(t)
    if m:
        return "-" + canon(m.group(1))
    return (t.lower().replace("$", "").replace(",", "")
            .strip().lstrip("+").rstrip(").").lstrip("("))


# A figure wholly wrapped in parentheses: an accounting negative. Deliberately
# narrow. The parens must enclose the entire token and contain nothing but a
# number, so "(Note 3)" is not a figure.
#
# And the parenthetical carries no currency sign. That is what separates an
# accounting negative from a figure stated inside prose parentheses, and this
# corpus is unanimous: the 2023 balance sheet's negatives are bare, (29,569),
# (19,228), (2,985,415), (2,958,199), because the column header carries the
# units, while note 4 of the 1956 income statement repeats the dollar sign
# every time it states an amount in a sentence: ($1,157,700,000),
# ($657,500,000), ($2,562,146). A sentence has no column header to inherit
# from. The truth files encode the same split, labeling the negatives
# "(29,569)" with their parentheses and the prose figures without.
#
# A rule that leans on the trailing period instead leans on sentence position:
# only "($657,500,000)." ends a sentence, so it is spared while the other two
# prose figures are silently negated.
ACCOUNTING_NEG_RE = re.compile(r"\(\s*([\d,. ]*\d[\d,. ]*)\s*\)")

NUMERIC_RE = re.compile(r"^-?[\d ,]+(?:\.\d+)?$")


def concat_match(printed: str, toks: list[str]) -> bool:
    """True when 2-4 ADJACENT tokens concatenate to this number.

    OCR regroups digits and the regrouping is not an error. Tesseract returns
    the Slovak page's "22 167 087" as "22 167087" and "4 070 210" as "4070
    210": same digits, different spaces. Scored token by token those are
    misses, and the reconciliation pass then reads them as figures that came
    back wrong while the row still balances, which is the signature of the
    quiet error this exercise hunts, produced by spacing alone.

    Concatenation is bounded to four tokens and to values of four digits or
    more so that "34" can never be assembled out of a "3" and a "4" sitting in
    different cells. It is only tried for numeric values, and only after the
    ordinary token match has failed.
    """
    pc = canon(printed)
    if len(pc.lstrip("-")) < 4:
        return False
    for i in range(len(toks)):
        acc = ""
        for k in range(4):
            if i + k >= len(toks):
                break
            acc += canon(toks[i + k])
            if acc == pc:
                return True
            if len(acc) > len(pc):
                break
    return False


def token_match(printed: str, toks: list[str]) -> bool:
    p, pc = printed.lower(), canon(printed)
    pn = nocomma(p)
    for t in toks:
        tl = t.lower()
        if tl == p or nocomma(tl) == pn or canon(t) == pc:
            return True
    if NUMERIC_RE.match(printed.strip()):
        return concat_match(printed, toks)
    return False


def substr_match(printed: str, lines: list[str]) -> bool:
    p = re.sub(r"\s+", " ", fold(printed)).strip().lower()
    return any(p in ln.lower() for ln in lines)


def is_multiword(printed: str, space_thousands: bool = False) -> bool:
    """True when the value must be matched as a substring rather than a token.

    The flag must match the one fold() WAS GIVEN. On a page that spaces its
    thousands, "132 434 809" is one token and must take the token path;
    deciding otherwise sends every figure on the page down the substring path,
    where a value can be credited to a line it merely overlaps. On a page that
    does not, joining here while the parser text was left alone would ask the
    two sides different questions.
    """
    p = join_thousands(printed) if space_thousands else printed
    return " " in p.strip()


def edit(a: str, b: str) -> int:
    """Levenshtein distance. Small strings only; the naive version is fine."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def shape_of(printed: str) -> str:
    """Which family of look-alikes could be confused for this value."""
    # a number written with spaced thousands is still a number. Without this
    # line "34 577 036" fell through every pattern to "text", and the prose
    # path, which slides a window along each line looking for the closest
    # substring, happily found the exact characters somewhere on the page
    # and reported the field as CORRUPT with a look-alike identical to the
    # printed value. What Docling actually did there is weld the last group of
    # one cell to the first group of the next ("...036" + "22..." = "03622"),
    # which destroys both values; the honest verdict is ABSENT for both, and
    # the number path reaches it.
    if NUMERIC_RE.match(printed.strip()):
        return "money"
    if MONEY_RE.match(printed):
        return "money"
    if DATE_RE.match(printed):
        return "date"
    if PO_RE.match(printed):
        return "po"
    if SKU_RE.match(printed):
        return "sku"
    if INT_RE.match(printed):
        return "int"
    return "text"


_SHAPE_RE = {"money": MONEY_RE, "date": DATE_RE, "po": PO_RE,
             "sku": SKU_RE, "int": INT_RE}


def mask_claimed(line: str, other_texts: list[str]) -> str:
    """Blank out every stretch of `line` that is another field, read right.

    A look-alike assembled out of other fields' correct text is not evidence
    of anything. When a parser returns only part of a page, the text it DID
    read is a rich source of accidental look-alikes: a page whose bank address
    is "1000 Walnut Kansas City" will happily supply "1000" as a candidate
    corruption of check numbers 1001, 1002 and 1003, and "1000 Walnut Ka" as
    one for an ATM location. Every one of those is made of characters
    belonging to a field the parser got RIGHT.

    Masking is by exact occurrence of the other field's own text, so a window
    that lands on genuinely new characters, a misread SKU sitting in a row
    whose description matched, survives untouched.
    """
    low = line.lower()
    keep = list(line)
    for v in other_texts:
        t = v.lower()
        if len(t) < 3:
            continue                      # too short to be anyone's evidence
        start = 0
        while (i := low.find(t, start)) >= 0:
            for j in range(i, i + len(t)):
                keep[j] = "\x00"
            start = i + len(t)
    return "".join(keep)


def classify_miss(printed: str, toks: list[str], lines: list[str],
                  claimed: set[str], scoped: bool,
                  other_texts: list[str] | None = None
                  ) -> tuple[str, str | None, int | None]:
    """ABSENT or CORRUPT, plus the look-alike that made it CORRUPT.

    `claimed` holds the printed values of the OTHER fields, so a neighboring
    field's correct value is never reported as this field's corruption. That
    guard matters here specifically: the corpus is built so that rows 2 and 3
    carry near-identical amounts, and without it every one of those pairs
    would score as a quiet error on a page the parser read perfectly.

    `other_texts` is the same set unfolded, used to mask multi-word
    candidates: see mask_claimed().
    """
    shape = shape_of(printed)
    if shape == "text":
        # Prose. A near-miss is any line with a high character overlap; report
        # the closest line, capped so a whole paragraph cannot qualify.
        best, bd = None, None
        for ln in lines:
            masked = mask_claimed(ln, other_texts or [])
            for width in (len(printed),):
                for start in range(0, max(1, len(ln) - width + 1)):
                    cand = ln[start:start + width]
                    # A window with nothing of its own in it is another
                    # field's text and cannot be this field's corruption.
                    if not any(c != "\x00" and not c.isspace()
                               for c in masked[start:start + width]):
                        continue
                    d = edit(cand.lower(), printed.lower())
                    if bd is None or d < bd:
                        best, bd = cand, d
        limit = max(1, len(printed) // 4)
        if bd is not None and bd <= limit:
            return "CORRUPT", best, bd
        return "ABSENT", best, bd

    # The candidate is not required to match the shape it was supposed to
    # have. Requiring that makes the classifier blind to the most interesting
    # error on the page: Tesseract reads the SKU "LN-10NY" as "LN-1ONY": a
    # zero recognized as the letter O. That token fails the SKU pattern
    # precisely BECAUSE it is corrupt, so the shape filter discarded it and
    # the field was scored ABSENT. A classifier that can only see corruption
    # which stays inside the schema would report the quiet errors as loud
    # ones, which is the exact inversion of what this script exists to
    # measure.
    #
    # What is required instead: a token of nearly the same length, within an
    # edit distance of a third of the value, that is not some other field's
    # correct value.
    if len(printed) < 3 and not scoped:
        # A one or two character value searched for across a WHOLE PAGE cannot
        # be told apart from any other short token on it; every digit on the
        # sheet is a look-alike for "2". Inside one row's block the window is
        # a single line and a same-length neighbor is a real candidate, so the
        # rule is suspended there. It has to be: the only content errors
        # Docling made on this corpus are single-digit quantities, and a
        # blanket rule against short values would report the one parser that
        # fails quietly as the one that fails loudly.
        return "ABSENT", None, None
    pc = canon(printed)
    limit = max(1, len(pc) // 3)
    best, bd = None, None
    for t in toks:
        tc = canon(t)
        if not tc or abs(len(tc) - len(pc)) > 1:
            continue
        if tc in claimed:
            continue                      # that is some other field, read right
        d = edit(tc, pc)
        if bd is None or d < bd:
            best, bd = t, d
    if bd is not None and bd <= limit:
        return "CORRUPT", best, bd
    # Not close enough to be a corruption of this value. Report the nearest
    # token only while it is still in the same neighborhood, so the artifact
    # does not record "24.95 was read as sleeve" and invite that sentence into
    # a write-up.
    return "ABSENT", (best if bd is not None and bd <= 2 * limit else None), bd


# Money is written differently by every parser and the canonical form already
# strips these, so they never make a numeric value implausible.
_MONEY_PUNCT = set("$,.- ")


def stays_in_alphabet(printed: str, got: str) -> bool:
    """Could `got` pass for a legitimate value of the field that printed
    `printed`, or is it visible junk?

    Corrupt is not the same as quiet and conflating them overstates the whole
    thesis. Docling's only content errors on the synthetic corpus are the
    quantity 9 returned as "#", the quantity 9 returned as "x", and the
    quantity 33 returned as "3e3" with a Greek epsilon. Those are same-length
    look-alikes, so the miss classifier calls them CORRUPT, and counting every
    CORRUPT as quiet reported Docling as failing 100% quietly. Nothing
    downstream would be fooled for an instant: int("#") raises, and so does
    every other cast anyone would put on a quantity. The error is loud the
    moment a type touches it.

    The test is deliberately derived from the PRINTED value rather than from a
    schema, because the truth files carry no types and inventing them would be
    inventing the answer. A digits-only value may come back as digits and its
    own separators; a value with letters may come back with letters. A
    character that could not appear in a legitimate reading of that field, "#"
    in a quantity, a cent sign inside an amount, makes it junk.

    This is not the shape filter that was removed. That one discarded the
    candidate and scored the field ABSENT, which hid "LN-10NY" read as
    "LN-1ONY". Letters and digits where letters and digits belong, which is
    exactly the dangerous case and is still counted quiet here. This splits
    the CORRUPT bucket for reporting and discards nothing.
    """
    got = (got or "").strip()
    if not got:
        return False
    has_digit = any(c.isdigit() for c in printed)
    has_alpha = any(c.isalpha() for c in printed)
    punct = {c for c in printed if not c.isalnum()} | {" "}
    if has_digit and not has_alpha:
        punct |= _MONEY_PUNCT
    for c in got:
        if c.isdigit() and has_digit:
            continue
        if c.isalpha() and has_alpha:
            continue
        if c in punct:
            continue
        return False
    return True


def row_blocks(lines: list[str], rows: list[dict],
               space_thousands: bool = False) -> dict[int, list[str]]:
    """Split the output into one block of lines per table row.

    A row is anchored by its anchor value: a SKU, a reference number, a row
    label, the first figure in the row. The block runs from the anchor line to
    the line before the next anchor, so a parser that puts each cell on its
    own line is graded on the same content as one that emits a Markdown table
    row. WITHOUT letting a cell be credited to a row it was not printed in.

    When an anchor matches several lines, the best one wins, and "best" means
    the line whose window contains the most of that row's other cells. The
    balance sheet is why: its anchor "Capital" also appears in the section
    heading "Capital & Liabilities" one line above, and anchoring on the
    heading would grade the row against the wrong window. Choosing the
    best-fitting window is the most GENEROUS reading of the parser's output,
    so a miss under it is a real miss rather than an anchoring accident.

    A row whose anchor never appears gets an empty block, and its cells are
    then graded against the whole page instead. Also the generous reading:
    if the anchor is the thing that was misread, the cells beside it should
    still be able to score.
    """
    anchors: dict[int, int] = {}
    used: set[int] = set()
    for i, row in enumerate(rows):
        anchor = row["anchor"]
        cells = [v for k, v in row["cells"].items() if v != anchor]
        best_n, best_score = None, -1
        for n, ln in enumerate(lines):
            if n in used:
                continue
            hit = (substr_match(anchor, [ln]) if is_multiword(anchor, space_thousands)
                   else token_match(anchor, tokens_of(ln)))
            if not hit:
                continue
            window = lines[n:n + 4]
            wtoks = [t for w in window for t in tokens_of(w)]
            score = sum(1 for c in cells
                        if (substr_match(c, window) if is_multiword(c, space_thousands)
                            else token_match(c, wtoks)))
            if score > best_score:
                best_n, best_score = n, score
            if score == len(cells):
                break
        if best_n is not None:
            anchors[i] = best_n
            used.add(best_n)
    order = sorted(anchors.items(), key=lambda kv: kv[1])
    blocks: dict[int, list[str]] = {}
    for pos, (idx, n) in enumerate(order):
        end = order[pos + 1][1] if pos + 1 < len(order) else min(len(lines), n + 4)
        end = min(end, n + 4)
        blocks[idx] = lines[n:max(end, n + 1)]
    for i in range(len(rows)):
        blocks.setdefault(i, [])
    return blocks


def grade_page(truth: dict, text: str) -> dict:
    space_thousands = bool(truth.get("space_thousands", False))
    lines = lines_of(text, space_thousands)
    all_toks = [t for ln in lines for t in tokens_of(ln)]
    printed = truth["printed"]
    rows = truth.get("rows", [])
    every = list(printed.values()) + [v for r in rows
                                      for v in r["cells"].values()]
    claimed = ({v.lower() for v in every} | {nocomma(v.lower()) for v in every}
               | {canon(v) for v in every})
    # And the tokens inside a multi-word value are claimed too. The bank
    # statement's street is "1000 Walnut", and without this the token "1000"
    # was free to be reported as a corruption of check number 1001, 1002 and
    # 1003 in turn. Three quiet errors invented out of an address the parser
    # read correctly. The guard only ever moves a verdict from CORRUPT to
    # ABSENT, which is the safe direction: it can understate the quiet count,
    # never inflate it.
    parts = [t for v in every for t in v.split() if len(t) > 1]
    claimed |= ({t.lower() for t in parts} | {nocomma(t.lower()) for t in parts}
                | {canon(t) for t in parts}) - {""}

    fields: dict[str, dict] = {}

    def grade(name: str, want: str, scope_lines: list[str] | None) -> None:
        sl = scope_lines if scope_lines else lines
        toks = [t for ln in sl for t in tokens_of(ln)]
        hit = (substr_match(want, sl) if is_multiword(want, space_thousands)
               else token_match(want, toks))
        if hit:
            fields[name] = {"printed": want, "status": "OK"}
            return
        # Not in scope. Before calling it a miss, check the whole page.
        #
        # A value that came back attached to the wrong row is its own defect
        # and the one a text-only comparison would otherwise hide. The
        # characters are perfect, so no OCR metric sees it; the cell simply
        # landed in a different row of the table. Downstream that is a record
        # that is well formed, complete, and describes a different purchase.
        # Docling does this exactly once on this corpus and Unstructured does
        # it repeatedly, and neither would show up as an error at all if the
        # grader only asked whether the page's characters came back.
        elsewhere = (substr_match(want, lines) if is_multiword(want, space_thousands)
                     else token_match(want, all_toks))
        mine = (want.lower(), nocomma(want.lower()), canon(want))
        others = {c for c in claimed if c not in mine}
        other_texts = [v for v in every if v.lower() not in mine]
        if elsewhere and scope_lines:
            fields[name] = {"printed": want, "status": "MISPLACED",
                            "got": want, "distance": 0}
            return
        status, cand, dist = classify_miss(want, toks or all_toks, sl or lines,
                                           others, bool(scope_lines),
                                           other_texts)
        fields[name] = {"printed": want, "status": status,
                        "got": cand, "distance": dist}
        if status == "CORRUPT":
            fields[name]["typed"] = stays_in_alphabet(want, cand)

    for f, want in printed.items():
        grade(f, want, None)

    n_rows = len(rows)
    blocks = row_blocks(lines, rows, space_thousands)
    for i, r in enumerate(rows):
        for f, want in r["cells"].items():
            grade(f"rows[{i}].{f}", want, blocks[i])

    ok = sum(1 for v in fields.values() if v["status"] == "OK")
    corrupt = sum(1 for v in fields.values() if v["status"] == "CORRUPT")
    absent = sum(1 for v in fields.values() if v["status"] == "ABSENT")
    misplaced = sum(1 for v in fields.values() if v["status"] == "MISPLACED")
    typed = sum(1 for v in fields.values()
                if v["status"] == "CORRUPT" and v["typed"])
    return {
        "doc_id": truth["doc_id"],
        "n_fields": len(fields),
        "ok": ok, "corrupt": corrupt, "absent": absent,
        "misplaced": misplaced, "corrupt_typed": typed,
        "rows_anchored": sum(1 for i in range(n_rows) if blocks[i]),
        "n_rows": n_rows,
        "fields": fields,
    }


def summarize(pages: list[dict]) -> dict:
    n = sum(p["n_fields"] for p in pages)
    ok = sum(p["ok"] for p in pages)
    corrupt = sum(p["corrupt"] for p in pages)
    absent = sum(p["absent"] for p in pages)
    misplaced = sum(p["misplaced"] for p in pages)
    typed = sum(p["corrupt_typed"] for p in pages)
    miss = corrupt + absent + misplaced
    # Quiet = type-valid corrupt + misplaced, and both terms are arguments.
    #
    # MISPLACED, because a value with perfect characters sitting in another
    # row is present, well formed and wrong, and no OCR metric sees it.
    #
    # TYPE-VALID, because the rest of the CORRUPT bucket is not quiet at all.
    # A quantity returned as "#" is a same-length look-alike and is counted
    # CORRUPT, but int("#") raises and the error announces itself. Counting it
    # quiet inflated exactly the number this exercise exists to report. The
    # split is in stays_in_alphabet().
    #
    # ABSENT produces a hole, which anything downstream can see. Whether a
    # given quiet error then survives an arithmetic cross-check is a question
    # about a whole payload and is deliberately not answered here.
    return {
        "pages": len(pages), "fields": n, "ok": ok,
        "corrupt": corrupt, "absent": absent, "misplaced": misplaced,
        "corrupt_typed": typed, "corrupt_junk": corrupt - typed,
        "recovery": round(ok / n, 4) if n else 0.0,
        "quiet_fraction_of_misses": (round((typed + misplaced) / miss, 4)
                                     if miss else None),
        "rows_anchored": sum(p["rows_anchored"] for p in pages),
        "rows": sum(p["n_rows"] for p in pages),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=HERE / "corpus")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--parser", default=None)
    ap.add_argument("--json", type=Path, default=None)
    # One set of hand labels, however many renderings of the page. The four
    # real pages are graded twice. Once as they came out of their source
    # documents, once re-rendered as scans at two resolutions, and copying the
    # truth files next to each rendering would be two sets of ground truth
    # waiting to drift apart.
    ap.add_argument("--truth", type=Path, default=None,
                    help="where the *.truth.json live; defaults to --corpus")
    args = ap.parse_args()

    truths = {p.name.split(".")[0]: json.loads(p.read_text())
              for p in sorted((args.truth or args.corpus)
                              .glob("*.truth.json"))}

    dirs = [d for d in sorted(args.out.iterdir())
            if d.is_dir() and (d / "manifest.json").exists()
            and (args.parser is None or d.name == args.parser)]

    report = {}
    dead: dict[str, int] = {}
    for d in dirs:
        man = json.loads((d / "manifest.json").read_text())

        # A run that produced no text on any page is a failed run, not a 0%
        # score. A library that hits an internal error, logs it as a warning
        # and returns an empty string without raising leaves a clean-looking
        # record with zero characters; graded, that becomes an extra parser
        # sitting at 0.0% recovery. An empty PAGE is still graded, because
        # textlayer returns zero bytes on both 1929 schedules, they have no
        # text layer for it to return, and that is a real result, in fact the
        # one that marks the floor. An empty RUN is not.
        alive = [r for r in man["records"] if not r.get("error")]
        if alive and not any((d / r["text_file"]).read_text().strip()
                             for r in alive):
            dead[d.name] = len(alive)
            continue

        by_dpi: dict[int, list[dict]] = {}
        secs: dict[int, list[float]] = {}
        for rec in man["records"]:
            if rec.get("error"):
                continue
            text = (d / rec["text_file"]).read_text()
            g = grade_page(truths[rec["doc_id"]], text)
            g["dpi"] = rec["dpi"]
            by_dpi.setdefault(rec["dpi"], []).append(g)
            secs.setdefault(rec["dpi"], []).append(rec["seconds"])
        report[d.name] = {
            "version": man["version"], "source": man["source"],
            "errors": [r for r in man["records"] if r.get("error")],
            "by_dpi": {str(k): {**summarize(v),
                                "seconds_per_page": round(
                                    sum(secs[k]) / len(secs[k]), 2)}
                       for k, v in sorted(by_dpi.items())},
            "pages": {f"{g['doc_id']}_{g['dpi']}": g
                      for v in by_dpi.values() for g in v},
        }

    hdr = (f"{'parser':<16}{'dpi':>5}{'fields':>8}{'recovered':>11}"
           f"{'absent':>8}{'corrupt':>9}{'typed':>7}{'misplcd':>9}"
           f"{'quiet%':>8}{'rows':>10}{'s/page':>8}")
    print(hdr)
    print("-" * len(hdr))
    for name, r in report.items():
        for dpi, s in r["by_dpi"].items():
            q = ("   -" if s["quiet_fraction_of_misses"] is None
                 else f"{s['quiet_fraction_of_misses'] * 100:6.0f}%")
            print(f"{name:<16}{dpi:>5}{s['fields']:>8}"
                  f"{s['ok'] / s['fields'] * 100:10.1f}%"
                  f"{s['absent']:>8}{s['corrupt']:>9}"
                  f"{s['corrupt_typed']:>7}{s['misplaced']:>9}{q:>8}"
                  f"{s['rows_anchored']:>6}/{s['rows']:<3}"
                  f"{s['seconds_per_page']:>8.1f}")
        if r["errors"]:
            print(f"{name:<16}  {len(r['errors'])} page(s) failed outright: "
                  f"{r['errors'][0]['error'].splitlines()[0][:60]}")
    for name, n in dead.items():
        print(f"{name:<16}  NOT GRADED: {n} page(s) ran without raising and "
              f"returned no text at all. A run that produces nothing is a "
              f"failed run, not a 0% score.")
    print("\nrecovered  the printed value came back, in the right row")
    print("absent     nothing like it came back           -- a hole, loud")
    print("corrupt    a same-shape look-alike came back")
    print("typed      of those, the ones a downstream cast would ACCEPT")
    print("           -- the rest carry a character the field cannot hold")
    print("           (a quantity read as '#'), and are loud")
    print("misplcd    the exact value came back in ANOTHER row -- quiet")
    print("quiet%     (typed + misplaced) / all misses")

    out = args.json or (args.out / "scores.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
