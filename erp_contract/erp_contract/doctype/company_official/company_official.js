// Copyright (c) 2026, QualityPoint and contributors
// For license information, please see license.txt

frappe.ui.form.on("Company Official", {
    employee(frm) {
        if (frm.doc.employee) {
            frappe.call({
                method: "erp_contract.erp_contract.doctype.company_official.company_official.get_employee_details",
                args: {
                    employee: frm.doc.employee
                },
                callback({ message }) {
                    if (!message) return;
                    frm.set_value({
                        "salutation": message.salutation,
                        "designation": message.designation,
                        "mobile_no": message.cell_number,
                        "email_id": message.company_email
                    });
                },
            });
        } else {
            ["salutation", "designation", "mobile_no", "email_id"].forEach((f) =>
                frm.set_value(f, null)
            );
        }
    },
});
