"""The accounting domain test matrix, one named test per required case.

This file exists to make the matrix auditable in one place. Every case the spec
asks for has exactly one test here with the name of the property it protects, so
a reader can go down the list, find the test, and see what breaks when a guard is
removed. That is a different job from ``test_ledger.py`` and
``test_trial_balance.py``, which explore those two reports property by property
and in far more depth; where the two overlap this file states the coarse
invariant and those files prove the edges of it.

**What replaced ``tests/accounting/test_double_entry.py``.** That file added up
two hardcoded lists of ``Decimal`` and asserted they were equal. It exercised
:func:`sum`, not Dina: it would have stayed green if the posting path accepted an
unbalanced journal, read another tenant's rows or let a draft into the ledger.
Every test below goes through a real object -- :class:`src.accounting_store.
AccountingStore` for what is written, and the real ``/ledger`` and
``/trial-balance`` endpoints for what is read -- so a green run says something
about the application.

**The altitude is deliberate.** The write rules are asserted on the store's own
API rather than through HTTP because that is where the guards live, and the store
*is* the real code path: the endpoints read the same objects through the same
methods. Asserting ``r.json()["detail"]`` here instead would only re-test the
HTTP status mapping, and would tie the matrix to an error-body shape that is a
public contract of its own.

Each test is written so that deleting the guard it names turns it red. Where a
guard is doubled -- an empty journal is refused by both the store and the
validator -- that is said in the test, and removing both copies is what turns the
suite red.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ledger_fixtures import (
    DAY_ONE,
    DAY_TWO,
    DAY_THREE,
    ORGANIZATION_ID,
    OTHER_ORGANIZATION_ID,
    account_id,
    account_report,
    draft_entry,
    get_ledger,
    get_trial_balance,
    line,
    other_org_account_id,
    post_entry,
    post_other_org_entry,
)
from src.accounting import validate_journal
from src.accounting_store import AccountingError, AccountingStore
from src.models import DRAFT, POSTED, REVERSED

#: An organization id that is deliberately never registered with the store, used
#: by the "who may post here" case. 900 is far above the fixture ids so it can
#: never collide with one that is.
UNKNOWN_ORGANIZATION_ID = 900


def add_entry(
    store: AccountingStore,
    lines: list,
    *,
    document_no: str = "JV-MATRIX",
    organization_id: int = ORGANIZATION_ID,
    entry_date: date = DAY_ONE,
    status: str = DRAFT,
):
    """Call ``store.add_entry`` with the matrix's defaults.

    The tests below care about the *lines*, not the header, so the header is
    filled in once here. Every call still goes through the store's public API --
    no dictionary is poked and no state is manufactured, so a fixture cannot
    create something the application itself would refuse to create.
    """
    return store.add_entry(
        organization_id=organization_id,
        document_no=document_no,
        description="matrix fixture",
        entry_date=entry_date,
        lines=lines,
        status=status,
    )


# -- posting: what may be written at all ------------------------------------


def test_a_balanced_journal_is_accepted_and_persisted_verbatim(accounting_store):
    """Case: a balanced journal succeeds, and what was written is what is read."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    entry = add_entry(
        accounting_store,
        [line(cash, debit="250.00"), line(revenue, credit="250.00")],
        document_no="JV-BALANCED",
    )

    stored = accounting_store.get_entry(ORGANIZATION_ID, entry.id)
    assert stored.status == DRAFT
    assert stored.document_no == "JV-BALANCED"
    assert stored.entry_date == DAY_ONE
    # Amounts come back at the storage scale and the line numbers are the
    # store's, not the caller's: a persisted line is a row, and its position is
    # assigned so the ledger has a total order to step through.
    assert [(row.line_no, row.account_id, row.debit, row.credit) for row in stored.lines] == [
        (1, cash, Decimal("250.0000"), Decimal("0.0000")),
        (2, revenue, Decimal("0.0000"), Decimal("250.0000")),
    ]


