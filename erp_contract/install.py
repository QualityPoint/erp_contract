# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe


def after_install():
    seed_contact_template()


def seed_contact_template():
    """Ensure the Contract Contact Template single doc has the default template loaded."""
    from erp_contract.erp_contract.doctype.contract_contact_template.contract_contact_template import (
        get_default_contact_template,
    )

    existing = frappe.db.get_singles_value(
        "Contract Contact Template", "template")
    if not existing:
        doc = frappe.get_single("Contract Contact Template")
        doc.template = get_default_contact_template()
        doc.save(ignore_permissions=True)
        frappe.db.commit()
