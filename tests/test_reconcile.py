"""The arithmetic checker's invariants.

The checker is what makes the ground truth verified rather than merely
careful, so a defect in it is worse than a defect in a parser: it does not
produce a wrong score, it produces a wrong FACT about the documents.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reconcile                                                # noqa: E402


def test_a_figure_wrapped_in_parentheses_is_negative():
    # Stripping the parentheses as punctuation turned the FDIC 2023 unrealized
    # loss of (29,569) into +29,569, which made the fund balance miss by twice
    # the figure.
    assert reconcile.num("(29,569)") == -29569.0


def test_a_figure_ending_a_sentence_is_positive_despite_its_closing_paren():
    # The counter-example was already in the corpus before the rule was
    # written, which is why the rule is narrow.
    assert reconcile.num("($657,500,000).") == 657500000.0


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
    # never saw the failure it was guarding against -- it saw 3.0.
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
    # THE GROUND TRUTH CHECKS ITSELF. This is the step that caught four of the
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
    # A per-row rule once skipped every row containing a blank cell -- 7 of 33,
    # including the one where the identity is tightest -- and reported a clean
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