def test_an_unbalanced_journal_is_refused_with_journal_not_balanced(accounting_store):
    """Case: debits that do not equal credits are refused, by name."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [line(cash, debit="100.00"), line(revenue, credit="90.00")],
            document_no="JV-UNBALANCED",
        )

    # The exact code, not merely "it raised": a journal that is 10 short and one
    # that has a line on both sides are different mistakes and a client has to be
    # able to tell them apart.
    assert refused.value.code == "journal_not_balanced"
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_a_negative_amount_is_refused_with_amount_must_be_non_negative(accounting_store):
    """Case: a negative amount is refused, and not as some other complaint."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [line(cash, debit="-100.00"), line(revenue, credit="100.00")],
            document_no="JV-NEGATIVE",
        )

    # A negative debit is also a line that is not "exactly one side", because
    # neither side is above zero. Asserting the specific code is what makes this
    # test distinguish "the sign was checked" from "the line was rejected later
    # for an unrelated reason".
    assert refused.value.code == "amount_must_be_non_negative"
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_a_line_with_both_a_debit_and_a_credit_is_refused(accounting_store):
    """Case: one line cannot be on both sides at once."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [
                line(cash, debit="100.00", credit="100.00"),
                line(revenue, credit="200.00"),
            ],
            document_no="JV-BOTH-SIDES",
        )

    assert refused.value.code == "line_must_have_exactly_one_side"
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_a_line_with_neither_a_debit_nor_a_credit_is_refused(accounting_store):
    """Case: one line must be on one side -- a line on neither is not a line."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [
                line(cash, debit="100.00"),
                line(revenue, credit="100.00"),
                line(cash, debit="0", credit="0"),
            ],
            document_no="JV-NEITHER-SIDE",
        )

    # The totals here do balance, so only the per-line rule can be what refused
    # this: remove it and the entry would be accepted.
    assert refused.value.code == "line_must_have_exactly_one_side"
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_an_empty_journal_is_refused_with_journal_must_have_lines(accounting_store):
    """Case: a journal with no lines is refused, by name.

    The guard is doubled on purpose -- the store refuses an empty line list
    before it looks at anything, and :func:`src.accounting.validate_journal`
    refuses it independently -- so that a journal cannot slip through whichever
    entry point a future caller uses. Removing either copy leaves the invariant
    enforced and this test green; removing both lets an empty entry through and
    turns it red.
    """
    with pytest.raises(AccountingError) as refused:
        add_entry(accounting_store, [], document_no="JV-EMPTY")

    assert refused.value.code == "journal_must_have_lines"
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_the_journal_validator_itself_refuses_an_empty_journal():
    """Case: the empty-journal rule holds at the validator, not only at the store.

    The rule is enforced twice on purpose, so this test is what pins the copy
    that :meth:`AccountingStore.add_entry` calls into. Without it, deleting the
    validator's own empty-list check would leave the store's guard as the only
    thing standing between a caller and an entry with no lines -- and a future
    second caller of :func:`src.accounting.validate_journal` would have nothing
    left.
    """
    with pytest.raises(ValueError) as refused:
        validate_journal([])

    assert str(refused.value) == "journal_must_have_lines"


# -- posting: who may post, and whose rows they may touch --------------------


def test_a_journal_naming_another_organizations_account_is_refused_and_persists_nothing(
    accounting_store,
):
    """Case: a cross-tenant account id is refused, and nothing is written."""
    foreign_cash = other_org_account_id(accounting_store, "1100")
    own_revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [line(foreign_cash, debit="100.00"), line(own_revenue, credit="100.00")],
            document_no="JV-CROSS-TENANT",
        )

    assert refused.value.code == "account_not_found"
    # The refusal happens before the entry id is drawn, so no header and no
    # lines exist. An entry half-written against another tenant's account is the
    # worst possible outcome, and "nothing persisted" is the half of the
    # assertion that proves it.
    assert accounting_store.list_entries(ORGANIZATION_ID) == []
    assert accounting_store.list_entries(OTHER_ORGANIZATION_ID) == []


