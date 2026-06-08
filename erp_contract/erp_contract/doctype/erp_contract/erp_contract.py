# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.jinja import validate_template
from erp_contract.utils.contract_status import get_contract_status
from erp_contract.utils.contract import calculate_contract_duration
from erp_contract.utils.payment import recalculate_contract_payment
from erp_contract.utils.approval import assert_approval_chain_complete


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
        self.validate_company_primary_official()
        self.validate_contract_duration()
        self.validate_contract_terms()
        self.validate_installment_payment()
        self.validate_signed_contract_attachment()

    def before_submit(self):
        assert_approval_chain_complete(self)
        self.update_contract_status()

    def on_submit(self):
        if self.sales_order:
            recalculate_contract_payment({self.sales_order})

    def before_update_after_submit(self):
        # is_signed is allow_on_submit, so signing happens here (validate() does not run)
        self.validate_signed_contract_attachment()
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

    def validate_signed_contract_attachment(self):
        """When Contract Settings → Require Signed Contract Attachment is on, the
        signed contract file must be uploaded before the contract may be marked
        as signed (is_signed)."""
        if not self.is_signed or self.signed_contract:
            return
        if not frappe.db.get_single_value("Contract Settings", "require_signed_contract_attachment"):
            return
        frappe.throw(
            _("Please attach the signed contract document before marking this contract as signed."),
            title=_("Signed Contract Required"),
        )

    def validate_sales_order_uniqueness(self):
        """Ensure the Sales Order is not already linked to another submitted ERP Contract."""
        self._assert_field_unique("sales_order", _("Sales Order"))

    def validate_advance_payment_uniqueness(self):
        """Ensure the Advance Payment Entry is not already linked to another submitted ERP Contract."""
        self._assert_field_unique(
            "advance_payment_entry", _("Advance Payment Entry"))

    def validate_company_primary_official(self):
        """Ensure the selected Company Primary Official has is_primary_official checked."""
        if not self.company_primary_official:
            return
        is_primary = frappe.db.get_value(
            "Company Official", self.company_primary_official, "is_primary_official"
        )
        if not is_primary:
            frappe.throw(
                _("Company Primary Official {0} does not have \"Is Primary Official\" checked.").format(
                    frappe.bold(self.company_primary_official)
                )
            )

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

        self._assert_no_duplicate_representatives(
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


@frappe.whitelist()
def renew_contract(contract_name, contract_date, start_date, end_date, duration_uom, sales_order):
    """
    Renew a submitted Duration-Based ERP Contract in-place.

    Steps:
      1. Guard: category, docstatus, status, grace window, new start_date > current end_date.
      2. Validate the new Sales Order (unused by this or any other submitted contract,
         same company/customer, submitted).
      3. Append the current period — including its Sales Order — to contract_records (archive).
      4. Apply new period values, attach the new Sales Order and its financials,
         reset signature/advance/installment fields.
      5. save() via ignore_validate_update_after_submit flag.

    contract_duration is recomputed server-side from the dates; the client value
    is never trusted.
    """
    from dateutil.relativedelta import relativedelta
    from frappe.utils import getdate, nowdate, add_days
    from erp_contract.utils.contract import calculate_contract_duration
    from erp_contract.utils.party import get_reference_document_price_details

    doc = frappe.get_doc("ERP Contract", contract_name)

    # --- Permission check ---
    if not frappe.has_permission("ERP Contract", "write", doc=doc):
        frappe.throw(
            _("You do not have permission to renew this contract."), frappe.PermissionError)

    # --- Input validation ---
    if duration_uom not in ("Day", "Month", "Year"):
        frappe.throw(_("Invalid Duration UOM: {0}").format(duration_uom))

    # --- Guards ---
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted contracts can be renewed."))
    if doc.contract_category != "Duration-Based":
        frappe.throw(_("Only Duration-Based contracts can be renewed."))
    if doc.status not in ("Active", "Inactive"):
        frappe.throw(
            _("Contract cannot be renewed in its current status ({0}).").format(doc.status))

    # Grace window guard (server-side mirror of client check)
    grace_period = frappe.db.get_single_value(
        "Contract Settings", "renewal_grace_period") or 1
    grace_uom = frappe.db.get_single_value(
        "Contract Settings", "grace_period_uom") or "Month"
    today = getdate(nowdate())
    current_end = getdate(doc.end_date)
    window_start = (
        current_end - relativedelta(months=int(grace_period))
        if grace_uom == "Month"
        else add_days(current_end, -int(grace_period))
    )
    if today < window_start:
        frappe.throw(_("The renewal window has not opened yet. It opens on {0}.").format(
            frappe.format(window_start, {"fieldtype": "Date"})
        ))

    # New start must be strictly after the current end_date (no overlap, no same-day handover)
    if getdate(start_date) <= current_end:
        frappe.throw(_("New Start Date ({0}) must be after the current End Date ({1}).").format(
            frappe.format(getdate(start_date), {"fieldtype": "Date"}),
            frappe.format(current_end, {"fieldtype": "Date"}),
        ))

    # Recompute duration server-side (also enforces end_date >= start_date)
    new_duration = calculate_contract_duration(start_date, end_date, duration_uom)

    # --- Validate the new Sales Order ---
    if not sales_order:
        frappe.throw(_("A new Sales Order is required to renew the contract."))

    used_sales_orders = {doc.sales_order} | {
        r.sales_order for r in doc.contract_records if r.sales_order
    }
    if sales_order in used_sales_orders:
        frappe.throw(
            _("Sales Order {0} has already been used by this contract. "
              "Select a Sales Order for the new period.").format(frappe.bold(sales_order))
        )

    so = frappe.db.get_value(
        "Sales Order", sales_order,
        ["company", "customer", "docstatus"], as_dict=True,
    )
    if not so:
        frappe.throw(_("Sales Order {0} does not exist.").format(frappe.bold(sales_order)))
    if so.docstatus != 1:
        frappe.throw(_("Sales Order {0} is not submitted.").format(frappe.bold(sales_order)))
    if so.company != doc.company:
        frappe.throw(_("Sales Order {0} does not belong to Company {1}.").format(
            frappe.bold(sales_order), frappe.bold(doc.company)))
    if so.customer != doc.customer:
        frappe.throw(_("Sales Order {0} does not belong to Customer {1}.").format(
            frappe.bold(sales_order), frappe.bold(doc.customer)))

    # Mirror validate_sales_order_uniqueness (skipped during update_after_submit):
    # the SO must not be linked to any *other* submitted contract.
    linked = frappe.db.get_value(
        "ERP Contract",
        {"sales_order": sales_order, "docstatus": 1, "name": ("!=", doc.name)},
        "name",
    )
    if linked:
        frappe.throw(
            _("Sales Order {0} is already linked to submitted Contract {1}.").format(
                frappe.bold(sales_order),
                frappe.utils.get_link_to_form("ERP Contract", linked),
            )
        )

    # --- Archive current period (including its Sales Order) ---
    doc.append("contract_records", {
        "contract_date": doc.contract_date,
        "start_date": doc.start_date,
        "end_date": doc.end_date,
        "duration_uom": doc.duration_uom,
        "contract_duration": doc.contract_duration,
        "archived_contract": doc.signed_contract,
        "sales_order": doc.sales_order,
    })

    # --- New period ---
    doc.contract_date = contract_date
    doc.start_date = start_date
    doc.end_date = end_date
    doc.duration_uom = duration_uom
    doc.contract_duration = new_duration

    # --- Signature reset ---
    doc.is_signed = 0
    doc.signed_contract = ""
    doc.signee = ""
    doc.signed_on = None
    doc.ip_address = ""
    doc.signee_customer = ""
    doc.signed_by_customer = ""

    # --- New Sales Order & its financials ---
    price = get_reference_document_price_details("Sales Order", sales_order)
    doc.sales_order = sales_order
    doc.currency = price["currency"]
    doc.net_total = price["net_total"]
    doc.net_total_in_words = price["net_total_in_words"]
    doc.total_taxes_and_charges = price["total_taxes_and_charges"]

    # --- Advance payment reset ---
    doc.advance_payment_entry = ""
    doc.advance_amount = 0
    doc.advance_amount_in_words = ""

    # --- Installment reset (explicit — before_validate does NOT run on update_after_submit) ---
    doc.apply_installment_payment = 0
    doc.due_start_date = None
    doc.payment_periodicity = ""
    doc.amount_due = 0
    doc.installment_count = 0
    doc.payment_schedule = []

    # --- Payment status reset ---
    doc.per_payment = 0
    doc.payment_status = "Unpaid"

    # --- Renewal flag ---
    doc.is_renewed = 1

    # --- Save (bypasses allow_on_submit; triggers before_update_after_submit → status = "Unsigned") ---
    doc.flags.ignore_validate_update_after_submit = True
    doc.save()
