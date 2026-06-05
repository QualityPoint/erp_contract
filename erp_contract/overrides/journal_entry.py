# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

from erp_contract.utils.payment import recalculate_contract_payment


def update_contract_payment_status_from_je(doc, method=None):
    """
    Called on Journal Entry on_submit and on_cancel via doc_events.

    Journal Entry references Sales Orders via the `accounts` child table
    (reference_type / reference_name fields), unlike Payment Entry which
    uses a dedicated `references` table.

    Delegates to recalculate_contract_payment() in utils — PLE-based,
    mirrors ERPNext's set_total_advance_paid pattern.
    """
    sales_orders = {
        row.reference_name
        for row in doc.get("accounts", [])
        if row.get("reference_type") == "Sales Order" and row.get("reference_name")
    }

    if not sales_orders:
        return

    recalculate_contract_payment(sales_orders)