def test_a_journal_for_an_organization_that_does_not_exist_is_refused(accounting_store):
    """Case: posting into an organization nobody created is refused."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    with pytest.raises(AccountingError) as refused:
        add_entry(
            accounting_store,
            [line(cash, debit="100.00"), line(revenue, credit="100.00")],
            document_no="JV-UNKNOWN-ORG",
            organization_id=UNKNOWN_ORGANIZATION_ID,
        )

    assert refused.value.code == "organization_not_found"
    # Registering the organization afterwards is how the store is asked whether
    # the refused write left anything under it. It did not: the entry count is
    # still zero, so the refusal happened before anything was stored rather than
    # after a row was written and hidden.
    accounting_store.add_organization(UNKNOWN_ORGANIZATION_ID)
    assert accounting_store.list_entries(UNKNOWN_ORGANIZATION_ID) == []


# -- what the ledger shows ---------------------------------------------------


def test_a_draft_entry_never_reaches_the_ledger(
    accounting_store, ledger_client: TestClient, ledger_url: str
):
    """Case: an entry nobody has posted is not a financial fact."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    draft_entry(
        accounting_store,
        "JV-DRAFT",
        DAY_ONE,
        [line(cash, debit="40.00"), line(revenue, credit="40.00")],
    )

    ledger = get_ledger(ledger_client, ledger_url)
    assert ledger["accounts"] == []
    assert ledger["period_debit_total"] == "0.00"
    assert ledger["period_credit_total"] == "0.00"
    assert ledger["is_balanced"] is True


def test_a_posted_entry_reaches_the_ledger_with_its_exact_amounts(
    accounting_store, ledger_client: TestClient, ledger_url: str
):
    """Case: the same journal, once posted, is in the ledger."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")

    post_entry(
        accounting_store,
        "JV-POSTED",
        DAY_ONE,
        [line(cash, debit="40.00"), line(revenue, credit="40.00")],
    )

    report = account_report(get_ledger(ledger_client, ledger_url), cash)
    assert report["account_code"] == "1100"
    assert report["normal_balance"] == "debit"
    assert report["opening_balance"] == "0.00"
    assert report["period_debit_total"] == "40.00"
    assert report["period_credit_total"] == "0.00"
    assert report["closing_balance"] == "40.00"
    assert [movement["document_no"] for movement in report["movements"]] == ["JV-POSTED"]


# -- reversal ----------------------------------------------------------------


def test_reversing_an_entry_leaves_the_original_intact(
    accounting_store, ledger_client: TestClient, ledger_url: str
):
    """Case: a reversal does not rewrite the entry it undoes."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    original_id = post_entry(
        accounting_store,
        "JV-ORIGINAL",
        DAY_ONE,
        [line(cash, debit="120.00"), line(revenue, credit="120.00")],
    )

    reversing = accounting_store.reverse_entry(
        ORGANIZATION_ID, original_id, "REV-1", DAY_TWO
    )

    original = accounting_store.get_entry(ORGANIZATION_ID, original_id)
    assert original.status == REVERSED
    assert original.document_no == "JV-ORIGINAL"
    assert [(row.account_id, row.debit, row.credit) for row in original.lines] == [
        (cash, Decimal("120.0000"), Decimal("0.0000")),
        (revenue, Decimal("0.0000"), Decimal("120.0000")),
    ]
    # Both entries are still readable from the ledger, in the order they
    # happened, so a reader can see the fact and its undo side by side.
    movements = account_report(get_ledger(ledger_client, ledger_url), cash)["movements"]
    assert [movement["document_no"] for movement in movements] == ["JV-ORIGINAL", "REV-1"]


