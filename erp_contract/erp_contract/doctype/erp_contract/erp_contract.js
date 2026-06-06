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
            if (!frm._renewal_settings) {
                frappe.call({
                    method: "erp_contract.utils.contract.get_renewal_settings",
                    callback(r) {
                        if (r.message) frm._renewal_settings = r.message;
                        add_status_action_buttons(frm);
                    }
                });
            } else {
                add_status_action_buttons(frm);
            }
        }

        // "Create" button group — Payment / Payment Request (any submitted contract),
        // plus Advance / Installment Payment (renewed contracts only)
        if (frm.doc.docstatus === 1) {
            add_create_buttons(frm);
        }

        // Hierarchical approval UI — draft and submitted (never on new or cancelled forms)
        if (!frm.is_new() && frm.doc.docstatus !== 2) {
            add_approval_buttons(frm);
        }
    },

    onload(frm) {
        // Only set the default terms template for new (unsaved) documents.
        // For existing contracts the saved value must not be overwritten.
        if (frm.is_new()) {
            frappe.call({
                method: "erp_contract.utils.contract.get_default_terms_template",
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("terms_template", r.message);
                    }
                }
            });
        }
    },

    company(frm) {
        if (frm.doc.company) {
            // Fetch default company address via Dynamic Link
            frappe.call({
                method: "erp_contract.utils.party.get_default_address",
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
                method: "erp_contract.utils.party.get_default_company_official",
                args: {
                    company: frm.doc.company
                },
                callback: function (r) {
                    frm.set_value("company_primary_official", r.message || "");
                }
            });
        } else {
            frm.set_value({
                "company_address": "",
                "company_address_display": "",
                "company_primary_official": "",
                "official_contact_display": ""
            });
        }
    },

    customer(frm) {
        if (frm.doc.customer) {
            frappe.call({
                method: "erp_contract.utils.party.get_default_contact",
                args: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                },
                callback: function (r) {
                    frm.set_value("customer_primary_official", r.message || "");
                }
            });
            frappe.call({
                method: "erp_contract.utils.party.get_default_address",
                args: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                },
                callback: function (r) {
                    frm.set_value("customer_address", r.message || "");
                }
            });
        } else {
            frm.set_value({
                "customer_primary_official": "",
                "customer_contact_display": "",
                "customer_address": "",
                "customer_address_display": ""
            });
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
                method: "erp_contract.utils.payment.get_payment_entry_details",
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
                method: "erp_contract.utils.party.get_reference_document_price_details",
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
            method: 'erp_contract.utils.payment.create_payment_schedule',
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
        method: "erp_contract.utils.contract.get_terms_template",
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
            method: "erp_contract.utils.contract.calculate_contract_duration",
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
            query: "erp_contract.utils.payment.get_advance_payment_entries",
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

    // Renew — Duration-Based only, when Active or Inactive, and within grace window
    if (is_duration && ["Active", "Inactive"].includes(status) && is_in_renewal_window(frm)) {
        frm.add_custom_button(__("Renew"), () => open_renewal_dialog(frm), GROUP);
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

function is_in_renewal_window(frm) {
    const settings = frm._renewal_settings;
    if (!settings || !frm.doc.end_date) return false;

    const grace = parseInt(settings.renewal_grace_period) || 1;
    const uom = settings.grace_period_uom || "Month";
    let window_start;

    if (uom === "Month") {
        window_start = frappe.datetime.add_months(frm.doc.end_date, -grace);
    } else {
        window_start = frappe.datetime.add_days(frm.doc.end_date, -grace);
    }

    return frappe.datetime.get_today() >= window_start;
}

function open_renewal_dialog(frm) {
    // Sales Orders already consumed by this contract (current + archived periods)
    // must not be selectable for the new period.
    const used_sales_orders = [];
    if (frm.doc.sales_order) used_sales_orders.push(frm.doc.sales_order);
    (frm.doc.contract_records || []).forEach((r) => {
        if (r.sales_order) used_sales_orders.push(r.sales_order);
    });

    const dialog = new frappe.ui.Dialog({
        title: __("Renew Contract"),
        fields: [

            {
                fieldname: "contract_date",
                fieldtype: "Date",
                label: __("Contract Date"),
                reqd: 1,
                description: __("Date of new contract conclusion"),
            },
            { fieldname: "sb0", fieldtype: "Section Break" },
            {
                fieldname: "start_date",
                fieldtype: "Date",
                label: __("Start Date"),
                reqd: 1,
                description: __("Must be after the current End Date ({0}).", [
                    frappe.format(frm.doc.end_date, { fieldtype: "Date" }),
                ]),
            },
            {
                fieldname: "end_date",
                fieldtype: "Date",
                label: __("End Date"),
                reqd: 1,
            },
            { fieldname: "cb2", fieldtype: "Column Break" },
            {
                fieldname: "duration_uom",
                fieldtype: "Select",
                label: __("Duration UOM"),
                options: "\nDay\nMonth\nYear",
                default: frm.doc.duration_uom || "Month",
                reqd: 1,
            },
            {
                fieldname: "contract_duration",
                fieldtype: "Float",
                label: __("Contract Duration"),
                read_only: 1,
                precision: 2,
            },
            { fieldname: "sb2", fieldtype: "Section Break" },
            {
                fieldname: "sales_order",
                fieldtype: "Link",
                label: __("New Sales Order"),
                options: "Sales Order",
                reqd: 1,
                description: __("Select a Sales Order not yet used by this contract."),
                get_query: () => ({
                    filters: {
                        company: frm.doc.company,
                        customer: frm.doc.customer,
                        docstatus: 1,
                        ...(used_sales_orders.length
                            ? { name: ["not in", used_sales_orders] }
                            : {}),
                    },
                }),
            },
        ],
        primary_action_label: __("Renew"),
        primary_action(values) {
            if (frm.doc.end_date && values.start_date <= frm.doc.end_date) {
                frappe.msgprint(
                    __("New Start Date must be after the current End Date ({0}).", [
                        frappe.format(frm.doc.end_date, { fieldtype: "Date" }),
                    ])
                );
                return;
            }
            frappe.call({
                method: "erp_contract.erp_contract.doctype.erp_contract.erp_contract.renew_contract",
                args: {
                    contract_name: frm.doc.name,
                    contract_date: values.contract_date,
                    start_date: values.start_date,
                    end_date: values.end_date,
                    duration_uom: values.duration_uom,
                    sales_order: values.sales_order,
                },
                freeze: true,
                freeze_message: __("Renewing contract..."),
                callback() {
                    dialog.hide();
                    frm.reload_doc();
                },
            });
        },
    });

    // Auto-calculate duration when any of the three fields change
    const recalc_duration = () => {
        const s = dialog.get_value("start_date");
        const e = dialog.get_value("end_date");
        const uom = dialog.get_value("duration_uom");
        if (s && e && uom) {
            frappe.call({
                method: "erp_contract.utils.contract.calculate_contract_duration",
                args: { start_date: s, end_date: e, duration_uom: uom },
                callback(r) {
                    dialog.set_value("contract_duration", r.message ?? 0);
                },
            });
        }
    };

    dialog.fields_dict.start_date.df.onchange = recalc_duration;
    dialog.fields_dict.end_date.df.onchange = recalc_duration;
    dialog.fields_dict.duration_uom.df.onchange = recalc_duration;

    dialog.show();
}

// ---------------------------------------------------------------------------
// "Create" button group
//   - Payment / Payment Request: any submitted contract, made against the
//     linked Sales Order (mirrors Sales Order). See docs/payments/create_payment_buttons.md
//   - Advance / Installment Payment: renewed contracts only.
//     See docs/contract_renewal/renewal_payment_setup.md
// ---------------------------------------------------------------------------

function add_create_buttons(frm) {
    const GROUP = __("Create");
    let added = false;

    // --- Payment / Payment Request — mirrors Sales Order, made against the linked SO ---
    const allowance = flt(frappe.boot.sysdefaults && frappe.boot.sysdefaults.over_billing_allowance);
    const not_fully_paid = flt(frm.doc.per_payment) < 100 + allowance;
    if (frm.doc.sales_order && not_fully_paid) {
        if ((frappe.boot.user.in_create || []).includes("Payment Request")) {
            frm.add_custom_button(__("Payment Request"), () => make_contract_payment_request(frm), GROUP);
            added = true;
        }
        if (frappe.model.can_create("Payment Entry")) {
            frm.add_custom_button(__("Payment"), () => make_contract_payment_entry(frm), GROUP);
            added = true;
        }
    }

    // --- Advance / Installment Payment — renewed contracts only ---
    if (frm.doc.is_renewed) {
        const has_advance = !!frm.doc.advance_payment_entry;
        const has_installments = !!(frm.doc.apply_installment_payment && (frm.doc.payment_schedule || []).length);

        // Advance must precede installments: hide once a schedule exists.
        if (!has_advance && !has_installments) {
            frm.add_custom_button(__("Advance Payment"), () => open_renewal_advance_dialog(frm), GROUP);
            added = true;
        }
        if (!frm.doc.apply_installment_payment) {
            frm.add_custom_button(__("Installment Payment"), () => open_renewal_installment_dialog(frm), GROUP);
            added = true;
        }
    }

    if (added) {
        frm.page.set_inner_btn_group_as_primary(GROUP);
    }
}

function make_contract_payment_entry(frm) {
    // New Payment Entry mapped against the linked Sales Order (same as SO's Create → Payment).
    frappe.call({
        method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        args: { dt: "Sales Order", dn: frm.doc.sales_order },
        callback(r) {
            if (!r.exc && r.message) {
                const doclist = frappe.model.sync(r.message);
                frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
            }
        },
    });
}

function make_contract_payment_request(frm) {
    frappe.call({
        method: "erpnext.accounts.doctype.payment_request.payment_request.make_payment_request",
        args: {
            dt: "Sales Order",
            dn: frm.doc.sales_order,
            party_type: "Customer",
            party: frm.doc.customer,
            party_name: frm.doc.customer_name,
            payment_request_type: "Inward",
        },
        callback(r) {
            if (!r.exc && r.message) {
                frappe.model.sync(r.message);
                frappe.set_route("Form", r.message.doctype, r.message.name);
            }
        },
    });
}

function open_renewal_advance_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Link Advance Payment"),
        fields: [
            {
                fieldname: "advance_payment_entry",
                fieldtype: "Link",
                label: __("Advance Payment Entry"),
                options: "Payment Entry",
                reqd: 1,
                description: __("A submitted receive Payment Entry referencing this contract's Sales Order."),
                get_query: () => ({
                    query: "erp_contract.utils.payment.get_advance_payment_entries",
                    filters: {
                        company: frm.doc.company,
                        customer: frm.doc.customer,
                        reference_doctype: "Sales Order",
                        reference_name: frm.doc.sales_order,
                        current_contract: frm.doc.name,
                    },
                }),
            },
            { fieldname: "currency", fieldtype: "Link", options: "Currency", hidden: 1, default: frm.doc.currency },
            { fieldname: "advance_amount", fieldtype: "Currency", label: __("Advance Amount"), read_only: 1, options: "currency" },
        ],
        primary_action_label: __("Link Advance"),
        primary_action(values) {
            frappe.call({
                method: "erp_contract.utils.payment.set_renewal_advance",
                args: { contract_name: frm.doc.name, advance_payment_entry: values.advance_payment_entry },
                freeze: true,
                freeze_message: __("Linking advance payment…"),
                callback(r) {
                    if (!r.exc) {
                        dialog.hide();
                        frappe.show_alert({ message: __("Advance payment linked."), indicator: "green" });
                        frm.reload_doc();
                    }
                },
            });
        },
    });

    // Preview the paid amount when a Payment Entry is chosen.
    dialog.fields_dict.advance_payment_entry.df.onchange = () => {
        const pe = dialog.get_value("advance_payment_entry");
        if (!pe) {
            dialog.set_value("advance_amount", 0);
            return;
        }
        frappe.call({
            method: "erp_contract.utils.payment.get_payment_entry_details",
            args: { deposit_reference: pe },
            callback(r) {
                if (r.message) dialog.set_value("advance_amount", r.message.paid_amount);
            },
        });
    };

    dialog.show();
}

