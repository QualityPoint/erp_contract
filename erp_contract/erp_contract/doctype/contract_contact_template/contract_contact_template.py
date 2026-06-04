# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

from pathlib import Path

import frappe
from frappe.model.document import Document
from frappe.utils.jinja import validate_template


class ContractContactTemplate(Document):
    def validate(self):
        if self.template:
            validate_template(self.template)

        if not self.template:
            self.template = get_default_contact_template()


@frappe.whitelist()
def get_default_contact_template() -> str:
    """Return the default contact template."""
    return (Path(__file__).parent / "contract_contact_template.jinja").read_text()


@frappe.whitelist()
def render_contact(contact_name: str, contact_doctype: str = "Contact") -> str | None:
    """Render a contact using the Contract Contact Template.

    Accepts both the Frappe Contact doctype and the Company Official doctype.
    """
    doc = frappe.get_cached_doc(contact_doctype, contact_name).as_dict()

    template = frappe.db.get_single_value(
        "Contract Contact Template", "template")
    if not template:
        return None

    return frappe.render_template(template, doc)
