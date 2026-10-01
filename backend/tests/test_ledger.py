"""Ledger tests: exact arithmetic, posted-only, reversals, tenancy, permission.

Every amount assertion here compares decimal *strings* such as ``"1250.75"``.
Comparing floats would defeat the point of the exercise: ``0.1 + 0.2 != 0.3``
in binary floating point, so a float assertion has to be written with a
tolerance, and a tolerance is exactly the slack that hides a real bug. The
strings are what the API returns and what a client ledger screen renders, so
asserting on them tests the actual contract.

Each test names one rule and states the number it expects. They are written so
that deleting the corresponding guard in :mod:`src.ledger`,
:mod:`src.accounting_store`, :mod:`src.permissions` or :mod:`src.identity`
makes the test fail rather than pass vacuously.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from ledger_fixtures import (
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
    account_report,
    as_accountant,
    draft_entry,
    get_ledger,
    line,
    other_org_account_id,
    post_entry,
    post_other_org_entry,
)

CASH = "1100"
REVENUE = "4000"
RENT = "5000"


# --------------------------------------------------------------------------
# Drafts are invisible; posted entries are visible
# --------------------------------------------------------------------------


def test_draft_entry_never_appears_in_the_ledger(
    ledger_client, accounting_store, ledger_url
):
    """A draft was never a financial fact, so it contributes nothing."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    draft_entry(
        accounting_store,
        "JV-DRAFT",
        DAY_ONE,
        [line(cash, debit="1250.75"), line(revenue, credit="1250.75")],
        description="never approved",
    )

    ledger = get_ledger(ledger_client, ledger_url)

    assert ledger["accounts"] == []
    assert ledger["period_debit_total"] == "0.00"
    assert ledger["period_credit_total"] == "0.00"
    assert ledger["is_balanced"] is True


def test_posted_entry_is_included_with_its_exact_amounts(
    ledger_client, accounting_store, ledger_url
):
    """A posted entry shows up with the exact figures it was posted with."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(cash, debit="1250.75"), line(revenue, credit="1250.75")],
        description="cash sale",
    )

    ledger = get_ledger(ledger_client, ledger_url)

    cash_report = account_report(ledger, cash)
    assert cash_report["opening_balance"] == "0.00"
    assert cash_report["period_debit_total"] == "1250.75"
    assert cash_report["period_credit_total"] == "0.00"
    assert cash_report["closing_balance"] == "1250.75"

    revenue_report = account_report(ledger, revenue)
    assert revenue_report["period_credit_total"] == "1250.75"
    # Revenue is credit-normal, so its balance reads positive despite the fact
    # that the money arrived as a credit.
    assert revenue_report["closing_balance"] == "1250.75"
    assert revenue_report["normal_balance"] == "credit"


def test_draft_and_posted_entries_in_the_same_period_ignore_only_the_draft(
    ledger_client, accounting_store, ledger_url
):
    """One draft alongside one posted entry changes nothing about the balance."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="1250.75"), line(revenue, credit="1250.75")]
    )
    draft_entry(
        accounting_store, "JV-DRAFT", DAY_ONE, [line(cash, debit="999.99"), line(revenue, credit="999.99")]
    )

    ledger = get_ledger(ledger_client, ledger_url)

    assert account_report(ledger, cash)["closing_balance"] == "1250.75"
    assert ledger["period_debit_total"] == "1250.75"
    # The draft is not merely excluded from the totals; it is absent from the
    # report, so no client can render it by accident.
    assert len(account_report(ledger, cash)["movements"]) == 1


# --------------------------------------------------------------------------
# Reversal
# --------------------------------------------------------------------------


