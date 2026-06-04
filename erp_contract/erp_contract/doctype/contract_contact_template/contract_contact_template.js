// Copyright (c) 2026, QualityPoint and contributors
// For license information, please see license.txt

frappe.ui.form.on("Contract Contact Template", {
    refresh(frm) {
        frm.add_custom_button(__("Reset to Default"), function () {
            frappe.call({
                method: "erp_contract.erp_contract.doctype.contract_contact_template.contract_contact_template.get_default_contact_template",
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("template", r.message);
                    }
                },
            });
        });
    },
});
