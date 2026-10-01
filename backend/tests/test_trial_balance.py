"""Trial balance tests: exact figures, posted-only, and an imbalance that shows.

Two things are being asserted here, and they pull in opposite directions.

The first is ordinary: cumulative debits and credits per account, exact decimal
strings, posted entries only, reversals netting to zero, ``as_of`` bounding the
window, and the same tenant and permission rules the ledger already enforces.

The second is the point of the report. Every journal that the application posts
balances by construction, so a balanced trial balance is the *expected* result
and proves nothing about the code that reports an imbalance. The imbalance path
therefore has to be reached through a state the application would refuse to
create, which is what
:func:`ledger_fixtures.force_unbalanced_posted_entry` does: it writes a posted
entry into the store past the public API, exactly as a bad migration or a
partial import would, without weakening
:func:`src.accounting.validate_journal` for everybody else. Those tests assert
the exact difference in exact decimal strings, because "close enough" is what a
trial balance must never be.

Every test names one rule and states the number it expects, and each fails if
the corresponding guard is removed from :mod:`src.trial_balance`,
:mod:`src.ledger` or :mod:`src.ledger_api`.
"""

from __future__ import annotations

import logging
import sys
import types
from decimal import Decimal

import pytest
from ledger_fixtures import (
    ACCOUNTANT_USER_ID,
    DAY_AFTER,
    DAY_BEFORE,
    DAY_ONE,
    DAY_THREE,
    DAY_TWO,
    ORGANIZATION_ID,
    OUTSIDER_USER_ID,
    STRANGER_USER_ID,
    VIEWER_USER_ID,
    account_id,
    as_accountant,
    draft_entry,
    force_unbalanced_posted_entry,
    get_trial_balance,
    line,
    post_entry,
    post_other_org_entry,
)

from src.trial_balance import (
    AUDIT_ACTION_TRIAL_BALANCE_UNBALANCED,
    TRIAL_BALANCE_UNBALANCED,
)

CASH = "1100"
REVENUE = "4000"
RENT = "5000"


def account_row(trial_balance: dict, account: int) -> dict:
    """The report row for one account, looked up by id."""
    for row in trial_balance["accounts"]:
        if row["account_id"] == account:
            return row
    raise AssertionError(f"account {account} is not in the trial balance")


def install_fake_audit(monkeypatch, captured: list[dict]) -> None:
    """Put a fake ``src.audit`` module in place and collect what is recorded.

    ``report_imbalance`` imports the audit service lazily so the report keeps
    working before that service lands. Stubbing the module is therefore the way
    to exercise the real lazy-import path rather than a mock of this module's
    own internals: what is asserted is the audit row itself.
    """
    module = types.ModuleType("src.audit")

    def record(**kwargs):
        captured.append(kwargs)

    module.record = record
    monkeypatch.setitem(sys.modules, "src.audit", module)


def raise_recorder(**kwargs):
    """An audit sink that fails, to prove the report survives a broken one."""
    raise RuntimeError("audit store is down")


# --------------------------------------------------------------------------
# Balanced case
# --------------------------------------------------------------------------


def test_a_balanced_posting_reports_equal_totals_and_no_error(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The ordinary case: two columns agree, and there is no failure to report."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="1250.75"), line(revenue, credit="1250.75")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["is_balanced"] is True
    assert trial_balance["totals"] == {
        "debit_total": "1250.75",
        "credit_total": "1250.75",
        "difference": "0.00",
    }
    # A balanced report carries no error envelope at all, so a client cannot
    # find a code to act on when there is nothing to act on.
    assert "error" not in trial_balance


def test_each_account_row_carries_code_name_debits_credits_and_balance(
    trial_balance_client, accounting_store, trial_balance_url
):
    """One row per account, with the code and name the chart of accounts uses."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="300.00"), line(revenue, credit="300.00")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)
    cash_row = account_row(trial_balance, cash)

    assert cash_row["account_code"] == "1100"
    assert cash_row["account_name"] == "Cash"
    assert cash_row["account_type"] == "asset"
    assert cash_row["normal_balance"] == "debit"
    assert cash_row["debit_total"] == "300.00"
    assert cash_row["credit_total"] == "0.00"
    assert cash_row["balance"] == "300.00"


def test_a_credit_normal_account_reports_a_positive_balance(
    trial_balance_client, accounting_store, trial_balance_url
):
    """Revenue is credit-normal, so its net balance reads positive.

    A raw ``debit - credit`` for every account would show revenue as a
    permanently negative figure and make every liability look like a loss.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="80.00"), line(revenue, credit="80.00")],
    )

    revenue_row = account_row(
        get_trial_balance(trial_balance_client, trial_balance_url), revenue
    )

    assert revenue_row["normal_balance"] == "credit"
    assert revenue_row["debit_total"] == "0.00"
    assert revenue_row["credit_total"] == "80.00"
    assert revenue_row["balance"] == "80.00"