def test_reversal_nets_to_zero_and_keeps_both_entries_visible(
    ledger_client, accounting_store, ledger_url
):
    """A reversal must cancel out without erasing what it reversed."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    original_id = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="1250.75"), line(revenue, credit="1250.75")]
    )
    accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=original_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )

    ledger = get_ledger(ledger_client, ledger_url)

    cash_report = account_report(ledger, cash)
    # Both entries are present and they cancel.
    assert [m["entry_id"] for m in cash_report["movements"]] == [original_id, original_id + 1]
    assert cash_report["closing_balance"] == "0.00"
    assert cash_report["period_debit_total"] == "1250.75"
    assert cash_report["period_credit_total"] == "1250.75"
    assert account_report(ledger, revenue)["closing_balance"] == "0.00"
    assert ledger["is_balanced"] is True


def test_reversed_entry_keeps_its_original_lines_untouched(
    ledger_client, accounting_store, ledger_url
):
    """The original keeps its amount; the reversing entry is its mirror image."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    original_id = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="400.00"), line(revenue, credit="400.00")]
    )
    accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=original_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )

    movements = account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]

    original, reversal = movements
    assert (original["debit"], original["credit"]) == ("400.00", "0.00")
    assert (reversal["debit"], reversal["credit"]) == ("0.00", "400.00")
    # The running balance returns to where it started.
    assert original["running_balance"] == "400.00"
    assert reversal["running_balance"] == "0.00"


def test_a_draft_entry_cannot_be_reversed(
    ledger_client, accounting_store, ledger_url
):
    """Reversal undoes a posting. There is nothing to undo in a draft."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    draft = draft_entry(
        accounting_store, "JV-DRAFT", DAY_ONE, [line(cash, debit="50.00"), line(revenue, credit="50.00")]
    )

    with pytest.raises(Exception) as raised:
        accounting_store.reverse_entry(
            organization_id=ORGANIZATION_ID,
            entry_id=draft,
            document_no="JV-DRAFT-REV",
            entry_date=DAY_TWO,
        )

    assert getattr(raised.value, "code", "") == "journal_not_reversible"
    # Nothing was written: the failed reversal left no trace in the ledger.
    assert get_ledger(ledger_client, ledger_url)["accounts"] == []


def test_an_entry_cannot_be_reversed_twice(
    ledger_client, accounting_store, ledger_url
):
    """A second reversal would double the correction and leave the books wrong."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    original_id = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="75.00"), line(revenue, credit="75.00")]
    )
    accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=original_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )

    with pytest.raises(Exception) as raised:
        accounting_store.reverse_entry(
            organization_id=ORGANIZATION_ID,
            entry_id=original_id,
            document_no="JV-1-REV-2",
            entry_date=DAY_THREE,
        )

    assert getattr(raised.value, "code", "") == "entry_already_reversed"
    # Still exactly one original and one reversal.
    assert len(account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]) == 2


def test_a_reversal_rejected_by_the_store_leaves_the_original_posted(
    ledger_client, accounting_store, ledger_url
):
    """A failed reversal must not half-apply.

    `document_no` collides with an existing entry, so `add_entry` refuses the
    mirror. If the original had already been flipped to `reversed` first, it
    would be left marked reversed with nothing behind it — and the retry would
    then fail as `journal_not_reversible`, a state the caller cannot get out of.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    original_id = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="75.00"), line(revenue, credit="75.00")]
    )
    post_entry(
        accounting_store, "JV-TAKEN", DAY_ONE, [line(cash, debit="5.00"), line(revenue, credit="5.00")]
    )

    with pytest.raises(Exception) as raised:
        accounting_store.reverse_entry(
            organization_id=ORGANIZATION_ID,
            entry_id=original_id,
            document_no="JV-TAKEN",  # already in use
            entry_date=DAY_TWO,
        )

    assert getattr(raised.value, "code", "") == "document_no_conflict"
    # Still posted, still reversible, and no half-written mirror in the ledger.
    assert accounting_store.get_entry(ORGANIZATION_ID, original_id).status == "posted"
    assert [m["entry_id"] for m in account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]] == [
        original_id,
        original_id + 1,
    ]

    # The legitimate retry now succeeds, which is the point of not corrupting the
    # original: `journal_not_reversible` would be raised instead.
    reversing = accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=original_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )
    assert reversing.reversal_of_entry_id == original_id
    assert accounting_store.get_entry(ORGANIZATION_ID, original_id).status == "reversed"


# --------------------------------------------------------------------------
# Running balance ordering
# --------------------------------------------------------------------------


def test_running_balance_steps_through_entries_in_entry_then_line_order(
    ledger_client, accounting_store, ledger_url
):
    """The running total is reproducible because the order is total."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    rent = account_id(accounting_store, RENT)
    first = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="100.00"), line(revenue, credit="100.00")]
    )
    second = post_entry(
        accounting_store, "JV-2", DAY_TWO, [line(cash, debit="25.50"), line(rent, credit="25.50")]
    )
    third = post_entry(
        accounting_store, "JV-3", DAY_THREE, [line(cash, debit="0.25"), line(rent, credit="0.25")]
    )

    movements = account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]

    assert [m["entry_id"] for m in movements] == [first, second, third]
    assert [m["line_no"] for m in movements] == [1, 1, 1]
    assert [m["running_balance"] for m in movements] == ["100.00", "125.50", "125.75"]


