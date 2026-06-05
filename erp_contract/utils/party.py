# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from erp_contract.utils.contract import format_currency_in_words


@frappe.whitelist()
def get_default_address(link_doctype, link_name, sort_key="is_primary_address"):
    """Get default address for any doctype (Company, Customer, etc.)"""
    if not link_name:
        return None

    if sort_key not in ["is_shipping_address", "is_primary_address"]:
        return None

    Addr = frappe.qb.DocType("Address")
    DL = frappe.qb.DocType("Dynamic Link")

    out = (
        frappe.qb.from_(Addr)
        .inner_join(DL).on(DL.parent == Addr.name)
        .select(Addr.name, Addr[sort_key])
        .where(DL.link_doctype == link_doctype)
        .where(DL.link_name == link_name)
        .where(Addr.disabled.isnull() | (Addr.disabled == 0))
    ).run()

    if out:
        return max(out, key=lambda x: x[1])[0]
    return None


@frappe.whitelist()
def get_default_company_official(company):
    """Get the primary Company Official for the given company."""
    if not company:
        return None

    return frappe.db.get_value(
        "Company Official", {"company": company, "is_primary_official": 1}, "name"
    ) or frappe.db.get_value("Company Official", {"company": company}, "name")


@frappe.whitelist()
def get_default_contact(link_doctype, link_name):
    """Get default contact for any doctype (Company, Customer, etc.)"""
    if not link_name:
        return None

    Cont = frappe.qb.DocType("Contact")
    DL = frappe.qb.DocType("Dynamic Link")

    out = (
        frappe.qb.from_(Cont)
        .inner_join(DL).on(DL.parent == Cont.name)
        .select(Cont.name, Cont.is_primary_contact)
        .where(DL.link_doctype == link_doctype)
        .where(DL.link_name == link_name)
    ).run()

    if out:
        return max(out, key=lambda x: x[1])[0]
    return None


@frappe.whitelist()
def get_reference_document_price_details(doctype, document_name):
    """Fetch currency, taxes and net total from any document (e.g. Sales Order)."""
    from frappe.utils import flt

    doc = frappe.get_doc(doctype, document_name)
    net_total = flt(doc.net_total, precision=2)

    return {
        "currency": doc.currency,
        "total_taxes_and_charges": doc.total_taxes_and_charges,
        "taxes": flt(doc.total_taxes_and_charges, precision=2),
        "net_total": net_total,
        "net_total_in_words": format_currency_in_words(net_total, doc.currency),
    }
