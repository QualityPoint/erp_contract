// Copyright (c) 2026, QualityPoint and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERP Contract", {
    setup(frm) {
        frm.set_query("company_primary_official", function () {
            return {
                filters: {
                    "company": frm.doc.company,
                    "is_primary_official": 1
                }
            };
        });

        frm.set_query("company_address", function () {
            return {
                filters: [
                    ["link_doctype", "=", "Company"],
                    ["link_name", "=", frm.doc.company]
                ]
            };
        });

        frm.set_query("customer_primary_official", function () {
            return {
                filters: [
                    ["link_doctype", "=", "Customer"],
                    ["link_name", "=", frm.doc.customer]
                ]
            };
        });

        frm.set_query("customer_address", function () {
            return {
                filters: [
                    ["link_doctype", "=", "Customer"],
                    ["link_name", "=", frm.doc.customer]
                ]
            };
        });

        frm.set_query("sales_order", function () {
            return {
                filters: {
                    "company": frm.doc.company,
                    "customer": frm.doc.customer,
                    "docstatus": 1
                }
            };
        });

        frm.set_query("representative", "customer_representatives", function () {
            return {
                filters: [
                    ["link_doctype", "=", "Customer"],
                    ["link_name", "=", frm.doc.customer]
                ]
            };
        });

        frm.set_query("representative", "company_representatives", function () {
            return {
                filters: {
                    "company": frm.doc.company
                }
            };
        });

        get_deposit_reference_document(frm);
    },

    refresh(frm) {
        // Re-render display fields on load if source fields are already set
        if (frm.doc.company_primary_official) {
            render_contact_display(frm, frm.doc.company_primary_official, "Company Official", "official_contact_display");
        }
        if (frm.doc.company_address) {
            render_address_display(frm, frm.doc.company_address, "company_address_display");
        }
        if (frm.doc.customer_primary_official) {
            render_contact_display(frm, frm.doc.customer_primary_official, "Contact", "customer_contact_display");
        }
        if (frm.doc.customer_address) {
            render_address_display(frm, frm.doc.customer_address, "customer_address_display");
        }

        if (frm.doc.docstatus === 1) {
            add_status_action_buttons(frm);
        }
    },

    onload(frm) {
        // Get default template and populate terms
        frappe.call({
            method: "erp_contract.utils.utils.get_default_terms_template",
            callback: function (r) {
                if (r.message) {
                    frm.set_value("terms_template", r.message);
                }
            }
        });
    },

    company(frm) {
        if (frm.doc.company) {
            // Fetch default company address via Dynamic Link
            frappe.call({
                method: "erp_contract.utils.utils.get_default_address",
                args: {
                    link_doctype: "Company",
                    link_name: frm.doc.company
                },
                callback: function (r) {
                    frm.set_value("company_address", r.message || "");
                }
            });
            // Fetch default company official (server-side)
            frappe.call({
                method: "erp_contract.utils.utils.get_default_company_official",
                args: {
                    company: frm.doc.company
                },
                callback: function (r) {
                    frm.set_value("company_primary_official", r.message || "");
                }
            });
        } else {
            frm.set_value("company_address", "");
            frm.set_value("company_address_display", "");
            frm.set_value("company_primary_official", "");
            frm.set_value("official_contact_display", "");
        }
    },

    customer(frm) {
        if (frm.doc.customer) {
            frappe.call({
                method: "erp_contract.utils.utils.get_default_contact",
                args: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                },
                callback: function (r) {
                    frm.set_value("customer_primary_official", r.message || "");
                }
            });
            frappe.call({
                method: "erp_contract.utils.utils.get_default_address",
                args: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                },
                callback: function (r) {
                    frm.set_value("customer_address", r.message || "");
                }
            });
        } else {
            frm.set_value("customer_primary_official", "");
            frm.set_value("customer_contact_display", "");
            frm.set_value("customer_address", "");
            frm.set_value("customer_address_display", "");
        }
    },

    company_primary_official(frm) {
        if (frm.doc.company_primary_official) {
            render_contact_display(frm, frm.doc.company_primary_official, "Company Official", "official_contact_display");
        } else {
            frm.set_value("official_contact_display", "");
        }
    },

    company_address(frm) {
        if (frm.doc.company_address) {
            render_address_display(frm, frm.doc.company_address, "company_address_display");
        } else {
            frm.set_value("company_address_display", "");
        }
    },

    customer_primary_official(frm) {
        if (frm.doc.customer_primary_official) {
            render_contact_display(frm, frm.doc.customer_primary_official, "Contact", "customer_contact_display");
        } else {
            frm.set_value("customer_contact_display", "");
        }
    },

    customer_address(frm) {
        if (frm.doc.customer_address) {
            render_address_display(frm, frm.doc.customer_address, "customer_address_display");
        } else {
            frm.set_value("customer_address_display", "");
        }
    },

    start_date(frm) {
        update_contract_duration(frm);
    },

    end_date(frm) {
        update_contract_duration(frm);
    },

    duration_uom(frm) {
        update_contract_duration(frm);
    },

    terms_template: function (frm) {
        if (frm.doc.terms_template) {
            get_contract_terms(frm, frm.doc.terms_template);
        }
    },

    advance_payment_entry: function (frm) {
        if (frm.doc.advance_payment_entry) {
            frappe.call({
                method: "erp_contract.utils.utils.get_payment_entry_details",
                args: {
                    deposit_reference: frm.doc.advance_payment_entry
                },
                callback: function (r) {
                    if (r.message) {
                        let data = r.message;
                        frm.set_value({
                            'advance_amount': data.paid_amount,
                            'advance_amount_in_words': data.advance_amount_in_words,
                        });
                    }
                }
            });
        } else {
            frm.set_value({
                'advance_amount': 0,
                'advance_amount_in_words': '',
                'amount_due': frm.doc.apply_installment_payment ? flt(frm.doc.net_total) : 0,
            });
            if (frm.doc.apply_installment_payment && frm.doc.payment_schedule && frm.doc.payment_schedule.length) {
                frm.clear_table('payment_schedule');
                frm.refresh_field('payment_schedule');
            }
        }
    },

    sales_order: function (frm) {
        if (frm.doc.sales_order) {
            frappe.call({
                method: "erp_contract.utils.utils.get_reference_document_price_details",
                args: {
                    doctype: "Sales Order",
                    document_name: frm.doc.sales_order
                },
                callback: function (r) {
                    if (r.message) {
                        let data = r.message;
                        frm.set_value({
                            'currency': data.currency,
                            'total_taxes_and_charges': data.total_taxes_and_charges,
                            'net_total': data.net_total,
                            'net_total_in_words': data.net_total_in_words,
                        });
                        update_amount_due(frm);
                    }
                }
            });
        } else {
            frm.set_value({
                'currency': '',
                'total_taxes_and_charges': 0,
                'net_total': 0,
                'net_total_in_words': '',
            });
            update_amount_due(frm);
        }
    },

    payment_periodicity: function (frm) {
        const counts = { 'Monthly': 12, 'Quarterly': 4, 'Half-Yearly': 2, 'Yearly': 1 };
        if (frm.doc.payment_periodicity && counts[frm.doc.payment_periodicity]) {
            frm.set_value('installment_count', counts[frm.doc.payment_periodicity]);
        }
    },

    apply_installment_payment: function (frm) {
        if (!frm.doc.apply_installment_payment) {
            frm.set_value('amount_due', 0);
            frm.clear_table('payment_schedule');
            frm.refresh_field('payment_schedule');
        } else {
            update_amount_due(frm);
        }
    },

    create_schedule: function (frm) {
        if (!frm.doc.due_start_date || !frm.doc.installment_count || !frm.doc.payment_periodicity) {
            frappe.msgprint(
                __('Please set Due Start Date, Instalment Count, and Payment Periodicity first.')
            );
            return;
        }
        if (!frm.doc.amount_due || frm.doc.amount_due <= 0) {
            frappe.msgprint(
                __('Amount Due must be greater than zero. Please link a Sales Order first.')
            );
            return;
        }

        frappe.call({
            method: 'erp_contract.utils.utils.create_payment_schedule',
            args: {
                due_start_date: frm.doc.due_start_date,
                installment_count: frm.doc.installment_count,
                payment_periodicity: frm.doc.payment_periodicity,
                amount_due: frm.doc.amount_due,
                currency: frm.doc.currency,
            },
            callback: function (r) {
                if (r.message) {
                    frm.clear_table('payment_schedule');
                    r.message.forEach(function (row) {
                        let d = frm.add_child('payment_schedule');
                        d.installment_amount = row.installment_amount;
                        d.installment_in_words = row.installment_in_words;
                        d.installment_due_date = row.installment_due_date;
                    });
                    frm.refresh_field('payment_schedule');
                }
            }
        });
    }
});