def test_two_lines_on_one_account_in_one_entry_step_by_line_number(
    ledger_client, accounting_store, ledger_url
):
    """Within one entry the line number is the tiebreak, not the entry id."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [
            line(cash, debit="10.00"),
            line(cash, debit="20.00"),
            line(revenue, credit="30.00"),
        ],
    )

    movements = account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]

    assert [m["line_no"] for m in movements] == [1, 2]
    assert [m["running_balance"] for m in movements] == ["10.00", "30.00"]


def test_entry_id_outranks_line_number_when_the_two_disagree(
    ledger_client, accounting_store, ledger_url
):
    """Entry id is the primary key of the order; line no only breaks ties.

    The first entry is given a *higher* line number than the second, so an
    implementation that sorted on line number alone would step these two
    movements in the opposite order and produce different running balances.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    first = post_entry(
        accounting_store,
        "JV-1",
        DAY_ONE,
        [line(revenue, credit="5.00"), line(cash, debit="5.00")],
    )
    second = post_entry(
        accounting_store,
        "JV-2",
        DAY_TWO,
        [line(cash, debit="5.00"), line(revenue, credit="5.00")],
    )

    movements = account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]

    # Cash is line 2 of the first entry and line 1 of the second.
    assert [m["line_no"] for m in movements] == [2, 1]
    assert [m["entry_id"] for m in movements] == [first, second]
    assert [m["running_balance"] for m in movements] == ["5.00", "10.00"]


def test_running_balance_is_stable_across_repeated_requests(
    ledger_client, accounting_store, ledger_url
):
    """The same data must produce the same sequence, every time it is asked."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    for index in range(1, 6):
        post_entry(
            accounting_store,
            f"JV-{index}",
            date(2026, 3, index),
            [line(cash, debit="10.00"), line(revenue, credit="10.00")],
        )

    first = get_ledger(ledger_client, ledger_url)
    second = get_ledger(ledger_client, ledger_url)

    assert first == second
    assert [
        m["running_balance"] for m in account_report(first, cash)["movements"]
    ] == ["10.00", "20.00", "30.00", "40.00", "50.00"]


# --------------------------------------------------------------------------
# Exact decimal arithmetic
# --------------------------------------------------------------------------


def test_amounts_that_break_in_binary_floating_point_stay_exact(
    ledger_client, accounting_store, ledger_url
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

    ledger = get_ledger(ledger_client, ledger_url)

    assert account_report(ledger, cash)["closing_balance"] == "0.30"
    assert ledger["period_debit_total"] == "0.30"
    assert Decimal(ledger["net_movement"]) == Decimal("0")


def test_amounts_are_serialised_as_strings_never_as_json_numbers(
    ledger_client, accounting_store, ledger_url
):
    """A JSON number would round-trip through a binary float in most clients."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="1250.75"), line(revenue, credit="1250.75")]
    )

    ledger = get_ledger(ledger_client, ledger_url)
    report = account_report(ledger, cash)

    assert report["closing_balance"] == "1250.75"
    assert isinstance(report["closing_balance"], str)
    assert report["movements"][0]["debit"] == "1250.75"
    assert ledger["period_debit_total"] == "1250.75"


