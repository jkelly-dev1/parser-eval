"""Cost reporting, and the check no single page can perform."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cloud_cost                                               # noqa: E402
import reconcile                                                # noqa: E402

DOCS = ["fdic_balance", "fdic_income", "fdic_earnings",
        "census29_wages", "census29_sales", "fdic2023_balance"]


def test_a_model_with_no_price_is_reported_unpriced_not_charged_zero():
    # A lookup that only matched exactly would silently price an unknown model
    # at zero and print a total that looks fine. Returning None is what lets
    # the report say UNPRICED instead of lying by omission.
    assert cloud_cost.price_for("some-model-that-does-not-exist") is None


def test_a_dated_snapshot_prices_as_its_base_model():
    # Providers serve dated snapshots. Pricing those at zero was the failure
    # this prefix match exists to prevent.
    assert cloud_cost.price_for("claude-opus-5-20260101") == \
        cloud_cost.price_for("claude-opus-5")


def test_prices_carry_the_date_they_were_verified():
    # A price that was right when it was written can stop being true with
    # nothing in the code changing, and it fails silently: every number
    # downstream stays plausible. The date is the only thing that makes the
    # table auditable.
    assert cloud_cost.PRICES_VERIFIED


def test_the_identities_between_pages_hold_against_the_labels():
    # A parser can read two pages each perfectly self-consistently and still
    # contradict itself between them. The 1956 income statement's closing fund
    # figure is the same number as the balance sheet's, and two figures that
    # appear only in prose are caught by nothing else at all.
    truths = {d: json.loads((ROOT / "real" / "pages" / f"{d}.truth.json").read_text())
              for d in DOCS}
    results = reconcile.check_identities(
        ROOT / "real" / "pages" / "cross_checks.json", truths, None)
    assert len(results) == 7, f"7 identities expected, {len(results)} ran"
    broken = [r for r in results if r["status"] != "HOLDS"]
    assert not broken, f"broken: {[r['name'] for r in broken]}"