def test_the_reversing_entry_is_the_mirror_image_of_the_original(accounting_store):
    """Case: every debit becomes a credit of the same amount, and vice versa."""
    cash = account_id(accounting_store, "1100")
    expense = account_id(accounting_store, "5000")
    original_id = post_entry(
        accounting_store,
        "JV-ORIGINAL",
        DAY_ONE,
        [line(cash, debit="75.50"), line(expense, credit="75.50")],
    )

    reversing = accounting_store.reverse_entry(
        ORGANIZATION_ID, original_id, "REV-1", DAY_TWO
    )
    original = accounting_store.get_entry(ORGANIZATION_ID, original_id)

    assert reversing.status == POSTED
    assert reversing.reversal_of_entry_id == original_id
    assert original.reversal_of_entry_id is None
    assert [
        (row.account_id, row.debit, row.credit) for row in reversing.lines
    ] == [
        (row.account_id, row.credit, row.debit) for row in original.lines
    ]


def test_a_reversal_nets_to_zero_on_the_account_balance(
    accounting_store, ledger_client: TestClient, ledger_url: str
):
    """Case: the pair together move the account by nothing."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    original_id = post_entry(
        accounting_store,
        "JV-ORIGINAL",
        DAY_ONE,
        [line(cash, debit="500.00"), line(revenue, credit="500.00")],
    )

    accounting_store.reverse_entry(ORGANIZATION_ID, original_id, "REV-1", DAY_TWO)

    report = account_report(get_ledger(ledger_client, ledger_url), cash)
    # Both sides are still visible -- that is the point of a reversal -- but they
    # are equal, so the account is left exactly where it started and neither the
    # original nor the reversal has been quietly dropped to make that true.
    assert report["period_debit_total"] == "500.00"
    assert report["period_credit_total"] == "500.00"
    assert report["closing_balance"] == "0.00"
    assert len(report["movements"]) == 2


# -- immutability ------------------------------------------------------------


def test_a_posted_entry_cannot_be_edited(accounting_store):
    """Case: a posted entry is not editable."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    entry_id = post_entry(
        accounting_store,
        "JV-LOCKED",
        DAY_ONE,
        [line(cash, debit="60.00"), line(revenue, credit="60.00")],
        description="as written",
    )

    with pytest.raises(AccountingError) as refused:
        accounting_store.update_entry(
            ORGANIZATION_ID, entry_id, description="quietly rewritten"
        )

    assert refused.value.code == "journal_immutable"
    unchanged = accounting_store.get_entry(ORGANIZATION_ID, entry_id)
    assert unchanged.description == "as written"
    assert unchanged.lines[0].debit == Decimal("60.0000")


def test_a_posted_entry_cannot_be_deleted(accounting_store):
    """Case: a posted entry is not deletable -- it is reversible, not erasable."""
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    entry_id = post_entry(
        accounting_store,
        "JV-LOCKED",
        DAY_ONE,
        [line(cash, debit="60.00"), line(revenue, credit="60.00")],
    )

    with pytest.raises(AccountingError) as refused:
        accounting_store.delete_entry(ORGANIZATION_ID, entry_id)

    assert refused.value.code == "journal_immutable"
    assert [entry.id for entry in accounting_store.list_entries(ORGANIZATION_ID)] == [
        entry_id
    ]


def test_a_reversed_entry_is_immutable_too(accounting_store):
    """Case: immutability outlives posting -- ``reversed`` is not a free state.

    A reversal is the correction, so the entry that carries the ``reversed``
    status is exactly the one a second correction must not rewrite. If it could,
    the pair would stop netting to zero and the ledger would be wrong.
    """
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    entry_id = post_entry(
        accounting_store,
        "JV-ORIGINAL",
        DAY_ONE,
        [line(cash, debit="30.00"), line(revenue, credit="30.00")],
    )
    accounting_store.reverse_entry(ORGANIZATION_ID, entry_id, "REV-1", DAY_TWO)

    with pytest.raises(AccountingError) as edit_refused:
        accounting_store.update_entry(ORGANIZATION_ID, entry_id, description="rewritten")
    with pytest.raises(AccountingError) as delete_refused:
        accounting_store.delete_entry(ORGANIZATION_ID, entry_id)

    assert edit_refused.value.code == "journal_immutable"
    assert delete_refused.value.code == "journal_immutable"


