# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Abs, Sum
from erp_contract.utils.contract import format_currency_in_words


def update_overdue_installments():
    """
    Daily scheduler task — safety net for installment rows that have never had a
    payment event fired against them.

    Marks installment rows as 'Overdue' when:
      - parent ERP Contract is submitted (docstatus=1)
      - apply_installment_payment is checked
      - installment_due_date < today
      - installment_payment_status is currently 'Unpaid' or 'Partially Paid'

    Note: 'Paid' and 'Overdue' rows are intentionally excluded from the query.
    The waterfall in recalculate_installment_payment() already sets 'Overdue'
    in real-time when a payment event fires. This scheduler only catches the
    remaining case: rows whose due date passed with no payment at all.
    """
    from frappe.utils import today

    today_date = today()

    Sch = frappe.qb.DocType("Installment Schedule")
    Con = frappe.qb.DocType("ERP Contract")

    rows = (
        frappe.qb.from_(Sch)
        .join(Con).on(Con.name == Sch.parent)
        .select(Sch.name)
        .where(Sch.parenttype == "ERP Contract")
        .where(Con.docstatus == 1)
        .where(Con.apply_installment_payment == 1)
        .where(Sch.installment_due_date < today_date)
        .where(Sch.installment_payment_status.isin(["Unpaid", "Partially Paid"]))
    ).run(as_dict=True)

    for row in rows:
        frappe.db.set_value(
            "Installment Schedule",
            row.name,
            "installment_payment_status",
            "Overdue",
            update_modified=False,
        )

    if rows:
        frappe.db.commit()


def _total_paid_against_so(so_name) -> float:
    """
    Total amount received against a Sales Order.

    The Sales Order is the *only* reference the contract tracks payment through.
    Any payment that references the SO (whether the user calls it an advance or a
    final payment) is recorded by ERPNext in the Advance Payment Ledger Entry
    against the order — this is the same figure ERPNext surfaces as
    Sales Order.advance_paid.

    delinked=0 excludes cancelled/reversed entries; Abs(Sum(...)) normalises the
    ledger sign.  Sales Invoices are intentionally NOT consulted: an invoice may
    or may not be paid, so the order is the reliable anchor.
    """
    from frappe.utils import flt

    APLE = frappe.qb.DocType("Advance Payment Ledger Entry")
    result = (
        frappe.qb.from_(APLE)
        .select(Abs(Sum(APLE.amount)).as_("total_paid"))
        .where(APLE.against_voucher_type == "Sales Order")
        .where(APLE.against_voucher_no == so_name)
        .where(APLE.delinked == 0)
    ).run(as_dict=True)

    return flt(result[0].total_paid if result else 0)


def recalculate_contract_payment(sales_orders):
    """
    Shared aggregation for payment override handlers (PE and JE) and on_submit.

    For every submitted ERP Contract linked to one of the given Sales Orders:
      1. Reads the total paid against the SO from the Advance Payment Ledger Entry.
      2. Updates contract-level per_payment and payment_status.
      3. If apply_installment_payment is set, additionally distributes the
         payment across payment_schedule rows via recalculate_installment_payment().

    Source of truth: Advance Payment Ledger Entry against the Sales Order
    (== Sales Order.advance_paid). The contract anchors only the SO and does not
    distinguish advance vs final payment — see _total_paid_against_so().
    """
    from frappe.utils import flt

    for so_name in sales_orders:
        contracts = frappe.get_all(
            "ERP Contract",
            filters={"sales_order": so_name, "docstatus": 1},
            fields=["name", "net_total", "advance_amount",
                    "apply_installment_payment"],
        )

        if not contracts:
            continue

        total_paid = _total_paid_against_so(so_name)

        for contract in contracts:
            net_total = flt(contract.net_total)
            per_payment = flt(total_paid / net_total *
                              100, 2) if net_total else 0

            if total_paid <= 0:
                payment_status = "Unpaid"
            elif per_payment >= 100:
                payment_status = "Fully Paid"
            else:
                payment_status = "Partially Paid"

            frappe.db.set_value(
                "ERP Contract",
                contract.name,
                {
                    "per_payment": per_payment,
                    "payment_status": payment_status,
                },
                update_modified=False,
            )

            if contract.apply_installment_payment:
                recalculate_installment_payment(
                    contract.name,
                    total_paid=total_paid,
                    advance_amount=flt(contract.advance_amount),
                )


