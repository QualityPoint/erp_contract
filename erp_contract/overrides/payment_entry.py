# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from erp_contract.utils.payment import recalculate_contract_payment


def update_contract_payment_status(doc, method=None):
    """
    Called on Payment Entry on_submit and on_cancel via doc_events.

    Extracts Sales Orders from the PE references table, then delegates
    to recalculate_contract_payment() (PLE-based, mirrors ERPNext's
    set_total_advance_paid pattern).
    """
    sales_orders = {
        ref.reference_name
        for ref in doc.get("references", [])
        if ref.reference_doctype == "Sales Order" and ref.reference_name
    }

    if not sales_orders:
        return

    recalculate_contract_payment(sales_orders)