def test_a_zero_balance_never_renders_as_negative_zero(
    ledger_client, accounting_store, ledger_url
):
    """A reversal nets to zero; "-0.0000" would read as a real negative amount."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    entry_id = post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="10.00"), line(revenue, credit="10.00")]
    )
    accounting_store.reverse_entry(
        organization_id=ORGANIZATION_ID,
        entry_id=entry_id,
        document_no="JV-1-REV",
        entry_date=DAY_TWO,
    )

    report = account_report(get_ledger(ledger_client, ledger_url), cash)

    assert report["closing_balance"] == "0.00"
    assert report["movements"][-1]["running_balance"] == "0.00"


# --------------------------------------------------------------------------
# Period filters
# --------------------------------------------------------------------------


def test_date_range_reports_opening_debit_credit_and_closing_balances(
    ledger_client, accounting_store, ledger_url
):
    """The opening balance is the history before the period; closing is after."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store,
        "JV-BEFORE",
        DAY_BEFORE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    post_entry(
        accounting_store, "JV-IN", DAY_TWO, [line(cash, debit="30.00"), line(revenue, credit="30.00")]
    )

    ledger = get_ledger(
        ledger_client, ledger_url, date_from=DAY_ONE.isoformat(), date_to=DAY_TWO.isoformat()
    )
    report = account_report(ledger, cash)

    assert report["opening_balance"] == "100.00"
    assert report["period_debit_total"] == "30.00"
    assert report["period_credit_total"] == "0.00"
    assert report["closing_balance"] == "130.00"
    # Only the period's own line appears; the earlier one became the opening.
    assert [m["document_no"] for m in report["movements"]] == ["JV-IN"]


def test_a_backdated_entry_posted_after_the_period_does_not_reset_the_running_balance(
    ledger_client, accounting_store, ledger_url
):
    """A late-posted backdated journal is history, not a reset of the period.

    `JV-LATE` (in-period) is posted first and therefore has the lower id;
    `JV-BACKDATED` is posted afterwards for a date before the period opens, so it
    has the *higher* id. Lines are walked in `(entry id, line no)` order but
    pre-period-ness is a property of the date, so the backdated line is reached
    after the period line. If the opening balance is folded in as the walk goes,
    the running balance is overwritten and the period's movement is lost.

    The three numbers below have to agree with each other: opening + period
    movement = closing, and the last running balance = closing.
    """
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-LATE", DAY_TWO, [line(cash, debit="100.00"), line(revenue, credit="100.00")]
    )
    post_entry(
        accounting_store,
        "JV-BACKDATED",
        DAY_BEFORE,
        [line(cash, debit="50.00"), line(revenue, credit="50.00")],
    )

    report = account_report(
        get_ledger(
            ledger_client,
            ledger_url,
            date_from=DAY_ONE.isoformat(),
            date_to=DAY_TWO.isoformat(),
        ),
        cash,
    )

    assert report["opening_balance"] == "50.00"
    assert report["period_debit_total"] == "100.00"
    assert report["closing_balance"] == "150.00"
    # The period's single movement carries the opening figure too, because it is
    # where the running balance is seeded.
    assert [m["document_no"] for m in report["movements"]] == ["JV-LATE"]
    assert report["movements"][-1]["running_balance"] == "150.00"


def test_a_backdated_entry_and_a_later_one_still_step_in_entry_id_order(
    ledger_client, accounting_store, ledger_url
):
    """Canonical order is `(entry id, line no)` even when the dates disagree."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    first = post_entry(
        accounting_store, "JV-1", DAY_TWO, [line(cash, debit="10.00"), line(revenue, credit="10.00")]
    )
    post_entry(
        accounting_store, "JV-2", DAY_TWO, [line(cash, debit="20.00"), line(revenue, credit="20.00")]
    )
    post_entry(
        accounting_store, "JV-BACKDATED", DAY_BEFORE, [line(cash, debit="5.00"), line(revenue, credit="5.00")]
    )

    report = account_report(
        get_ledger(
            ledger_client,
            ledger_url,
            date_from=DAY_ONE.isoformat(),
            date_to=DAY_TWO.isoformat(),
        ),
        cash,
    )

    # Id order, not date order: the backdated entry is the opening figure even
    # though it was posted last, and it is not stepped as a movement.
    assert report["opening_balance"] == "5.00"
    assert [m["entry_id"] for m in report["movements"]] == [first, first + 1]
    assert [m["running_balance"] for m in report["movements"]] == ["15.00", "35.00"]
    assert report["closing_balance"] == "35.00"


def test_entries_after_the_period_are_excluded(ledger_client, accounting_store, ledger_url):
    """A period report must not include the future."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-IN", DAY_ONE, [line(cash, debit="10.00"), line(revenue, credit="10.00")]
    )
    post_entry(
        accounting_store, "JV-LATER", DAY_AFTER, [line(cash, debit="70.00"), line(revenue, credit="70.00")]
    )

    ledger = get_ledger(
        ledger_client, ledger_url, date_from=DAY_ONE.isoformat(), date_to=DAY_TWO.isoformat()
    )

    assert account_report(ledger, cash)["closing_balance"] == "10.00"


