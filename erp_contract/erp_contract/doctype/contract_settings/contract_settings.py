# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.user import get_users_with_role


class ContractSettings(Document):
    def validate(self):
        self.validate_approval_roles()

    def validate_approval_roles(self):
        """
        Validate the hierarchical approval chain at settings-save time so
        misconfigurations surface here rather than when an end-user clicks
        "Request Approval".

        Enforced when ``apply_hierarchical_approvals`` is on:
          - precedence values are unique
          - each role appears at most once
          - every role has at least one enabled user to act on it
        """
        if not self.apply_hierarchical_approvals:
            return

        seen_precedence: set[str] = set()
        seen_role: set[str] = set()
        for row in self.roles:
            if row.precedence in seen_precedence:
                frappe.throw(
                    _("Row #{0}: precedence {1} is used more than once. "
                      "Each approval step must have a unique precedence.").format(
                        row.idx, row.precedence
                    )
                )
            seen_precedence.add(row.precedence)

            if row.role in seen_role:
                frappe.throw(
                    _("Row #{0}: role {1} appears more than once. "
                      "Each role may define only one approval step.").format(
                        row.idx, frappe.bold(row.role)
                    )
                )
            seen_role.add(row.role)

            if not get_users_with_role(row.role):
                frappe.throw(
                    _("Row #{0}: no active user holds the {1} role. "
                      "Assign it to at least one user before enabling this step.").format(
                        row.idx, frappe.bold(row.role)
                    )
                )