def recalculate_installment_payment(contract_name, total_paid=None, advance_amount=None):
    """
    Distribute the net installment payment across Installment Schedule rows using a
    chronological waterfall: earliest due_date rows are filled first.

    The advance payment is already captured in total_paid (the SO advance ledger
    includes it) but belongs to a separate financial bucket — it must be subtracted
    before distributing across installment rows, which only sum to
    (net_total - advance_amount).

        installment_pool = max(0, total_paid - advance_amount)

    Each row receives as much of the pool as it can absorb (up to its installment_amount),
    then the remainder flows to the next row.

    Status logic is date-aware: if a row's due_date has already passed, it is marked
    'Overdue' instead of 'Unpaid' or 'Partially Paid', so cancelling a payment never
    silently resets an overdue row to a misleadingly clean status.

    Per-row fields written (all allow_on_submit=1, read_only):
        paid_amount              — amount absorbed by this row
        installment_per_payment  — paid_amount / installment_amount * 100
        installment_payment_status — Unpaid / Overdue / Partially Paid / Paid

    If total_paid / advance_amount are not supplied (standalone call), the function
    re-reads the SO advance ledger and advance_amount from the contract document.
    Both must be supplied together or not at all.
    """
    from frappe.utils import flt, getdate, today as get_today

    if total_paid is None or advance_amount is None:
        contract_doc = frappe.db.get_value(
            "ERP Contract",
            contract_name,
            ["sales_order", "advance_amount", "net_total"],
            as_dict=True,
        )
        if not contract_doc:
            return

        if advance_amount is None:
            advance_amount = flt(contract_doc.advance_amount)

        if total_paid is None:
            # sales_order is required only for the ledger query; guard it here,
            # not at the outer level, so a supplied total_paid is never discarded.
            if not contract_doc.sales_order:
                return
            total_paid = _total_paid_against_so(contract_doc.sales_order)

    installment_pool = max(0.0, flt(total_paid) - flt(advance_amount))

    rows = frappe.get_all(
        "Installment Schedule",
        filters={"parent": contract_name, "parentfield": "payment_schedule"},
        fields=["name", "installment_amount", "installment_due_date"],
        order_by="installment_due_date asc",
    )

    today_date = getdate(get_today())
    remaining = installment_pool

    for row in rows:
        installment_amount = flt(row.installment_amount)
        due_date = getdate(
            row.installment_due_date) if row.installment_due_date else None
        is_past_due = bool(due_date and due_date < today_date)

        absorbed = min(remaining, installment_amount)
        remaining = max(0.0, remaining - absorbed)

        per = flt(absorbed / installment_amount *
                  100, 2) if installment_amount else 0

        if per >= 100:
            status = "Paid"
        elif absorbed <= 0:
            status = "Overdue" if is_past_due else "Unpaid"
        else:
            status = "Overdue" if is_past_due else "Partially Paid"

        frappe.db.set_value(
            "Installment Schedule",
            row.name,
            {
                "paid_amount": absorbed,
                "installment_per_payment": per,
                "installment_payment_status": status,
            },
            update_modified=False,
        )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_advance_payment_entries(doctype, txt, searchfield, start, page_len, filters):
    """Get Payment Entry documents filtered by company, customer, and reference document,
    excluding entries already linked to a submitted ERP Contract."""
    company = filters.get('company')
    customer = filters.get('customer')
    reference_doctype = filters.get('reference_doctype')
    reference_name = filters.get('reference_name')
    current_contract = filters.get('current_contract')

    if not all([company, customer, reference_doctype, reference_name]):
        return []

    PE = frappe.qb.DocType("Payment Entry")
    PER = frappe.qb.DocType("Payment Entry Reference")
    EC = frappe.qb.DocType("ERP Contract")

    taken = frappe.qb.from_(EC).select(EC.advance_payment_entry).where(
        (EC.docstatus == 1)
        & (EC.advance_payment_entry.isnotnull())
        & (EC.advance_payment_entry != "")
        & (EC.name != (current_contract or ""))
    )

    query = (
        frappe.qb.from_(PE)
        .inner_join(PER).on(PER.parent == PE.name)
        .select(PE.name, PE[searchfield])
        .distinct()
        .where(PE.docstatus == 1)
        .where(PE.company == company)
        .where(PE.party == customer)
        .where(PE.payment_type == "Receive")
        .where(PER.reference_doctype == reference_doctype)
        .where(PER.reference_name == reference_name)
        .where(PE.name.notin(taken))
        .orderby(PE[searchfield])
        .limit(page_len)
        .offset(start)
    )

    if txt:
        query = query.where(PE[searchfield].like(f"%{txt}%"))

    return query.run()


