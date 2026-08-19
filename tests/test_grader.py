"""The grader's own invariants.

The grader is where an error in this project concentrates, not in any parser,
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
    this is where to say why."""
    import glob
    import json
    asked = [f for f in glob.glob("real/pages/*.truth.json") + glob.glob("corpus/*.truth.json")
             if json.load(open(f)).get("space_thousands")]
    assert asked == [], f"these pages ask for the thousands rule: {asked}"


def test_formatting_that_carries_no_information_is_stripped():
    assert score.canon("$7,126.11") == "7126.11"
    assert score.canon("+3,615.08") == "3615.08"


def test_but_a_leading_minus_is_never_stripped():
    assert score.canon("-20.00") != score.canon("20.00")
