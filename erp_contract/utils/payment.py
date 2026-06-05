# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
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


def recalculate_contract_payment(sales_orders):
    """
    Shared aggregation for payment override handlers (PE and JE) and on_submit.

    For every submitted ERP Contract linked to one of the given Sales Orders:
      1. Queries Payment Ledger Entry (PLE) for the total paid against the SO.
      2. Updates contract-level per_payment and payment_status.
      3. If apply_installment_payment is set, additionally distributes the net
         installment payment across payment_schedule rows via
         recalculate_installment_payment().

    Source of truth: PLE (GL layer) — mirrors ERPNext's set_total_advance_paid pattern.
    delinked=0 excludes cancelled/reversed entries automatically.
    Abs(Sum(...)) normalises sign differences between PE and JE entries.
    """
    from frappe.utils import flt

    PLE = frappe.qb.DocType("Payment Ledger Entry")

    for so_name in sales_orders:
        contracts = frappe.get_all(
            "ERP Contract",
            filters={"sales_order": so_name, "docstatus": 1},
            fields=["name", "net_total", "advance_amount", "apply_installment_payment"],
        )

        if not contracts:
            continue

        result = (
            frappe.qb.from_(PLE)
            .select(
                frappe.qb.fn.Abs(
                    frappe.qb.fn.Sum(PLE.amount_in_account_currency)
                ).as_("total_paid")
            )
            .where(PLE.against_voucher_type == "Sales Order")
            .where(PLE.against_voucher_no == so_name)
            .where(PLE.delinked == 0)
        ).run(as_dict=True)

        total_paid = flt(result[0].total_paid if result else 0)

        for contract in contracts:
            net_total = flt(contract.net_total)
            per_payment = flt(total_paid / net_total * 100, 2) if net_total else 0

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

    The advance payment is already captured in total_paid (PLE includes it) but
    belongs to a separate financial bucket — it must be subtracted before distributing
    across installment rows, which only sum to (net_total - advance_amount).

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
    re-queries PLE and reads advance_amount from the contract document. Both must
    be supplied together or not at all.
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
            # sales_order is required only for the PLE query; guard it here,
            # not at the outer level, so a supplied total_paid is never discarded.
            if not contract_doc.sales_order:
                return
            PLE = frappe.qb.DocType("Payment Ledger Entry")
            result = (
                frappe.qb.from_(PLE)
                .select(
                    frappe.qb.fn.Abs(
                        frappe.qb.fn.Sum(PLE.amount_in_account_currency)
                    ).as_("total_paid")
                )
                .where(PLE.against_voucher_type == "Sales Order")
                .where(PLE.against_voucher_no == contract_doc.sales_order)
                .where(PLE.delinked == 0)
            ).run(as_dict=True)
            total_paid = flt(result[0].total_paid if result else 0)

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
        due_date = getdate(row.installment_due_date) if row.installment_due_date else None
        is_past_due = bool(due_date and due_date < today_date)

        absorbed = min(remaining, installment_amount)
        remaining = max(0.0, remaining - absorbed)

        per = flt(absorbed / installment_amount * 100, 2) if installment_amount else 0

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

    periodicity_months = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
    months = periodicity_months.get(payment_periodicity)
    if not months:
        frappe.throw(_("Invalid Payment Periodicity: {0}").format(payment_periodicity))

    base_amount = flt(amount_due / installment_count, 2)
    last_amount = flt(amount_due - base_amount * (installment_count - 1), 2)

    start = getdate(due_start_date)
    schedule = []
    for i in range(installment_count):
        amount = last_amount if i == installment_count - 1 else base_amount
        schedule.append({
            "installment_amount": amount,
            "installment_in_words": format_currency_in_words(amount, currency),
            "installment_due_date": str(start + relativedelta(months=i * months)),
        })

    return schedule