@frappe.whitelist()
def get_payment_entry_details(deposit_reference):
    """Fetch payment entry details based on the deposit reference."""
    doc = frappe.get_doc("Payment Entry", deposit_reference)

    return {
        "paid_amount": doc.paid_amount,
        "advance_amount_in_words": format_currency_in_words(doc.paid_amount, doc.paid_to_account_currency),
    }


def installment_percents(amounts, amount_due):
    """Each amount's share of ``amount_due`` as a percentage (2dp).

    The last row absorbs the rounding drift so the percentages sum to exactly 100.
    Returns zeros when ``amount_due`` is non-positive. Works for equal or
    hand-edited (unequal) amounts — used both when generating a schedule and when
    revalidating a manually edited one on save.
    """
    from frappe.utils import flt

    amount_due = flt(amount_due)
    if amount_due <= 0 or not amounts:
        return [0.0] * len(amounts)

    percents = [flt(flt(a) / amount_due * 100, 2) for a in amounts]
    percents[-1] = flt(percents[-1] + 100 - sum(percents), 2)
    return percents


@frappe.whitelist()
def create_payment_schedule(due_start_date, installment_count, payment_periodicity, amount_due, currency):
    """Generate installment schedule rows from the given parameters."""
    from dateutil.relativedelta import relativedelta
    from frappe.utils import getdate, flt

    installment_count = int(installment_count)
    amount_due = flt(amount_due)

    if installment_count <= 0:
        frappe.throw(_("Installment Count must be greater than zero"))
    if amount_due <= 0:
        frappe.throw(_("Amount Due must be greater than zero"))

    periodicity_months = {"Monthly": 1,
                          "Quarterly": 3,
                          "Half-Yearly": 6,
                          "Yearly": 12}
    months = periodicity_months.get(payment_periodicity)
    if not months:
        frappe.throw(_("Invalid Payment Periodicity: {0}").format(
            payment_periodicity))

    base_amount = flt(amount_due / installment_count, 2)
    last_amount = flt(amount_due - base_amount * (installment_count - 1), 2)
    amounts = [base_amount] * (installment_count - 1) + [last_amount]
    percents = installment_percents(amounts, amount_due)

    start = getdate(due_start_date)
    return [
        {
            "installment_amount": amounts[i],
            "installment_in_words": format_currency_in_words(amounts[i], currency),
            "installment_due_date": str(start + relativedelta(months=i * months)),
            "installment_percent": percents[i],
        }
        for i in range(installment_count)
    ]


# ---------------------------------------------------------------------------
# Post-renewal payment setup
# (see docs/contract_renewal/renewal_payment_setup.md)
# ---------------------------------------------------------------------------

def _assert_renewal_payment_editable(doc) -> None:
    """Guard shared by the post-renewal 'Create' payment methods."""
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted contracts can be modified."))
    if not doc.is_renewed:
        frappe.throw(
            _("Payment setup is only available on renewed contracts."))