def test_a_draft_may_still_be_edited_and_deleted(accounting_store):
    """Case: the immutability guard is about posting, not about being strict.

    If every mutation were refused this whole file would be green for the wrong
    reason. A draft is editable and deletable, and that is what makes the refusal
    above a real boundary rather than a blanket one.
    """
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    entry_id = draft_entry(
        accounting_store,
        "JV-DRAFT",
        DAY_ONE,
        [line(cash, debit="10.00"), line(revenue, credit="10.00")],
    )

    edited = accounting_store.update_entry(
        ORGANIZATION_ID, entry_id, description="now with a description"
    )
    assert edited.description == "now with a description"
    assert edited.status == DRAFT

    accounting_store.delete_entry(ORGANIZATION_ID, entry_id)
    assert accounting_store.list_entries(ORGANIZATION_ID) == []


def test_editing_a_draft_cannot_smuggle_in_an_unbalanced_journal(accounting_store):
    """Case: the edit path enforces the same invariants as the create path.

    An edit that skipped re-validation would be a hole straight past every rule
    in the posting matrix above, reachable by writing a valid draft and then
    changing it into something the application would never have accepted.
    """
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    entry_id = draft_entry(
        accounting_store,
        "JV-DRAFT",
        DAY_ONE,
        [line(cash, debit="10.00"), line(revenue, credit="10.00")],
    )

    with pytest.raises(AccountingError) as refused:
        accounting_store.update_entry(
            ORGANIZATION_ID,
            entry_id,
            lines=[line(cash, debit="10.00"), line(revenue, credit="9.00")],
        )

    assert refused.value.code == "journal_not_balanced"
    assert accounting_store.get_entry(ORGANIZATION_ID, entry_id).lines[1].credit == (
        Decimal("10.0000")
    )


# -- the two reports, and the arithmetic they claim to do -------------------


def test_the_trial_balance_totals_debits_equal_totals_credits(
    accounting_store, trial_balance_client: TestClient, trial_balance_url: str
):
    """Case: the trial balance's two columns are equal for a balanced book."""
    cash = account_id(accounting_store, "1100")
    expense = account_id(accounting_store, "5000")
    revenue = account_id(accounting_store, "4000")
    post_entry(
        accounting_store,
        "JV-ONE",
        DAY_ONE,
        [line(cash, debit="1000.00"), line(revenue, credit="1000.00")],
    )
    post_entry(
        accounting_store,
        "JV-TWO",
        DAY_TWO,
        [line(expense, debit="250.25"), line(cash, credit="250.25")],
    )

    report = get_trial_balance(trial_balance_client, trial_balance_url)

    assert report["is_balanced"] is True
    assert report["totals"]["debit_total"] == "1250.25"
    assert report["totals"]["credit_total"] == "1250.25"
    assert report["totals"]["difference"] == "0.00"
    # The two columns are also the sum of the rows, so the total is a total and
    # not a second, independently computed figure.
    assert sum(Decimal(row["debit_total"]) for row in report["accounts"]) == Decimal(
        "1250.25"
    )
    assert sum(Decimal(row["credit_total"]) for row in report["accounts"]) == Decimal(
        "1250.25"
    )


def test_the_ledger_running_balance_is_correct_across_multiple_entries(
    accounting_store, ledger_client: TestClient, ledger_url: str
):
    """Case: the running balance steps by each line and ends where it should.

    Three movements of different signs in a row, so a running balance that is
    merely seeded correctly but never updated -- or updated from the wrong side
    -- lands somewhere else.
    """
    cash = account_id(accounting_store, "1100")
    expense = account_id(accounting_store, "5000")
    revenue = account_id(accounting_store, "4000")
    post_entry(
        accounting_store,
        "JV-ONE",
        DAY_ONE,
        [line(cash, debit="100.00"), line(revenue, credit="100.00")],
    )
    post_entry(
        accounting_store,
        "JV-TWO",
        DAY_TWO,
        [line(expense, debit="30.00"), line(cash, credit="30.00")],
    )
    post_entry(
        accounting_store,
        "JV-THREE",
        DAY_THREE,
        [line(cash, debit="5.00"), line(revenue, credit="5.00")],
    )

    report = account_report(get_ledger(ledger_client, ledger_url), cash)

    assert [movement["running_balance"] for movement in report["movements"]] == [
        "100.00",
        "70.00",
        "75.00",
    ]
    assert report["period_debit_total"] == "105.00"
    assert report["period_credit_total"] == "30.00"
    assert report["opening_balance"] == "0.00"
    assert report["closing_balance"] == "75.00"
    assert report["closing_balance"] == report["movements"][-1]["running_balance"]