def test_a_debit_normal_account_with_a_credit_balance_reports_a_negative_balance(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The sign follows the account, so an overdrawn asset is negative."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(revenue, debit="20.00"), line(cash, credit="20.00")],
    )

    cash_row = account_row(
        get_trial_balance(trial_balance_client, trial_balance_url), cash
    )

    assert cash_row["debit_total"] == "0.00"
    assert cash_row["credit_total"] == "20.00"
    assert cash_row["balance"] == "-20.00"


def test_totals_are_the_sum_of_every_account_row(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The totals row is arithmetic, not a second source of truth."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    rent = account_id(accounting_store, RENT)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    post_entry(
        accounting_store,
        "JV-2",
        DAY_TWO,
        [line(cash, debit="0.10"), line(rent, credit="0.10")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert sum(Decimal(row["debit_total"]) for row in trial_balance["accounts"]) == Decimal(
        trial_balance["totals"]["debit_total"]
    )
    assert sum(Decimal(row["credit_total"]) for row in trial_balance["accounts"]) == Decimal(
        trial_balance["totals"]["credit_total"]
    )


# --------------------------------------------------------------------------
# Exact decimals
# --------------------------------------------------------------------------


def test_amounts_that_break_in_floating_point_stay_exact_strings(
    trial_balance_client, accounting_store, trial_balance_url
):
    """0.10 + 0.20 is 0.30 as decimal and 0.30000000000000004 as a float."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="0.10"), line(revenue, credit="0.10")],
    )
    post_entry(
        accounting_store,
        "JV-2",
        DAY_TWO,
        [line(cash, debit="0.20"), line(revenue, credit="0.20")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)
    totals = trial_balance["totals"]

    assert totals["debit_total"] == "0.30"
    assert totals["credit_total"] == "0.30"
    assert totals["difference"] == "0.00"
    for row in trial_balance["accounts"]:
        assert isinstance(row["debit_total"], str)
        assert isinstance(row["credit_total"], str)
        assert isinstance(row["balance"], str)


def test_a_reversal_nets_to_zero_and_never_renders_as_negative_zero(
    trial_balance_client, accounting_store, trial_balance_url
):
    """Both entries stay in the report and cancel out.

    "-0.0000" would read as a real negative balance, so the zero has to render
    as a zero.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    entry_id = post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="1250.75"), line(revenue, credit="1250.75")],
    )
    accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=entry_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    # The reversal is included next to the entry it reverses rather than
    # erasing it, so the two columns carry the same figures and cancel.
    assert account_row(trial_balance, cash)["debit_total"] == "1250.75"
    assert account_row(trial_balance, cash)["credit_total"] == "1250.75"
    assert account_row(trial_balance, cash)["balance"] == "0.00"
    assert account_row(trial_balance, revenue)["balance"] == "0.00"
    assert trial_balance["is_balanced"] is True
    assert trial_balance["totals"]["difference"] == "0.00"


# --------------------------------------------------------------------------
# Posted-only, and the as_of window
# --------------------------------------------------------------------------