@frappe.whitelist()
def set_renewal_advance(contract_name, advance_payment_entry):
    """
    Link an existing advance Payment Entry to a renewed contract's new period.

    Allowed only before an installment schedule is built (advance must precede
    installments — see renewal_payment_setup.md). Writes through
    ignore_validate_update_after_submit, then resyncs payment progress.
    """
    from frappe.utils import flt

    doc = frappe.get_doc("ERP Contract", contract_name)
    frappe.has_permission("ERP Contract", "write", doc, throw=True)

    _assert_renewal_payment_editable(doc)
    if doc.advance_payment_entry:
        frappe.throw(
            _("An advance payment is already linked to this contract."))
    if doc.apply_installment_payment and doc.payment_schedule:
        frappe.throw(
            _("Installments are already set up; the advance can no longer be changed.")
        )
    if not advance_payment_entry:
        frappe.throw(_("An advance Payment Entry is required."))

    pe = frappe.db.get_value(
        "Payment Entry", advance_payment_entry,
        ["docstatus", "payment_type", "company", "party",
         "paid_amount", "paid_to_account_currency"],
        as_dict=True,
    )
    if not pe:
        frappe.throw(_("Payment Entry {0} does not exist.").format(
            frappe.bold(advance_payment_entry)))
    if pe.docstatus != 1:
        frappe.throw(_("Payment Entry {0} is not submitted.").format(
            frappe.bold(advance_payment_entry)))
    if pe.payment_type != "Receive":
        frappe.throw(_("Payment Entry {0} is not a receive payment.").format(
            frappe.bold(advance_payment_entry)))
    if pe.company != doc.company:
        frappe.throw(_("Payment Entry {0} does not belong to Company {1}.").format(
            frappe.bold(advance_payment_entry), frappe.bold(doc.company)))
    if pe.party != doc.customer:
        frappe.throw(_("Payment Entry {0} does not belong to Customer {1}.").format(
            frappe.bold(advance_payment_entry), frappe.bold(doc.customer)))

    if not frappe.db.exists(
        "Payment Entry Reference",
        {"parent": advance_payment_entry, "reference_doctype": "Sales Order",
         "reference_name": doc.sales_order},
    ):
        frappe.throw(_("Payment Entry {0} does not reference Sales Order {1}.").format(
            frappe.bold(advance_payment_entry), frappe.bold(doc.sales_order)))

    taken_by = frappe.db.get_value(
        "ERP Contract",
        {"advance_payment_entry": advance_payment_entry, "docstatus": 1,
         "name": ("!=", doc.name)},
        "name",
    )
    if taken_by:
        frappe.throw(_("Payment Entry {0} is already the advance of Contract {1}.").format(
            frappe.bold(advance_payment_entry),
            frappe.utils.get_link_to_form("ERP Contract", taken_by)))

    advance_amount = flt(pe.paid_amount)
    net_total = flt(doc.net_total)
    if advance_amount > net_total:
        frappe.throw(_("Advance amount ({0}) cannot exceed the contract net total ({1}).").format(
            advance_amount, net_total))

    doc.advance_payment_entry = advance_payment_entry
    doc.advance_amount = advance_amount
    doc.advance_amount_in_words = format_currency_in_words(
        advance_amount, pe.paid_to_account_currency)
    doc.amount_due = max(0.0, flt(net_total - advance_amount, 2))

    doc.flags.ignore_validate_update_after_submit = True
    doc.save()

    if doc.sales_order:
        recalculate_contract_payment({doc.sales_order})

    return {"advance_amount": advance_amount, "amount_due": doc.amount_due}


@frappe.whitelist()
def set_renewal_installments(contract_name, due_start_date, payment_periodicity, installment_count):
    """
    Build the installment schedule for a renewed contract's new period.

    amount_due is derived from (net_total - advance_amount); the schedule rows
    sum to amount_due by construction. Writes through
    ignore_validate_update_after_submit, then resyncs payment progress (which
    runs the installment waterfall).
    """
    from frappe.utils import flt

    doc = frappe.get_doc("ERP Contract", contract_name)
    frappe.has_permission("ERP Contract", "write", doc, throw=True)

    _assert_renewal_payment_editable(doc)
    if doc.apply_installment_payment:
        frappe.throw(
            _("An installment schedule already exists for this contract."))

    amount_due = flt(flt(doc.net_total) - flt(doc.advance_amount), 2)
    if amount_due <= 0:
        frappe.throw(
            _("Amount Due ({0}) must be greater than zero to create an installment schedule.").format(
                amount_due)
        )

    schedule = create_payment_schedule(
        due_start_date=due_start_date,
        installment_count=installment_count,
        payment_periodicity=payment_periodicity,
        amount_due=amount_due,
        currency=doc.currency,
    )

    doc.apply_installment_payment = 1
    doc.due_start_date = due_start_date
    doc.payment_periodicity = payment_periodicity
    doc.installment_count = int(installment_count)
    doc.amount_due = amount_due
    doc.payment_schedule = []
    for row in schedule:
        doc.append("payment_schedule", row)

    doc.flags.ignore_validate_update_after_submit = True
    doc.save()

    if doc.sales_order:
        recalculate_contract_payment({doc.sales_order})

    return {"amount_due": amount_due, "rows": len(schedule)}