def test_the_stores_ledger_read_is_scoped_to_one_organization(accounting_store):
    """Case: the tenant-scoped read returns one organization's entries and no others.

    The reports call this, so it is the read the isolation guarantee is actually
    made of. Asserting it directly, rather than only through the rendered report,
    is deliberate: a report can come out clean by accident -- account ids are
    globally unique, so a leak into a report is not guaranteed to change the
    figures. Here the leak is the thing being tested, and org 2's entry is
    unmistakable in org 1's list.
    """
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    post_entry(
        accounting_store,
        "JV-ORG-ONE",
        DAY_ONE,
        [line(cash, debit="500.00"), line(revenue, credit="500.00")],
    )
    post_other_org_entry(accounting_store, "JV-ORG-TWO", DAY_ONE, "7000.00")

    assert [entry.document_no for entry in accounting_store.ledger_entries(ORGANIZATION_ID)] == [
        "JV-ORG-ONE"
    ]
    assert [
        entry.document_no
        for entry in accounting_store.ledger_entries(OTHER_ORGANIZATION_ID)
    ] == ["JV-ORG-TWO"]


def test_an_entry_in_one_organization_never_reaches_another_tenants_reports(
    accounting_store, ledger_client: TestClient, ledger_url: str, trial_balance_url: str
):
    """Case: org B's postings are invisible in org A's ledger and trial balance.

    Org 2 is made a real tenant with real postings first, so a clean report for
    org 1 cannot be explained by org 2 simply having nothing in it.

    This is the end-to-end half of the isolation guarantee; the store-scoped read
    it depends on is pinned by ``test_the_stores_ledger_read_is_scoped_to_one_
    organization``. Between them there is defence in depth: account ids are
    globally unique and ``add_entry`` refuses a line naming another tenant's
    account, so this report would stay clean even without the ledger read's own
    organization filter. That is a reason to be glad there are two guards, not a
    reason to test the same line twice.
    """
    cash = account_id(accounting_store, "1100")
    revenue = account_id(accounting_store, "4000")
    post_entry(
        accounting_store,
        "JV-ORG-ONE",
        DAY_ONE,
        [line(cash, debit="500.00"), line(revenue, credit="500.00")],
    )
    post_other_org_entry(accounting_store, "JV-ORG-TWO", DAY_ONE, "7000.00")

    ledger = get_ledger(ledger_client, ledger_url)
    # Keyed by account code so an entry touching two accounts is not counted
    # twice: the report is a per-account ledger, and the assertion is that the
    # set of accounts and the set of documents are org 1's alone.
    documents_by_account = {
        report["account_code"]: [
            movement["document_no"] for movement in report["movements"]
        ]
        for report in ledger["accounts"]
    }
    assert documents_by_account == {"1100": ["JV-ORG-ONE"], "4000": ["JV-ORG-ONE"]}
    assert ledger["period_debit_total"] == "500.00"
    assert ledger["period_credit_total"] == "500.00"

    trial_balance = get_trial_balance(ledger_client, trial_balance_url)
    assert trial_balance["totals"]["debit_total"] == "500.00"
    assert trial_balance["totals"]["credit_total"] == "500.00"
    assert {row["account_code"] for row in trial_balance["accounts"]} == {"1100", "4000"}
    assert trial_balance["is_balanced"] is True