def test_a_draft_entry_never_reaches_the_trial_balance(
    trial_balance_client, accounting_store, trial_balance_url
):
    """A draft was never a financial fact, so it contributes nothing."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    draft_entry(
        accounting_store,
        "JV-DRAFT",
        DAY_ONE,
        [line(cash, debit="999.99"), line(revenue, credit="999.99")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["accounts"] == []
    assert trial_balance["totals"]["debit_total"] == "0.00"
    assert trial_balance["is_balanced"] is True


def test_as_of_includes_an_entry_dated_that_day(
    trial_balance_client, accounting_store, trial_balance_url
):
    """`as_of` is inclusive, so an entry dated exactly on it is in the report."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-ON-THE-DAY",
        DAY_TWO,
        [line(cash, debit="60.00"), line(revenue, credit="60.00")],
    )

    trial_balance = get_trial_balance(
        trial_balance_client, trial_balance_url, as_of=DAY_TWO.isoformat()
    )

    assert trial_balance["as_of"] == DAY_TWO.isoformat()
    assert trial_balance["totals"]["debit_total"] == "60.00"


def test_entries_after_as_of_are_excluded(
    trial_balance_client, accounting_store, trial_balance_url
):
    """A report as of a date must not include the future."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-IN",
        DAY_ONE,
        [line(cash, debit="10.00"), line(revenue, credit="10.00")],
    )
    post_entry(
        accounting_store,
        "JV-LATER",
        DAY_AFTER,
        [line(cash, debit="70.00"), line(revenue, credit="70.00")],
    )

    trial_balance = get_trial_balance(
        trial_balance_client, trial_balance_url, as_of=DAY_TWO.isoformat()
    )

    assert trial_balance["totals"]["debit_total"] == "10.00"
    assert account_row(trial_balance, cash)["balance"] == "10.00"


def test_the_report_is_cumulative_rather_than_period_only(
    trial_balance_client, accounting_store, trial_balance_url
):
    """Every posting up to `as_of` is in the columns, not just the last day."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-BEFORE",
        DAY_BEFORE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    post_entry(
        accounting_store,
        "JV-IN",
        DAY_TWO,
        [line(cash, debit="30.00"), line(revenue, credit="30.00")],
    )

    trial_balance = get_trial_balance(
        trial_balance_client, trial_balance_url, as_of=DAY_TWO.isoformat()
    )
    cash_row = account_row(trial_balance, cash)

    assert cash_row["debit_total"] == "130.00"
    assert cash_row["balance"] == "130.00"
    assert trial_balance["totals"]["debit_total"] == "130.00"


def test_an_organization_with_no_postings_reports_zero_totals_and_is_balanced(
    trial_balance_client, trial_balance_url
):
    """No transactions yet is a normal state, not an error."""
    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance == {
        "organization_id": ORGANIZATION_ID,
        "as_of": None,
        "is_balanced": True,
        "totals": {
            "debit_total": "0.00",
            "credit_total": "0.00",
            "difference": "0.00",
        },
        "accounts": [],
    }


def test_an_account_with_no_activity_is_absent_from_the_report(
    trial_balance_client, accounting_store, trial_balance_url
):
    """An untouched account would only add a row of zeros."""
    rent = account_id(accounting_store, RENT)
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="15.00"), line(revenue, credit="15.00")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert rent not in [row["account_id"] for row in trial_balance["accounts"]]


# --------------------------------------------------------------------------
# The imbalance itself
# --------------------------------------------------------------------------


