"""The grader's own invariants.

THE GRADER IS WHERE AN ERROR IN THIS PROJECT CONCENTRATES, not in any parser,
because it is the instrument and nothing else measures it. Every test here
pins one way it can be wrong, and each was written by breaking the rule it
protects and watching this file go red.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
    # correct read, and a sign flip is the most expensive quiet error a
    # financial document can carry.
    assert score.canon("29,569") != score.canon("(29,569)")


def test_a_positive_figure_ending_a_sentence_is_not_a_negative():
    # Note 4 of the 1956 income statement ends a sentence with
    # "($657,500,000)." -- a positive figure wearing a closing paren. The
    # negative rule must be narrow enough to leave it alone.
    assert score.canon("($657,500,000).") == "657500000"


def test_a_parenthesized_figure_survives_tokenization_intact():
    # The defect that made this necessary: tokens_of stripped the parens as
    # punctuation while canon kept them, so all seven tools were scored CORRUPT
    # with `got` character-identical to `printed`, and twenty-eight quiet
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


def test_formatting_that_carries_no_information_is_stripped():
    assert score.canon("$7,126.11") == "7126.11"
    assert score.canon("+3,615.08") == "3615.08"


def test_but_a_leading_minus_is_never_stripped():
    assert score.canon("-20.00") != score.canon("20.00")