def test_account_filter_restricts_the_report_to_one_account(
    ledger_client, accounting_store, ledger_url
):
    """Filtering by account must not change the other accounts' arithmetic."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="60.00"), line(revenue, credit="60.00")]
    )

    ledger = get_ledger(ledger_client, ledger_url, account_id=cash)

    assert [a["account_id"] for a in ledger["accounts"]] == [cash]
    assert ledger["accounts"][0]["closing_balance"] == "60.00"
    # The report's totals follow the filter, not the whole ledger.
    assert ledger["period_debit_total"] == "60.00"
    assert ledger["period_credit_total"] == "0.00"


def test_entry_reference_filter_narrows_the_report_to_one_entry(
    ledger_client, accounting_store, ledger_url
):
    """Either an entry id or a document number selects a single entry."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="11.00"), line(revenue, credit="11.00")]
    )
    wanted = post_entry(
        accounting_store, "JV-2", DAY_TWO, [line(cash, debit="22.00"), line(revenue, credit="22.00")]
    )

    by_id = get_ledger(ledger_client, ledger_url, entry_id=wanted)
    by_document = get_ledger(ledger_client, ledger_url, document_no="JV-2")

    assert account_report(by_id, cash)["closing_balance"] == "22.00"
    assert account_report(by_document, cash)["closing_balance"] == "22.00"
    assert [m["entry_id"] for m in account_report(by_id, cash)["movements"]] == [wanted]


def test_an_entry_that_matches_no_filter_is_an_empty_report_not_an_error(
    ledger_client, accounting_store, ledger_url
):
    """A filter that legitimately matches nothing returns zero totals."""
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="5.00"), line(revenue, credit="5.00")]
    )

    ledger = get_ledger(ledger_client, ledger_url, document_no="JV-DOES-NOT-EXIST")

    assert ledger["accounts"] == []
    assert ledger["period_debit_total"] == "0.00"


# --------------------------------------------------------------------------
# Empty ledger
# --------------------------------------------------------------------------


def test_organization_with_no_posted_entries_returns_an_empty_report(
    ledger_client, ledger_url
):
    """No transactions yet is a normal state, not an error."""
    response = ledger_client.get(ledger_url, headers=as_accountant())

    assert response.status_code == 200
    ledger = response.json()
    assert ledger == {
        "organization_id": ORGANIZATION_ID,
        "period_debit_total": "0.00",
        "period_credit_total": "0.00",
        "net_movement": "0.00",
        "is_balanced": True,
        "accounts": [],
    }


def test_an_account_with_no_activity_is_absent_from_the_report(
    ledger_client, accounting_store, ledger_url
):
    """An untouched account would only add a row of zeros."""
    rent = account_id(accounting_store, RENT)
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-1", DAY_ONE, [line(cash, debit="15.00"), line(revenue, credit="15.00")]
    )

    ledger = get_ledger(ledger_client, ledger_url)

    assert rent not in [a["account_id"] for a in ledger["accounts"]]


# --------------------------------------------------------------------------
# Tenant isolation
# --------------------------------------------------------------------------