def test_an_unbalanced_ledger_is_reported_with_the_exact_difference(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The whole point: a broken ledger says so, and by how much.

    The forced entry is a one-cent debit with nothing on the other side, on top
    of a perfectly balanced posting. Posting validation still refuses it; the
    report has to cope with it existing.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="1250.75"), line(revenue, credit="1250.75")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_TWO,
        [line(cash, debit="0.05")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["is_balanced"] is False
    assert trial_balance["totals"] == {
        "debit_total": "1250.80",
        "credit_total": "1250.75",
        "difference": "0.05",
    }
    assert trial_balance["error"]["code"] == TRIAL_BALANCE_UNBALANCED
    assert trial_balance["error"]["details"] == {
        "organization_id": "1",
        "as_of": "",
        "debit_total": "1250.80",
        "credit_total": "1250.75",
        "difference": "0.05",
    }


def test_the_response_is_returned_with_the_imbalance_flag_not_as_a_failure(
    trial_balance_client, accounting_store, trial_balance_url
):
    """200 with the figures, not a bare error the operator cannot act on.

    The discrepancy is the most useful thing in the response, so throwing the
    report away to signal it would leave a client with a code and nothing to
    investigate.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_ONE,
        [line(revenue, debit="7.00")],
    )

    response = trial_balance_client.get(
        trial_balance_url, headers=as_accountant()
    )

    assert response.status_code == 200
    assert response.json()["is_balanced"] is False
    assert response.json()["totals"]["difference"] == "7.00"


def test_the_imbalance_is_never_corrected_away(
    trial_balance_client, accounting_store, trial_balance_url
):
    """No side is nudged to make the columns look equal.

    The per-account row still carries the real figures, and the difference is
    exactly the gap between them: any "fix" that adjusted a total would show up
    here as a row that no longer matches the entry that was posted.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_ONE,
        [line(cash, debit="0.0001")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)
    cash_row = account_row(trial_balance, cash)

    # The smallest amount the money scale stores is still a difference, not a
    # rounding error to be swallowed into "0.00".
    assert cash_row["debit_total"] == "100.0001"
    assert trial_balance["totals"]["difference"] == "0.0001"
    assert trial_balance["error"]["details"]["difference"] == "0.0001"
    assert (
        Decimal(trial_balance["totals"]["debit_total"])
        - Decimal(trial_balance["totals"]["credit_total"])
        == Decimal(trial_balance["totals"]["difference"])
    )


def test_an_imbalance_after_as_of_is_out_of_the_report(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The window bounds the damage as well as the figures."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-LATER-CORRUPT",
        DAY_AFTER,
        [line(cash, debit="5.00")],
    )

    before = get_trial_balance(
        trial_balance_client, trial_balance_url, as_of=DAY_TWO.isoformat()
    )
    after = get_trial_balance(
        trial_balance_client, trial_balance_url, as_of=DAY_AFTER.isoformat()
    )

    assert before["is_balanced"] is True
    assert "error" not in before
    assert after["is_balanced"] is False
    assert after["totals"]["difference"] == "5.00"
    assert after["error"]["details"]["as_of"] == DAY_AFTER.isoformat()


def test_a_balanced_report_is_never_logged_as_an_imbalance(
    trial_balance_client, accounting_store, trial_balance_url, caplog
):
    """A clean report must stay silent, or the log stops meaning anything."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="10.00"), line(revenue, credit="10.00")],
    )

    with caplog.at_level(logging.WARNING, logger="dina.trial_balance"):
        trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["is_balanced"] is True
    assert caplog.records == []


def test_the_imbalance_is_logged_with_the_exact_figures(
    trial_balance_client, accounting_store, trial_balance_url, caplog
):
    """Somebody has to find out even if nobody opens the report."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_THREE,
        [line(cash, debit="3.25")],
    )

    with caplog.at_level(logging.WARNING, logger="dina.trial_balance"):
        get_trial_balance(
            trial_balance_client, trial_balance_url, as_of=DAY_THREE.isoformat()
        )

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert TRIAL_BALANCE_UNBALANCED in messages[0]
    assert "difference=3.25" in messages[0]
    assert "debit_total=103.25" in messages[0]
    assert "credit_total=100.00" in messages[0]


def test_the_imbalance_is_audited_with_the_exact_figures(
    trial_balance_client, accounting_store, trial_balance_url, monkeypatch
):
    """The audit trail records the event, not just the response."""
    captured: list[dict] = []
    install_fake_audit(monkeypatch, captured)
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_ONE,
        [line(cash, debit="0.05")],
    )

    get_trial_balance(trial_balance_client, trial_balance_url)

    assert len(captured) == 1
    entry = captured[0]
    assert entry["action"] == AUDIT_ACTION_TRIAL_BALANCE_UNBALANCED
    assert entry["organization_id"] == ORGANIZATION_ID
    # The caller's id is what makes the audit row attributable.
    assert entry["user_id"] == ACCOUNTANT_USER_ID
    assert entry["metadata"]["difference"] == "0.05"
    assert entry["metadata"]["debit_total"] == "100.05"
    assert entry["metadata"]["credit_total"] == "100.00"


def test_a_broken_audit_sink_does_not_hide_the_imbalance(
    trial_balance_client, accounting_store, trial_balance_url, monkeypatch
):
    """A failing audit store is not a licence to swallow the discrepancy.

    The report still comes back, still says ``is_balanced: false`` and still
    carries the exact difference; the audit failure is logged instead.
    """
    monkeypatch.setitem(
        sys.modules, "src.audit", types.SimpleNamespace(record=raise_recorder)
    )
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-CORRUPT",
        DAY_ONE,
        [line(cash, debit="1.00")],
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["is_balanced"] is False
    assert trial_balance["totals"]["difference"] == "1.00"
    assert trial_balance["error"]["code"] == TRIAL_BALANCE_UNBALANCED


