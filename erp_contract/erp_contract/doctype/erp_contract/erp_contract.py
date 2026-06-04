# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.jinja import validate_template
from erp_contract.utils.utils import calculate_contract_duration, get_contract_status


class ERPContract(Document):
    def before_validate(self):
        self.clear_duration_fields()
        self.clear_installment_fields()
        self.clear_schedule_on_advance_removed()

    def clear_duration_fields(self):
        if self.contract_category != "Duration-Based":
            self.end_date = None
            self.duration_uom = ""
            self.contract_duration = 0

    def clear_installment_fields(self):
        if not self.apply_installment_payment:
            self.due_start_date = None
            self.amount_due = 0
            self.installment_count = 0
            self.payment_periodicity = ""
            self.payment_schedule = []

    def clear_schedule_on_advance_removed(self):
        if self.apply_installment_payment and not self.advance_payment_entry and self.payment_schedule:
            self.payment_schedule = []

    def validate(self):
        self.validate_sales_order_uniqueness()
        self.validate_advance_payment_uniqueness()
        self.validate_customer_representatives()
        self.validate_company_representatives()
        self.validate_contract_duration()
        self.validate_contract_terms()
        self.render_contract_terms()
        self.validate_installment_payment()

    def on_submit(self):
        self.update_contract_status()

    def before_update_after_submit(self):
        # Preserve manual statuses — only recalculate auto-driven ones
        if self.status not in ("On Hold", "Completed", "Terminated"):
            self.update_contract_status()

    def on_cancel(self):
        self.db_set("status", "Cancelled")

    def update_contract_status(self):
        self.status = get_contract_status(
            is_signed=self.is_signed,
            contract_category=self.contract_category,
            start_date=self.start_date,
            end_date=self.end_date,
        )

    def validate_sales_order_uniqueness(self):
        """Ensure the Sales Order is not already linked to another submitted ERP Contract."""
        self._assert_field_unique("sales_order", _("Sales Order"))

    def validate_advance_payment_uniqueness(self):
        """Ensure the Advance Payment Entry is not already linked to another submitted ERP Contract."""
        self._assert_field_unique(
            "advance_payment_entry", _("Advance Payment Entry"))

    def _assert_field_unique(self, fieldname, label):
        value = self.get(fieldname)
        if not value:
            return
        existing = frappe.db.get_value(
            "ERP Contract",
            {fieldname: value, "docstatus": 1, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                _("{0} {1} is already linked to submitted Contract {2}.").format(
                    label,
                    frappe.bold(value),
                    frappe.utils.get_link_to_form("ERP Contract", existing),
                )
            )

    def validate_customer_representatives(self):
        """Ensure no duplicate representatives and all belong to the selected customer."""
        if not self.customer_representatives:
            return

        seen = self._assert_no_duplicate_representatives(
            self.customer_representatives, _("Customer Representatives")
        )

        for row in self.customer_representatives:
            if not row.representative:
                continue

            # Verify the Contact is linked to the selected customer via Dynamic Link
            linked = frappe.db.exists(
                "Dynamic Link",
                {
                    "parenttype": "Contact",
                    "parent": row.representative,
                    "link_doctype": "Customer",
                    "link_name": self.customer,
                },
            )
            if not linked:
                frappe.throw(
                    _("Row #{0}: Representative {1} does not belong to Customer {2}.").format(
                        row.idx, frappe.bold(
                            row.full_name or row.representative), frappe.bold(self.customer)
                    )
                )

    def validate_company_representatives(self):
        """Ensure no duplicate representatives and all belong to the selected company."""
        if not self.company_representatives:
            return

        self._assert_no_duplicate_representatives(
            self.company_representatives, _("Company Representatives")
        )

        for row in self.company_representatives:
            if not row.representative:
                continue

            # Verify the Company Official belongs to the selected company
            official_company = frappe.db.get_value(
                "Company Official", row.representative, "company"
            )
            if official_company != self.company:
                frappe.throw(
                    _("Row #{0}: Representative {1} does not belong to Company {2}.").format(
                        row.idx, frappe.bold(
                            row.full_name or row.representative), frappe.bold(self.company)
                    )
                )

            # Verify the representative is not the same as the Company Primary Official
            if row.representative == self.company_primary_official:
                frappe.throw(
                    _("Row #{0}: Representative {1} is already set as the Company Primary Official.").format(
                        row.idx, frappe.bold(
                            row.full_name or row.representative)
                    )
                )

    def _assert_no_duplicate_representatives(self, rows, table_label):
        seen = set()
        for row in rows:
            if not row.representative:
                continue
            if row.representative in seen:
                frappe.throw(
                    _("Row #{0}: Representative {1} is duplicated in {2}.").format(
                        row.idx, frappe.bold(
                            row.full_name or row.representative), table_label
                    )
                )
            seen.add(row.representative)
        return seen

    def validate_contract_duration(self):
        """Compute and set contract_duration from start_date, end_date, and duration_uom."""
        if self.contract_category != "Duration-Based":
            return

        if self.start_date and self.end_date and self.duration_uom:
            self.contract_duration = calculate_contract_duration(
                self.start_date, self.end_date, self.duration_uom
            )

    def validate_contract_terms(self):
        """Validate the terms_and_conditions field in the contract_terms child table."""
        if not self.contract_terms:
            frappe.throw(_("Contract Terms cannot be empty"))

        for term in self.contract_terms:
            if term.terms_and_conditions_primary:
                validate_template(term.terms_and_conditions_primary)
            if term.terms_and_conditions_foreign:
                validate_template(term.terms_and_conditions_foreign)

    def render_contract_terms(self):
        """Render Jinja variables in contract_terms child table using the current document as context."""
        doc_context = self.as_dict()
        for term in self.contract_terms:
            if term.terms_and_conditions_primary:
                term.terms_and_conditions_primary = frappe.render_template(
                    term.terms_and_conditions_primary, doc_context
                )
            if term.terms_and_conditions_foreign:
                term.terms_and_conditions_foreign = frappe.render_template(
                    term.terms_and_conditions_foreign, doc_context
                )

    def validate_installment_payment(self):
        from frappe.utils import flt

        if not self.apply_installment_payment:
            return

        if not self.payment_schedule:
            frappe.throw(
                _("Payment Schedule is empty"))

        total = sum(flt(row.installment_amount)
                    for row in self.payment_schedule)
        expected = flt(flt(self.net_total) - flt(self.advance_amount), 2)
        if abs(total - expected) > 0.1:
            frappe.throw(
                _("Total installment amount ({0}) does not match Amount Due ({1})").format(
                    flt(total, 2), expected
                )
            )
