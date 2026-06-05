# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CompanyOfficial(Document):
	pass


@frappe.whitelist()
def get_employee_details(employee):
	return frappe.db.get_value(
		"Employee",
		employee,
		["salutation", "designation", "cell_number", "company_email"],
		as_dict=True,
	)