def test_an_account_id_from_another_organization_is_refused(
    ledger_client, accounting_store, ledger_url
):
    """A foreign account id must be rejected, never silently summed in."""
    foreign = other_org_account_id(accounting_store)

    response = ledger_client.get(
        ledger_url, headers=as_accountant(), params={"account_id": foreign}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "account_not_found"


def test_an_entry_id_from_another_organization_is_refused(
    ledger_client, accounting_store, ledger_url
):
    """A foreign entry id must be rejected as well."""
    foreign_entry = post_other_org_entry(
        accounting_store, "JV-FOREIGN", DAY_ONE, "1000.00"
    )

    response = ledger_client.get(
        ledger_url, headers=as_accountant(), params={"entry_id": foreign_entry}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "journal_not_found"


def test_another_tenants_postings_never_reach_the_report(
    ledger_client, accounting_store, ledger_url
):
    """Org 2's money must not appear in org 1's ledger in any form."""
    org2_cash = other_org_account_id(accounting_store)
    cash = account_id(accounting_store, CASH)
    revenue = account_id(accounting_store, REVENUE)
    post_entry(
        accounting_store, "JV-OWN", DAY_ONE, [line(cash, debit="42.00"), line(revenue, credit="42.00")]
    )
    post_other_org_entry(accounting_store, "JV-THEIRS", DAY_ONE, "5000.00")

    ledger = get_ledger(ledger_client, ledger_url)

    assert ledger["period_debit_total"] == "42.00"
    assert org2_cash not in [a["account_id"] for a in ledger["accounts"]]
    assert all(
        "5000" not in movement["debit"]
        for report in ledger["accounts"]
        for movement in report["movements"]
    )


def test_a_non_member_cannot_read_another_tenants_ledger(ledger_client, ledger_url):
    """An accountant of org 2 is still a stranger to org 1.

    403, not 401: the identity was accepted, and what is missing is a
    membership. Telling a logged-in user to log in again is the wrong
    instruction.
    """
    response = ledger_client.get(
        f"/api/v1/organizations/{ORGANIZATION_ID}/ledger",
        headers=as_accountant(OUTSIDER_USER_ID),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "not_a_member"


def test_an_unknown_organization_is_reported_as_not_found(ledger_client):
    """Asking for an organization that does not exist is a 404, not a leak."""
    response = ledger_client.get(
        "/api/v1/organizations/999/ledger", headers=as_accountant()
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "organization_not_found"


# --------------------------------------------------------------------------
# Permission
# --------------------------------------------------------------------------


def test_a_viewer_may_not_read_the_ledger(ledger_client, ledger_url):
    """The ledger is above the read-only reporting a viewer is granted."""
    response = ledger_client.get(ledger_url, headers=as_accountant(VIEWER_USER_ID))

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


@pytest.mark.parametrize("role", ["accountant", "manager", "owner"])
def test_accounting_roles_and_above_may_read_the_ledger(ledger_url, client_as, role):
    """The threshold is inclusive and every role at or above it is served."""
    test_client = client_as(role)
    try:
        response = test_client.get(ledger_url, headers=as_accountant())
    finally:
        test_client.__exit__(None, None, None)

    assert response.status_code == 200


@pytest.mark.parametrize("role", ["viewer", "sales", "warehouse"])
def test_roles_below_accounting_may_not_read_the_ledger(ledger_url, client_as, role):
    """Sales and warehouse sit below accountant, so the ledger is closed to them."""
    test_client = client_as(role)
    try:
        response = test_client.get(ledger_url, headers=as_accountant())
    finally:
        test_client.__exit__(None, None, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


def test_an_unknown_role_is_treated_as_unprivileged(ledger_url, client_as):
    """A stale or misspelled role must fail closed, never open."""
    test_client = client_as("superuser")
    try:
        response = test_client.get(ledger_url, headers=as_accountant())
    finally:
        test_client.__exit__(None, None, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


def test_an_unauthenticated_request_is_refused(ledger_client, ledger_url):
    """No identity means no ledger, even for a real organization."""
    response = ledger_client.get(ledger_url)

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_a_non_numeric_identity_is_refused(ledger_client, ledger_url):
    """A malformed header is an authentication failure, not a default user."""
    response = ledger_client.get(ledger_url, headers={"X-User-Id": "not-a-number"})

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_a_user_with_no_memberships_is_refused(ledger_client, ledger_url):
    """Being a real user is not the same as being a member of this tenant."""
    response = ledger_client.get(ledger_url, headers=as_accountant(STRANGER_USER_ID))

    assert response.status_code == 403
    assert response.json()["detail"] == "not_a_member"