function open_renewal_installment_dialog(frm) {
    const remaining = flt(frm.doc.net_total) - flt(frm.doc.advance_amount);
    if (remaining <= 0) {
        frappe.msgprint(__("Amount Due is zero — nothing to schedule."));
        return;
    }

    const counts = { Monthly: 12, Quarterly: 4, "Half-Yearly": 2, Yearly: 1 };

    const dialog = new frappe.ui.Dialog({
        title: __("Create Installment Schedule"),
        fields: [
            { fieldname: "currency", fieldtype: "Link", options: "Currency", hidden: 1, default: frm.doc.currency },
            { fieldname: "amount_due", fieldtype: "Currency", label: __("Amount Due"), read_only: 1, options: "currency", default: remaining },
            { fieldname: "due_start_date", fieldtype: "Date", label: __("Due Start Date"), reqd: 1 },
            { fieldname: "cb", fieldtype: "Column Break" },
            {
                fieldname: "payment_periodicity",
                fieldtype: "Select",
                label: __("Payment Periodicity"),
                options: "\nMonthly\nQuarterly\nHalf-Yearly\nYearly",
                reqd: 1,
            },
            { fieldname: "installment_count", fieldtype: "Int", label: __("Installment Count"), reqd: 1 },
        ],
        primary_action_label: __("Create Schedule"),
        primary_action(values) {
            frappe.call({
                method: "erp_contract.utils.payment.set_renewal_installments",
                args: {
                    contract_name: frm.doc.name,
                    due_start_date: values.due_start_date,
                    payment_periodicity: values.payment_periodicity,
                    installment_count: values.installment_count,
                },
                freeze: true,
                freeze_message: __("Creating installment schedule…"),
                callback(r) {
                    if (!r.exc) {
                        dialog.hide();
                        frappe.show_alert({ message: __("Installment schedule created."), indicator: "green" });
                        frm.reload_doc();
                    }
                },
            });
        },
    });

    // Default the installment count from the periodicity (mirrors the main form).
    dialog.fields_dict.payment_periodicity.df.onchange = () => {
        const p = dialog.get_value("payment_periodicity");
        if (counts[p]) dialog.set_value("installment_count", counts[p]);
    };

    dialog.show();
}