# --------------------------------------------------------------------------
# Tenant isolation
# --------------------------------------------------------------------------


def test_another_tenants_postings_never_reach_the_report(
    trial_balance_client, accounting_store, trial_balance_url
):
    """Org 2's money must not appear in org 1's trial balance in any form."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-OWN",
        DAY_ONE,
        [line(cash, debit="42.00"), line(revenue, credit="42.00")],
    )
    post_other_org_entry(accounting_store, "JV-THEIRS", DAY_ONE, "5000.00")

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["totals"]["debit_total"] == "42.00"
    assert "5000" not in str(trial_balance)


def test_another_tenants_imbalance_does_not_unbalance_this_one(
    trial_balance_client, accounting_store, trial_balance_url
):
    """The other tenant's corruption is theirs to fix, not ours to report."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-OWN",
        DAY_ONE,
        [line(cash, debit="42.00"), line(revenue, credit="42.00")],
    )
    force_unbalanced_posted_entry(
        accounting_store,
        "JV-THEIR-CORRUPT",
        DAY_ONE,
        [line(cash, debit="900.00")],
        organization_id=2,
    )

    trial_balance = get_trial_balance(trial_balance_client, trial_balance_url)

    assert trial_balance["is_balanced"] is True
    assert trial_balance["totals"] == {
        "debit_total": "42.00",
        "credit_total": "42.00",
        "difference": "0.00",
    }


def test_a_non_member_cannot_read_another_tenants_trial_balance(
    trial_balance_client, trial_balance_url
):
    """An accountant of org 2 is still a stranger to org 1."""
    response = trial_balance_client.get(
        trial_balance_url, headers=as_accountant(OUTSIDER_USER_ID)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"


def test_an_unknown_organization_is_reported_as_not_found(trial_balance_client):
    """Asking for an organization that does not exist is a 404, not a leak."""
    response = trial_balance_client.get(
        "/api/v1/organizations/999/trial-balance", headers=as_accountant()
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "organization_not_found"


# --------------------------------------------------------------------------
# Permission and authentication
# --------------------------------------------------------------------------


def test_a_viewer_may_not_read_the_trial_balance(
    trial_balance_client, trial_balance_url
):
    """The trial balance is above the read-only reporting a viewer is granted."""
    response = trial_balance_client.get(
        trial_balance_url, headers=as_accountant(VIEWER_USER_ID)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize("role", ["accountant", "manager", "owner"])
def test_accounting_roles_and_above_may_read_the_trial_balance(
    trial_balance_url, client_as, role
):
    """The threshold is inclusive and every role at or above it is served."""
    test_client = client_as(role)
    try:
        response = test_client.get(trial_balance_url, headers=as_accountant())
    finally:
        test_client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.json()["is_balanced"] is True


@pytest.mark.parametrize("role", ["viewer", "sales", "warehouse", "superuser"])
def test_roles_below_accounting_may_not_read_the_trial_balance(
    trial_balance_url, client_as, role
):
    """Sales and warehouse sit below accountant; an unknown role fails closed."""
    test_client = client_as(role)
    try:
        response = test_client.get(trial_balance_url, headers=as_accountant())
    finally:
        test_client.__exit__(None, None, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_an_unauthenticated_request_is_refused(
    trial_balance_client, trial_balance_url
):
    """No identity means no report, even for a real organization."""
    response = trial_balance_client.get(trial_balance_url)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_a_non_numeric_identity_is_refused(
    trial_balance_client, trial_balance_url
):
    """A malformed header is an authentication failure, not a default user."""
    response = trial_balance_client.get(
        trial_balance_url, headers={"X-User-Id": "not-a-number"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_a_user_with_no_memberships_is_refused(
    trial_balance_client, trial_balance_url
):
    """Being a real user is not the same as being a member of this tenant."""
    response = trial_balance_client.get(
        trial_balance_url, headers=as_accountant(STRANGER_USER_ID)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"
