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


def test_the_cost_report_prices_each_side_at_its_rate_and_names_what_it_cannot_price(tmp_path, capsys):
    # Input and output tokens have different prices, the total is only as good
    # as the sum behind it, and a model with no price on file has to be named
    # rather than folded into the total as free. One million input tokens and
    # one hundred thousand output tokens make each side of the price visible.
    rows = [
        {"doc_id": "a", "dpi": 300, "model": "claude-opus-5",
         "input_tokens": 1_000_000, "output_tokens": 100_000},
        {"doc_id": "b", "dpi": 300, "model": "no-such-model",
         "input_tokens": 10, "output_tokens": 10},
    ]
    (tmp_path / "usage.json").write_text(json.dumps(rows))
    got = cloud_cost.report(tmp_path)
    price_in, price_out = cloud_cost.PRICES["claude-opus-5"]
    assert price_in != price_out, "the check needs two different rates"
    assert got["cost_usd"] == round(price_in + 0.1 * price_out, 4)
    assert got["pages"] == 2
    assert got["unpriced"] == ["no-such-model"]
    assert "no price on file for 'no-such-model'" in capsys.readouterr().out


def test_all_reads_every_run_directory_that_has_usage_records(capsys, monkeypatch):
    # `cloud_cost.py --all` is the command given for the cost of every run, so
    # it has to report each run directory under out*/ that holds usage
    # records, the real-document runs included.
    want = sorted(str(p.parent) for p in ROOT.glob("out*/*/usage.json"))
    assert want, "no run directory holds usage.json, so nothing was examined"
    monkeypatch.setattr(sys, "argv", ["cloud_cost.py", "--all"])
    assert cloud_cost.main() == 0
    printed = capsys.readouterr().out
    missing = [d for d in want if d not in printed]
    assert not missing, f"--all did not report {missing}"


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


def test_an_empty_usage_record_is_reported_and_fails_the_exit_code(
        tmp_path, monkeypatch, capsys):
    # A run in which every page failed before finish() recorded anything
    # leaves an empty list. Left out of --all, the total looks complete.
    run = tmp_path / "out" / "x"
    run.mkdir(parents=True)
    (run / "usage.json").write_text("[]")
    monkeypatch.setattr(sys, "argv", ["cloud_cost.py", str(run)])
    assert cloud_cost.main() == 1
    out = capsys.readouterr().out
    assert str(run) in out and "EMPTY" in out, out


def test_a_price_prefix_matches_only_a_dated_id():
    """A bare prefix priced a different model as its namesake."""
    assert cloud_cost.price_for("gpt-5.4-mini") is None
    assert cloud_cost.price_for("claude-opus-50") is None
    assert cloud_cost.price_for("gpt-5.6-sol-2026-08-01") == \
        cloud_cost.price_for("gpt-5.6-sol")


def test_an_unpriced_run_is_kept_out_of_the_total_and_fails_the_exit_code(
        tmp_path, monkeypatch, capsys):
    run = tmp_path / "out" / "x"
    run.mkdir(parents=True)
    (run / "usage.json").write_text(json.dumps([
        {"doc_id": "d", "dpi": 300, "model": "no-such-model",
         "input_tokens": 1000, "output_tokens": 1000, "stop": "end_turn"}]))
    monkeypatch.setattr(sys, "argv", ["cloud_cost.py", str(run)])
    assert cloud_cost.main() == 1
    out = capsys.readouterr().out
    assert "not in the cost" in out and "counted as $0.00" not in out
