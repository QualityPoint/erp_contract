# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe


def get_contract_status(is_signed, contract_category, start_date, end_date):
    """
    Pure function — derives ERP Contract status from document fields.

    Duration-Based:
        not signed          → Unsigned
        signed, within dates → Active
        signed, past end    → Inactive

    Milestone-Based:
        not signed → Unsigned
        signed     → Active  (Completed/Terminated are set manually via buttons)
    """
    if not is_signed:
        return "Unsigned"

    if contract_category == "Duration-Based":
        from frappe.utils import getdate, nowdate
        today = getdate(nowdate())
        start = getdate(start_date) if start_date else today
        end = getdate(end_date) if end_date else None

        if end and today > end:
            return "Inactive"
        if today >= start:
            return "Active"
        # Signed but start_date is in the future — the contract is valid,
        # it simply hasn't started yet.  "Unsigned" would be misleading
        # because the document IS signed.
        return "Active"

    # Milestone-Based — only auto transition is Unsigned → Active on signing
    return "Active"


def update_status_for_contracts():
    """
    Daily scheduler task — recalculates Active/Inactive for all submitted,
    signed, Duration-Based ERP Contracts whose status is not manually locked.
    """
    MANUAL_STATUSES = {"On Hold", "Terminated", "Cancelled"}

    contracts = frappe.get_all(
        "ERP Contract",
        filters={
            "docstatus": 1,
            "is_signed": 1,
            "contract_category": "Duration-Based",
            "status": ("not in", list(MANUAL_STATUSES)),
        },
        fields=["name", "start_date", "end_date"],
    )

    for contract in contracts:
        new_status = get_contract_status(
            is_signed=True,
            contract_category="Duration-Based",
            start_date=contract.start_date,
            end_date=contract.end_date,
        )
        frappe.db.set_value("ERP Contract", contract.name, "status", new_status, update_modified=False)

    frappe.db.commit()
