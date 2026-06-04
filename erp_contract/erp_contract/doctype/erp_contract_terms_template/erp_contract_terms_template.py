# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.jinja import validate_template


class ERPContractTermsTemplate(Document):
    def validate(self):
        self.validate_default_template()
        self.validate_contract_terms()

    def validate_default_template(self):
        if not self.is_default and not self._get_previous_default():
            self.is_default = 1
            if frappe.is_setup_complete():
                frappe.msgprint(
                    _("Setting this Contract Terms Template as default as there is no other default"))

    def validate_contract_terms(self):
        """validate the terms_and_conditions field in the terms child table"""
        if not self.terms:
            frappe.throw(_("Template Terms cannot be empty"))

        for term in self.terms:
            if term.terms_and_conditions_primary:
                validate_template(term.terms_and_conditions_primary)
            if term.terms_and_conditions_foreign:
                validate_template(term.terms_and_conditions_foreign)

    def on_update(self):
        if self.is_default and (previous_default := self._get_previous_default()):
            frappe.db.set_value("ERP Contract Terms Template",
                                previous_default, "is_default", 0)

    def on_trash(self):
        if self.is_default:
            frappe.throw(
                _("Default ERP Contract Terms Template cannot be deleted"))

    def _get_previous_default(self) -> str | None:
        return frappe.db.get_value("ERP Contract Terms Template", {"is_default": 1, "name": ("!=", self.name)})