// ---------------------------------------------------------------------------
// Hierarchical Approval buttons
// ---------------------------------------------------------------------------

function add_approval_buttons(frm) {
    frappe.call({
        method: "erp_contract.utils.approval.get_approval_context",
        args: { contract_name: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const ctx = r.message;

            // Progress indicator — always shown when the chain has been initiated.
            // `user` is the actor who approved/rejected; it is blank until the
            // step is acted on, so it is only appended once present.
            if (ctx.chain && ctx.chain.length) {
                frm.dashboard.add_comment(
                    ctx.chain.map(step => {
                        const actor = step.user ? ` — ${step.user}` : "";
                        return `<b>${step.precedence}.</b> ${step.role}${actor} `
                            + `<span class="indicator ${_approval_color(step.approval_status)}">`
                            + `${step.approval_status}</span>`;
                    }).join("<br>"),
                    "blue", true
                );
            }

            const GROUP = __("Approvals");

            // "Request Approval" — shown to the contract owner before chain starts
            // and again after rejection so they can re-initiate
            if (ctx.can_request) {
                frm.add_custom_button(__("Request Approval"), () => {
                    frappe.confirm(
                        __("Initiate the hierarchical approval chain for this contract?"),
                        () => {
                            frappe.call({
                                method: "erp_contract.utils.approval.request_approval",
                                args: { contract_name: frm.doc.name },
                                freeze: true,
                                freeze_message: __("Initiating approval chain…"),
                                callback(r) {
                                    if (!r.exc) {
                                        frappe.show_alert({
                                            message: __("Approval chain initiated. The first approver has been notified."),
                                            indicator: "green",
                                        });
                                        frm.reload_doc();
                                    }
                                },
                            });
                        }
                    );
                }, GROUP).addClass("btn-primary");
            }

            // "Approve" / "Reject" — only for the active Pending approver
            if (!ctx.is_approver) return;

            frm.add_custom_button(__("Approve"), () => {
                open_signature_dialog(frm, (signature) => {
                    frappe.call({
                        method: "erp_contract.utils.approval.approve_contract",
                        args: { contract_name: frm.doc.name, signature },
                        freeze: true,
                        freeze_message: __("Recording approval…"),
                        callback(r) {
                            if (!r.exc) {
                                frappe.show_alert({ message: __("Approval recorded."), indicator: "green" });
                                frm.reload_doc();
                            }
                        },
                    });
                });
            }, GROUP).addClass("btn-success");

            frm.add_custom_button(__("Reject"), () => {
                frappe.prompt(
                    { fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
                    (values) => {
                        frappe.call({
                            method: "erp_contract.utils.approval.reject_contract",
                            args: { contract_name: frm.doc.name, reason: values.reason },
                            freeze: true,
                            freeze_message: __("Recording rejection…"),
                            callback(r) {
                                if (!r.exc) {
                                    frappe.show_alert({ message: __("Contract rejected."), indicator: "red" });
                                    frm.reload_doc();
                                }
                            },
                        });
                    },
                    __("Reject Contract"),
                    __("Confirm Rejection")
                );
            }, GROUP).addClass("btn-danger");
        },
    });
}

function open_signature_dialog(frm, callback) {
    const dialog = new frappe.ui.Dialog({
        title: __("Sign Approval"),
        fields: [
            {
                fieldname: "signature",
                fieldtype: "Signature",
                label: __("Your Signature"),
            },
        ],
        primary_action_label: __("Confirm Approval"),
        primary_action(values) {
            dialog.hide();
            callback(values.signature || "");
        },
    });
    dialog.show();
}

function _approval_color(status) {
    return {
        "Approved": "green",
        "Rejected": "red",
        "Pending": "orange",
        "Waiting": "grey"
    }[status] || "grey";
}