function update_amount_due(frm) {
    if (!frm.doc.apply_installment_payment) return;
    let amount_due = flt(frm.doc.net_total) - flt(frm.doc.advance_amount);
    frm.set_value('amount_due', amount_due > 0 ? amount_due : 0);
}

function get_contract_terms(frm, template_name) {
    if (!template_name) return;

    frappe.call({
        method: "erp_contract.utils.utils.get_terms_template",
        args: {
            template_name: template_name,
            doc: frm.doc,
        },
        callback: function (r) {
            if (r && r.message) {
                // Clear existing rows first
                frm.clear_table("contract_terms");

                let data = r.message;
                data.forEach((element) => {
                    let d = frm.add_child("contract_terms");
                    d.title_primary = element.title_primary;
                    d.terms_and_conditions_primary = element.terms_and_conditions_primary;
                    d.title_foreign = element.title_foreign;
                    d.terms_and_conditions_foreign = element.terms_and_conditions_foreign;
                });

                frm.refresh_field("contract_terms");
            }
        },
    });
}

function update_contract_duration(frm) {
    if (frm.doc.contract_category !== "Duration-Based") return;

    if (frm.doc.start_date && frm.doc.end_date && frm.doc.duration_uom) {
        frappe.call({
            method: "erp_contract.utils.utils.calculate_contract_duration",
            args: {
                start_date: frm.doc.start_date,
                end_date: frm.doc.end_date,
                duration_uom: frm.doc.duration_uom
            },
            callback: function (r) {
                frm.set_value("contract_duration", r.message ?? 0);
            }
        });
    } else {
        frm.set_value("contract_duration", 0);
    }
}

