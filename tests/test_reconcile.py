"""The arithmetic checker's invariants.

The checker is what makes the ground truth verified rather than merely
careful, so a defect in it is worse than a defect in a parser: it does not
produce a wrong score, it produces a wrong FACT about the documents.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import reconcile                                                # noqa: E402


def test_a_figure_wrapped_in_parentheses_is_negative():
    # Stripping the parentheses as punctuation turned the FDIC 2023 unrealized
    # loss of (29,569) into +29,569, which made the fund balance miss by twice
    # the figure.
    assert reconcile.num("(29,569)") == -29569.0


def test_a_figure_ending_a_sentence_is_positive_despite_its_closing_paren():
    # The counter-example was already in the corpus before the rule was
    # written, so the rule is narrow.
    assert reconcile.num("($657,500,000).") == 657500000.0


def test_an_amount_stated_in_prose_parentheses_is_positive():
    """The currency sign is the discriminator, not the sentence position.

    Note 4 of the 1956 income statement states three amounts inside prose
    parentheses and only one of them ends a sentence. A rule that leans on the
    trailing period spares that one and negates the other two, and because
    every parser returns the page correctly, all seven fail the same field
    identically. Section 8 of FINDINGS names that signature: when all seven
    tools fail one field the same way, suspect the checker.

    This corpus is unanimous on the real distinction. A loss in a column is
    bare, because the column header carries the units. An amount in a sentence
    repeats the currency sign, because a sentence has no header to inherit.
    """
    for prose, want in (("($1,157,700,000)", 1157700000.0),
                        ("($2,562,146)", 2562146.0),
                        ("($657,500,000)", 657500000.0)):
        assert reconcile.num(prose) == want, f"{prose} is an amount, not a loss"
    for loss, want in (("(29,569)", -29569.0), ("(19,228)", -19228.0),
                       ("(2,985,415)", -2985415.0), ("(2,958,199)", -2958199.0)):
        assert reconcile.num(loss) == want, f"{loss} is a loss and lost its sign"


def test_no_rule_fails_identically_for_every_parser():
    """The signature of a checker defect, asserted rather than described.

    FINDINGS section 8: "A single sign convention read two ways manufactures
    quiet failures that never happened, across every tool at once, and the
    only tell is that all seven fail one field identically." Seven independent
    tools do not agree on a mistake. When they do, the checker made it.
    """
    import json
    data = json.loads((ROOT / "out_real" / "reconcile.json").read_text())
    parsers = sorted(data)
    broken = {}
    for parser in parsers:
        for page, res in data[parser].items():
            for rule in res.get("detail", []):
                if rule["status"] == "BROKEN":
                    broken.setdefault((page, rule["name"]), set()).add(parser)
    unanimous = {k: v for k, v in broken.items() if len(v) == len(parsers)}
    assert not unanimous, (
        "every parser breaks these rules identically, which is the signature "
        f"of a defect in the checker rather than in any parser: {sorted(unanimous)}")


def test_an_unparseable_figure_raises_rather_than_crashing_the_whole_run():
    # Tesseract returned "11311-" for a hand-written total. A bare float()
    # took the entire reconciliation down with it, so every other page went
    # unreported. It must fail as a catchable, typed error on ONE value.
    with pytest.raises(ValueError):
        reconcile.num("11311-")


def test_a_label_that_merely_contains_a_digit_is_not_a_figure():
    # "(Note 3)" is a footnote reference, not a number. The parser said as
    # much and the checker disagreed: every character that was not a digit was
    # deleted and whatever survived was parsed, so any string with a digit in
    # it produced a value. A caller guarding num() with try/except therefore
    # never saw the failure it was guarding against; it saw 3.0.
    with pytest.raises(ValueError):
        reconcile.num("(Note 3)")


def test_a_digit_misread_as_a_letter_is_unparseable_not_a_smaller_number():
    # Tesseract reads the 4 of "479" as an A on the 1956 earnings table. That
    # is a miss, and it must be reported as one. Silently parsing "A79" as 79
    # feeds a wrong value into a sum that is supposed to detect wrong values.
    with pytest.raises(ValueError):
        reconcile.num("A79")


def test_ordinary_formatting_is_noise_and_is_ignored():
    assert reconcile.num("1,810,140,116") == 1810140116.0
    assert reconcile.num("$8,346,249") == 8346249.0


@pytest.mark.parametrize("doc_id", [
    "fdic_balance", "fdic_income", "fdic_earnings",
    "census29_wages", "census29_sales", "fdic2023_balance",
])
def test_every_sum_each_page_asserts_holds_against_the_hand_labels(doc_id):
    # The ground truth checks itself. This is the step that caught four of the
    # author's own labeling errors on the 1956 scan: a careful reader misreads
    # about one cell in forty at that age of print.
    import json
    truth = json.loads(
        (Path(__file__).resolve().parent.parent
         / "real" / "pages" / f"{doc_id}.truth.json").read_text())
    results = reconcile.check_sums(truth, None)
    assert results, f"{doc_id} declares no rules at all"
    broken = [r for r in results if r["status"] != "HOLDS"]
    assert not broken, f"{doc_id}: {[r['name'] for r in broken]}"


def test_the_rules_that_ran_are_counted_not_just_the_ones_that_passed():
    # A per-row rule once skipped every row containing a blank cell, 7 of 33,
    # including the one where the identity is tightest, and reported a clean
    # pass having checked 26. A checker that declines silently looks exactly
    # like a checker that agrees, so the COUNT is asserted, not just the
    # verdict.
    import json
    truth = json.loads(
        (Path(__file__).resolve().parent.parent
         / "real" / "pages" / "fdic_earnings.truth.json").read_text())
    results = reconcile.check_sums(truth, None)
    assert len(results) == 69, (
        f"the earnings table asserts 69 rule instances, {len(results)} ran")
