"""The grader's own invariants.

The grader is where an error in this project concentrates, not in any parser,
because it is the instrument and nothing else measures it. Every test here
pins one way it can be wrong, and each was written by breaking the rule it
protects and watching this file go red.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import score                                                    # noqa: E402


def test_accounting_parentheses_are_read_as_the_minus_sign():
    # A figure wholly wrapped in parentheses is how every financial statement
    # prints a loss. A parser returning the printed form and one returning an
    # explicit minus have both read the page correctly.
    assert score.canon("(29,569)") == "-29569"
    assert score.canon("-29,569") == "-29569"


def test_a_loss_with_its_sign_discarded_is_still_wrong():
    # The other half of the rule above, and the reason it is not just leniency:
    # if parentheses folded away to nothing, a sign flip would score as a
    # correct read, and a sign flip is the most expensive silent error a
    # financial document can carry.
    assert score.canon("29,569") != score.canon("(29,569)")


def test_a_positive_figure_ending_a_sentence_is_not_a_negative():
    # Note 4 of the 1956 income statement ends a sentence with
    # "($657,500,000).": a positive figure wearing a closing paren. The
    # negative rule must be narrow enough to leave it alone.
    assert score.canon("($657,500,000).") == "657500000"


def test_a_figure_in_prose_parentheses_is_not_a_negative_either():
    """The currency sign is the discriminator, not the sentence position.

    Note 4 states three amounts inside prose parentheses and only one of them
    happens to end a sentence. A rule that leans on the trailing period spares
    that one and silently negates the other two, which breaks one sum per rule
    per parser: fourteen manufactured failures with every tool reading the
    page correctly and all seven failing the same field identically.

    The corpus is unanimous on the real distinction: a loss in a column is
    bare because the column header carries the units, and an amount in a
    sentence repeats the dollar sign because a sentence has no header to
    inherit from.
    """
    for prose in ("($1,157,700,000)", "($2,562,146)", "($657,500,000)"):
        assert not score.canon(prose).startswith("-"), (
            f"{prose} is an amount stated in prose, not a loss")
    for loss in ("(29,569)", "(19,228)", "(2,985,415)", "(2,958,199)"):
        assert score.canon(loss).startswith("-"), (
            f"{loss} is a loss in a column and lost its sign")


def test_a_parenthesized_figure_survives_tokenization_intact():
    # The defect that made this necessary: tokens_of stripped the parens as
    # punctuation while canon kept them, so all seven tools were scored CORRUPT
    # with `got` character-identical to `printed`, and twenty-eight silent
    # failures were manufactured in a run that was about to be published.
    assert "(29,569)" in score.tokens_of("unrealized loss of (29,569) on the fund")


def test_tokens_split_on_a_colon_with_no_space_after_it():
    # Docling writes the balance sheet footer as "Place:Kolkata". A
    # whitespace-only split makes that one token matching nothing, and the
    # grader then reports a miss whose closest look-alike is itself.
    assert score.tokens_of("Place:Kolkata") == ["Place", "Kolkata"]


def test_an_html_entity_is_not_scored_as_a_corrupted_character():
    # An ampersand that survived a trip through an HTML writer is a property of
    # the serializer, not a misread. Scoring it punishes one parser for its
    # output format, which is measuring the grader.
    assert score.fold("S.R. Batliboi &amp; Associates") == "S.R. Batliboi & Associates"


def test_thousands_separated_by_spaces_join_into_one_number():
    assert score.join_thousands("132 434 809") == "132434809"


def test_but_two_adjacent_cells_are_never_welded_into_one_number():
    # "10 115.92" is a quantity beside a unit price. Joining them would invent
    # the value 10115.92, which appears nowhere on the page.
    assert score.join_thousands("10 115.92") == "10 115.92"


def test_the_thousands_rule_is_off_unless_the_page_asks_for_it():
    """Plain text cannot tell "132 434 809" from three adjacent cells, so the
    grader must not guess. On a columnar financial table the rule welds a
    comma-grouped figure into its neighbor and destroys the value before it is
    ever compared:

        1,842,842 1,316 738 A79   ->   1,842,842 1,316738 A79

    Markdown output is untouched, because its pipes still separate the cells
    when this runs, so the damage falls only on the parsers that emit plain
    columns, which are the three the results are least kind to. A grader that
    penalizes one output format and not another is measuring the grader.
    """
    row = "obligations. . 1,842,842 1,316 738 A79 1,840,309 11,698"
    assert score.fold(row) == score.fold(row, space_thousands=False)
    assert "1,316 738" in score.fold(row), "an adjacent cell was welded in"
    assert "1,316738" in score.fold(row, space_thousands=True), (
        "the opt-in path no longer joins, so this test proves nothing")


def test_no_page_in_this_corpus_asks_for_the_thousands_rule():
    """It stays for the Slovak cash-flow page in Sample_Documents, which uses
    the convention and is not labeled. If a truth file ever sets the flag,
    this is where to say why.

    The globs are anchored on ROOT, and the count is asserted before the flag
    is, so the test cannot pass over an empty file list when pytest runs from
    another directory.
    """
    import json
    truths = (sorted((ROOT / "real" / "pages").glob("*.truth.json"))
              + sorted((ROOT / "corpus").glob("*.truth.json")))
    assert len(truths) >= 6, (
        f"found only {len(truths)} truth files under {ROOT}; this test cannot "
        f"say anything about a corpus it did not read")
    asked = [f.name for f in truths
             if json.loads(f.read_text()).get("space_thousands")]
    assert asked == [], f"these pages ask for the thousands rule: {asked}"


def test_formatting_that_carries_no_information_is_stripped():
    assert score.canon("$7,126.11") == "7126.11"
    assert score.canon("+3,615.08") == "3615.08"


def test_but_a_leading_minus_is_never_stripped():
    assert score.canon("-20.00") != score.canon("20.00")


# --------------------------------------------------------------------------
# Three grader rules whose removal would move scores and nothing else would
# notice. Each test below fails when its rule is removed.
# --------------------------------------------------------------------------


def test_a_look_alike_made_only_of_other_fields_text_is_not_a_corruption():
    """mask_claimed(), pinned. Mutation: `return line` and this goes red.

    A silent error is expensive precisely because it is plausible, so the
    grader must not MANUFACTURE plausible ones. A line that is entirely
    another field's correct text contains no characters of its own, and a
    window cut out of it is evidence about that other field and nothing else.
    Without the mask, a bank page whose address reads "1000 Walnut Kansas Cty"
    supplies a one-edit look-alike for the branch name the parser never
    returned, and the page scores a silent error it did not commit.
    """
    printed = "1000 Walnut Kansas City"
    line = "1000 Walnut Kansas Cty"        # entirely another field, read right
    others = [line]
    status, got, _ = score.classify_miss(
        printed, score.tokens_of(line), [line], set(), True, others)
    assert status == "ABSENT", (
        f"a window cut out of another field's correct text was reported as "
        f"this field's corruption: {got!r}")


def test_a_token_inside_a_multi_word_value_is_claimed_by_that_value():
    """The claimed-parts guard in grade_page(), pinned.

    Mutation: drop the `parts` union from grade_page and this goes red.
    "1000 Walnut" is one labeled value, so the bare token "1000" belongs to it
    and is not free to be reported as a corruption of check numbers 1001 and
    1002 in turn, which would invent silent errors from an address the parser
    read correctly.

    This goes through grade_page rather than classify_miss. The guard is a line
    in grade_page that builds `claimed`; a test that assembled `claimed` itself
    and passed it to classify_miss would prove the mechanism works and pin
    nothing, because deleting the production line would not touch it.

    The guard only ever moves a verdict from CORRUPT to ABSENT, which is the
    safe direction: it can understate the silent count and never inflate it.
    """
    truth = {"doc_id": "synthetic", "rows": [],
             "printed": {"branch_address": "1000 Walnut",
                         "check_1": "1001", "check_2": "1002"}}
    # A parser that returned ONLY the address, and returned it correctly.
    graded = score.grade_page(truth, "1000 Walnut\n")
    verdicts = {k: v["status"] for k, v in graded["fields"].items()}
    assert verdicts["branch_address"] == "OK"
    assert verdicts["check_1"] == "ABSENT", (
        f"the token 1000, which belongs to the address, was reported as a "
        f"corruption of check_1: {graded['fields']['check_1']}")
    assert verdicts["check_2"] == "ABSENT"


def test_an_accent_is_folded_so_the_correct_read_is_not_scored_corrupt():
    """NFD combining-mark stripping in fold(), pinned.

    Mutation: drop the NFD pass and this goes red. The Slovak cash-flow page
    prints its auditor with a hacek; some parsers return it, some drop it, and
    the hand label is typed in ASCII. Unfolded, the parsers that read the page
    correctly would score CORRUPT and the one that loses the diacritic would
    score OK, which is the grader inverting the result it is there to measure.
    """
    label = "RNDr. Jozef Pleska, CSc."
    returned = "auditor: RNDr. Jozef Ple\u0161k\u00e1, CSc. signed"
    assert score.substr_match(label, score.lines_of(returned)), (
        "a correctly-read accented name did not match its ASCII hand label")
    # Nothing in this corpus is distinguished only by an accent, so folding
    # costs no discrimination. A leading minus still must not fold away,
    # which is the line between "formatting" and "content".
    assert score.canon("-20.00") != score.canon("20.00")


def _page(printed, rows=()):
    return {"doc_id": "T1", "printed": dict(printed), "rows": list(rows)}


def test_one_printed_token_credits_one_field_not_every_field_sharing_it():
    # Without consume-once, a single "11" credits twelve monthly fields of "11".
    truth = _page({"m1": "11", "m2": "11", "m3": "11"})
    once = score.grade_page(truth, "Hours 11\n")
    assert once["ok"] == 1, once["fields"]
    thrice = score.grade_page(truth, "Hours 11 11 11\n")
    assert thrice["ok"] == 3, thrice["fields"]


def test_a_regrouped_number_is_joined_only_from_neighbors_on_one_line():
    # OCR that regroups digits is credited: "22 167087" is 22167087.
    ok = score.grade_page(_page({"v": "22167087"}), "Total 22 167087\n")
    assert ok["fields"]["v"]["status"] == "OK", ok["fields"]
    # The pieces must be neighbors. Once "5" is taken by field a, the
    # "12" and "345" on either side of it are not adjacent, and neither are
    # tokens on two different lines.
    truth = _page({"a": "5", "b": "12345"})
    split = score.grade_page(truth, "12 5 345\n")
    assert split["fields"]["a"]["status"] == "OK", split["fields"]
    assert split["fields"]["b"]["status"] != "OK", split["fields"]
    lines = score.grade_page(_page({"b": "12345"}), "12\n345\n")
    assert lines["fields"]["b"]["status"] != "OK", lines["fields"]
    # A token another field took is not a piece of this one.
    used = score.grade_page(_page({"a": "34", "b": "1234"}), "12 34\n")
    assert used["fields"]["a"]["status"] == "OK", used["fields"]
    assert used["fields"]["b"]["status"] != "OK", used["fields"]


def test_a_multiword_value_printed_once_credits_one_field():
    truth = _page({"ship_to": "1000 Walnut Street", "bill_to": "1000 Walnut Street"})
    once = score.grade_page(truth, "Ship to 1000 Walnut Street\n")
    assert once["ok"] == 1, once["fields"]
    twice = score.grade_page(truth, "Ship to 1000 Walnut Street\nBill to 1000 Walnut Street\n")
    assert twice["ok"] == 2, twice["fields"]


def test_unanchored_rows_graded_against_the_page_cannot_share_one_token():
    # A row whose anchor never appears is graded against the whole page, so
    # without consume-once one "40" credits the quantity of every such row.
    rows = [{"anchor": "SKU-1", "cells": {"qty": "40"}},
            {"anchor": "SKU-2", "cells": {"qty": "40"}}]
    truth = _page({}, rows)
    one = score.grade_page(truth, "Qty 40\n")
    assert one["ok"] == 1, one["fields"]
    two = score.grade_page(truth, "Qty 40 40\n")
    assert two["ok"] == 2, two["fields"]


def test_recovery_is_reported_with_and_without_the_errored_pages():
    # A page a parser raised on leaves the first denominator and is
    # counted in the second.
    page = {"n_fields": 10, "ok": 8, "corrupt": 1, "absent": 1, "misplaced": 0,
            "corrupt_typed": 1, "rows_anchored": 0, "n_rows": 0}
    s = score.summarize([page], errored_fields=10)
    assert s["recovery"] == 0.8
    assert s["recovery_including_errors"] == 0.4
    assert s["fields_on_errored_pages"] == 10
    assert score.summarize([page])["recovery_including_errors"] == 0.8


def test_main_counts_the_fields_of_a_page_the_parser_raised_on(tmp_path, monkeypatch):
    import json
    corpus, out = tmp_path / "corpus", tmp_path / "out"
    (out / "p").mkdir(parents=True)
    corpus.mkdir()
    for doc in ("A", "B"):
        (corpus / f"{doc}.truth.json").write_text(json.dumps(
            {"doc_id": doc, "printed": {"x": "PO-1", "y": "2026-01-01"}, "rows": []}))
    (out / "p" / "A_150.txt").write_text("PO-1 2026-01-01\n")
    (out / "p" / "manifest.json").write_text(json.dumps({
        "version": "t", "source": "png", "records": [
            {"doc_id": "A", "dpi": 150, "seconds": 0.1, "error": None,
             "text_file": "A_150.txt"},
            {"doc_id": "B", "dpi": 150, "seconds": 0.1,
             "error": "RuntimeError: boom", "text_file": "B_150.txt"}]}))
    monkeypatch.setattr(sys, "argv", ["score.py", "--corpus", str(corpus),
                                      "--out", str(out)])
    score.main()
    s = json.loads((out / "scores.json").read_text())["p"]["by_dpi"]["150"]
    assert s["recovery"] == 1.0
    assert s["fields_on_errored_pages"] == 2
    assert s["recovery_including_errors"] == 0.5


def test_finding_a_value_in_another_row_does_not_use_it_up():
    # Both rows print 37; row 1's copy did not come back in its own window, row
    # 2's did. Row 1 is MISPLACED (the value is on the page, elsewhere) and
    # row 2 must still be credited with its own copy, not scored as having
    # read "37" as "37".
    rows = [{"anchor": "SKU-1", "cells": {"sku": "SKU-1", "qty": "37"}},
            {"anchor": "SKU-2", "cells": {"sku": "SKU-2", "qty": "37"}}]
    g = score.grade_page(_page({}, rows), "SKU-1 x\nSKU-2 37\n")
    assert g["fields"]["rows[0].qty"]["status"] == "MISPLACED", g["fields"]
    assert g["fields"]["rows[1].qty"]["status"] == "OK", g["fields"]


def test_a_row_cell_gets_the_copy_in_its_own_window_before_a_page_field():
    # One "37" on the page, printed once in a row and once as a page total.
    # The row, whose location is known, takes it; the total is ABSENT.
    rows = [{"anchor": "SKU-1", "cells": {"sku": "SKU-1", "qty": "37"}}]
    truth = _page({"total": "37"}, rows)
    g = score.grade_page(truth, "SKU-1 37\n")
    assert g["fields"]["rows[0].qty"]["status"] == "OK", g["fields"]
    assert g["fields"]["total"]["status"] == "ABSENT", g["fields"]


def test_two_cells_of_one_row_sharing_a_value_are_not_scored_as_misreads():
    # fdic_earnings row 20 prints 14,090 for both "us" and "continental_us".
    # With one copy returned, one cell is credited and the other is ABSENT,
    # not CORRUPT with "read as '14,090' (printed '14,090')", which
    # reconcile.py would count as a quiet failure that never happened.
    rows = [{"anchor": "R20", "cells": {"label": "R20", "us": "14,090",
                                         "continental_us": "14,090"}}]
    g = score.grade_page(_page({}, rows), "R20 14,090\n")
    st = sorted(g["fields"][f]["status"] for f in ("rows[0].us", "rows[0].continental_us"))
    assert st == ["ABSENT", "OK"], g["fields"]


def test_a_word_joined_to_the_last_by_an_em_dash_is_still_a_word():
    # "Other areas\u2014Alaska" came back from GPT and was scored CORRUPT with
    # got "Alaska" at distance zero.
    g = score.grade_page(_page({"col_alaska": "Alaska"}),
                         "| Other areas\u2014Alaska | Puerto Rico |\n")
    assert g["fields"]["col_alaska"]["status"] == "OK", g["fields"]


def test_a_number_split_across_two_lines_is_not_called_taken():
    """A value whose digits sit on two lines is not on the page; no other
    field took it, so it must not carry the note that another did."""
    got = score.grade_page(_page({"a": "12345"}), "12\n345\n")["fields"]["a"]
    assert got["status"] == "ABSENT"
    assert "note" not in got, got