function render_contact_display(frm, contact_name, contact_doctype, display_field) {
    frappe.call({
        method: "erp_contract.erp_contract.doctype.contract_contact_template.contract_contact_template.render_contact",
        args: {
            contact_name: contact_name,
            contact_doctype: contact_doctype
        },
        callback: function (r) {
            frm.set_value(display_field, r.message || "");
        },
    });
}

function get_deposit_reference_document(frm) {
    frm.set_query('advance_payment_entry', function (doc) {
        if (!doc.company || !doc.customer || !doc.sales_order) {
            return {
                filters: {
                    'name': 'No Deposit Reference Document'
                }
            };
        }

        return {
            query: "erp_contract.utils.utils.get_advance_payment_entries",
            filters: {
                'company': doc.company,
                'customer': doc.customer,
                'reference_doctype': 'Sales Order',
                'reference_name': doc.sales_order,
                'current_contract': doc.name,
            }
        };
    });
}

function render_address_display(frm, address_name, display_field) {
    frappe.call({
        method: "frappe.contacts.doctype.address.address.get_address_display",
        args: {
            address_dict: address_name
        },
        callback: function (r) {
            frm.set_value(display_field, r.message || "");
        },
    });
}

function add_status_action_buttons(frm) {
    const status = frm.doc.status;
    const is_duration = frm.doc.contract_category === "Duration-Based";
    const is_milestone = frm.doc.contract_category === "Milestone-Based";
    const GROUP = __("Actions");

    // On Hold — available when Active, for both categories
    if (status === "Active") {
        frm.add_custom_button(__("On Hold"), () => set_contract_status(frm, "On Hold"), GROUP);
    }

    // Resume — available when On Hold, for both categories
    if (status === "On Hold") {
        frm.add_custom_button(__("Resume"), () => set_contract_status(frm, "Active"), GROUP);
    }

    // Completed — only Milestone-Based, when Active or On Hold
    if (is_milestone && ["Active", "On Hold"].includes(status)) {
        frm.add_custom_button(__("Mark Completed"), () => set_contract_status(frm, "Completed"), GROUP);
    }

    // Terminated — available for both categories when Active, On Hold, or (Duration-Based) Inactive
    const can_terminate = ["Active", "On Hold"].includes(status) ||
        (is_duration && status === "Inactive");
    if (can_terminate) {
        frm.add_custom_button(__("Terminate"), () => set_contract_status(frm, "Terminated"), GROUP);
    }
}

function set_contract_status(frm, new_status) {
    frappe.prompt(
        [
            {
                fieldname: "remarks",
                fieldtype: "Text",
                label: __("Remarks"),
                reqd: 1,
                description: __("Required — explain why the status is being changed to {0}.", [new_status]),
            },
        ],
        (values) => {
            frappe.call({
                method: "frappe.client.set_value",
                args: {
                    doctype: "ERP Contract",
                    name: frm.doc.name,
                    fieldname: {
                        status: new_status,
                        remarks: values.remarks
                    },
                },
                callback: () => frm.reload_doc(),
            });
        },
        __("Set Status to {0}", [new_status]),
        __("Confirm")
    );
}
