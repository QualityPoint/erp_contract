# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_contract_status(is_signed, contract_category, start_date, end_date):
    """
    Pure function — derives ERP Contract status from document fields.

    Duration-Based:
        not signed          → Unsigned
        signed, within dates → Active
        signed, past end    → Inactive

    Milestone-Based:
        not signed → Unsigned
        signed     → Active  (Completed/Terminated are set manually via buttons)
    """
    if not is_signed:
        return "Unsigned"

    if contract_category == "Duration-Based":
        from frappe.utils import getdate, nowdate
        today = getdate(nowdate())
        start = getdate(start_date) if start_date else today
        end = getdate(end_date) if end_date else None

        if end and today > end:
            return "Inactive"
        if today >= start:
            return "Active"
        return "Unsigned"  # signed but start_date is in the future

    # Milestone-Based — only Auto transition is Unsigned → Active on signing
    return "Active"


def update_status_for_contracts():
    """
    Daily scheduler task — recalculates Active/Inactive for all submitted,
    signed, Duration-Based ERP Contracts whose status is not manually locked.
    """
    MANUAL_STATUSES = {"On Hold", "Terminated", "Cancelled"}

    contracts = frappe.get_all(
        "ERP Contract",
        filters={
            "docstatus": 1,
            "is_signed": 1,
            "contract_category": "Duration-Based",
            "status": ("not in", list(MANUAL_STATUSES)),
        },
        fields=["name", "start_date", "end_date"],
    )

    for contract in contracts:
        new_status = get_contract_status(
            is_signed=True,
            contract_category="Duration-Based",
            start_date=contract.start_date,
            end_date=contract.end_date,
        )
        frappe.db.set_value("ERP Contract", contract.name,
                            "status", new_status)

    frappe.db.commit()


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
        "Company Official", {"company": company,
                             "is_primary_official": 1}, "name"
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
def calculate_contract_duration(start_date, end_date, duration_uom):
    """
    Calculate contract duration (inclusive of both start and end dates).
    Strategy: add 1 day to end_date (exclusive end) so that full-month/year
    ranges resolve to exact whole numbers via relativedelta.
    e.g. Jan 1 → Jan 31 (+1 day → Feb 1) = exactly 1 month.
    """
    import calendar
    from dateutil.relativedelta import relativedelta
    from frappe.utils import getdate, add_days, flt

    if not (start_date and end_date and duration_uom):
        return None

    start = getdate(start_date)
    end = getdate(end_date)

    if end < start:
        frappe.throw(_("End Date cannot be before Start Date"))

    exclusive_end = add_days(end, 1)

    if duration_uom == "Day":
        return flt((exclusive_end - start).days, 2)

    elif duration_uom == "Month":
        rd = relativedelta(exclusive_end, start)
        total_months = rd.years * 12 + rd.months
        if rd.days == 0:
            return flt(total_months, 2)
        # Fractional: remaining days over days in the partial month
        partial_start = start + relativedelta(months=total_months)
        days_in_partial = calendar.monthrange(
            partial_start.year, partial_start.month)[1]
        return flt(total_months + rd.days / days_in_partial, 2)

    elif duration_uom == "Year":
        rd = relativedelta(exclusive_end, start)
        if rd.months == 0 and rd.days == 0:
            return flt(rd.years, 2)
        return flt(rd.years + rd.months / 12 + rd.days / 365.25, 2)

    return None


@frappe.whitelist()
def get_default_terms_template():
    """Get the default ERP Contract Terms Template"""
    default_template = frappe.db.get_value(
        "ERP Contract Terms Template",
        {"is_default": 1},
        "name"
    )
    return default_template


@frappe.whitelist()
def get_terms_template(template_name, doc=None):
    """
    Fetch terms and conditions from the ERP Contract Terms Template.
    Renders Jinja variables using the provided doc context (ERPNext convention).
    """
    import json

    if not template_name:
        return

    if isinstance(doc, str):
        doc = json.loads(doc)

    try:
        template_doc = frappe.get_doc(
            "ERP Contract Terms Template", template_name)

        template_terms = []
        for terms in template_doc.get("terms", []):
            primary = terms.terms_and_conditions_primary or ""
            foreign = terms.terms_and_conditions_foreign or ""

            if doc:
                primary = frappe.render_template(primary, doc)
                foreign = frappe.render_template(
                    foreign, doc) if foreign else ""

            template_terms.append({
                "title_primary": terms.title_primary,
                "terms_and_conditions_primary": primary,
                "title_foreign": terms.title_foreign,
                "terms_and_conditions_foreign": foreign,
            })

        return template_terms

    except frappe.DoesNotExistError:
        frappe.throw(
            _("ERP Contract Terms Template {0} does not exist").format(template_name))
    except Exception as e:
        frappe.log_error(
            "Terms and Conditions Fetch",
            f"Error fetching terms and conditions: {str(e)}")


@frappe.whitelist()
def create_payment_schedule(due_start_date, installment_count, payment_periodicity, amount_due, currency):
    """Generate installment schedule rows from the given parameters."""
    from dateutil.relativedelta import relativedelta
    from frappe.utils import getdate, flt

    installment_count = int(installment_count)
    amount_due = flt(amount_due)

    if installment_count <= 0:
        frappe.throw(_("Installment Count must be greater than zero"))
    if amount_due <= 0:
        frappe.throw(_("Amount Due must be greater than zero"))

    periodicity_months = {"Monthly": 1,
                          "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
    months = periodicity_months.get(payment_periodicity)
    if not months:
        frappe.throw(_("Invalid Payment Periodicity: {0}").format(
            payment_periodicity))

    base_amount = flt(amount_due / installment_count, 2)
    last_amount = flt(amount_due - base_amount * (installment_count - 1), 2)

    start = getdate(due_start_date)
    schedule = []
    for i in range(installment_count):
        amount = last_amount if i == installment_count - 1 else base_amount
        schedule.append({
            "installment_amount": amount,
            "installment_in_words": format_currency_in_words(amount, currency),
            "installment_due_date": str(start + relativedelta(months=i * months)),
        })

    return schedule


@frappe.whitelist()
def format_currency_in_words(amount, currency):
    from frappe.utils.data import in_words
    from decimal import Decimal

    """Helper function to format currency placement in words"""
    currency_doc = frappe.db.get_value(
        "Currency", currency, ["currency_name", "fraction"], as_dict=True, cache=True
    ) or frappe._dict(currency_name=currency, fraction="")

    currency_name = currency_doc.currency_name or currency
    fraction_name = currency_doc.fraction or ""

    amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    integer_part, fractional_part = str(amount).split('.')

    # in_words respects frappe.local.lang so returns Arabic when locale is Arabic
    integer_words = in_words(int(integer_part)).title()

    if int(fractional_part) > 0:
        fractional_words = in_words(int(fractional_part)).title()
        formatted_words = f"{integer_words} {_(currency_name, context='Currency')} {_('and')} {fractional_words} {_(fraction_name, context='Currency')} {_('only.')}"
    else:
        formatted_words = f"{integer_words} {_(currency_name, context='Currency')} {_('only.')}"

    return formatted_words


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_advance_payment_entries(doctype, txt, searchfield, start, page_len, filters):
    """Get Payment Entry documents filtered by company, customer, and reference document,
    excluding entries already linked to a submitted ERP Contract."""
    company = filters.get('company')
    customer = filters.get('customer')
    reference_doctype = filters.get('reference_doctype')
    reference_name = filters.get('reference_name')
    current_contract = filters.get('current_contract')

    if not all([company, customer, reference_doctype, reference_name]):
        return []

    PE = frappe.qb.DocType("Payment Entry")
    PER = frappe.qb.DocType("Payment Entry Reference")
    EC = frappe.qb.DocType("ERP Contract")

    # Subquery: payment entries already taken by another submitted contract
    taken = frappe.qb.from_(EC).select(EC.advance_payment_entry).where(
        (EC.docstatus == 1) & (EC.advance_payment_entry.isnotnull()) & (
            EC.advance_payment_entry != "")
        & (EC.name != (current_contract or ""))
    )

    query = (
        frappe.qb.from_(PE)
        .inner_join(PER).on(PER.parent == PE.name)
        .select(PE.name, PE[searchfield])
        .distinct()
        .where(PE.docstatus == 1)
        .where(PE.company == company)
        .where(PE.party == customer)
        .where(PE.payment_type == "Receive")
        .where(PER.reference_doctype == reference_doctype)
        .where(PER.reference_name == reference_name)
        .where(PE.name.notin(taken))
        .orderby(PE[searchfield])
        .limit(page_len)
        .offset(start)
    )

    if txt:
        query = query.where(PE[searchfield].like(f"%{txt}%"))

    return query.run()


@frappe.whitelist()
def get_payment_entry_details(deposit_reference):
    """Fetch payment entry details based on the deposit reference."""
    doc = frappe.get_doc("Payment Entry", deposit_reference)

    return {
        "paid_amount": doc.paid_amount,
        "advance_amount_in_words": format_currency_in_words(doc.paid_amount, doc.paid_to_account_currency)
    }


@frappe.whitelist()
def get_reference_document_price_details(doctype, document_name):
    """Fetch contract items based on the document name."""
    from frappe.utils import flt

    doc = frappe.get_doc(doctype, document_name)
    price_details = {
        "currency": doc.currency,
        "total_taxes_and_charges": doc.total_taxes_and_charges,
    }
    # Set precision to 2 decimal places for the taxes and charges
    price_details.update({
        "taxes": flt(doc.total_taxes_and_charges, precision=2)
    })

    # Calculate the net total
    net_total = flt(doc.net_total, precision=2)
    price_details.update({
        "net_total": net_total
    })

    # Convert the net total to words
    net_total_in_words = format_currency_in_words(
        net_total, doc.currency)
    price_details.update({
        "net_total_in_words": net_total_in_words
    })

    return price_details


@frappe.whitelist()
def renew_contract(contract_name, new_start_date, new_end_date=None):
    """Create a renewed copy of an ERP Contract and record the renewal on the original."""
    original = frappe.get_doc("ERP Contract", contract_name)

    if original.docstatus != 1:
        frappe.throw(_("Only submitted contracts can be renewed."))

    # Create a copy — no_copy fields (is_renewed, contract_renewal_records) are excluded automatically
    new_doc = frappe.copy_doc(original)
    new_doc.start_date = new_start_date
    new_doc.end_date = new_end_date or None
    new_doc.remarks = ""
    new_doc.status = "Draft"
    new_doc.insert(ignore_permissions=True)

    # Record the renewal on the original (db-level to bypass submit lock)
    frappe.db.set_value("ERP Contract", contract_name, "is_renewed", 1)
    frappe.get_doc({
        "doctype": "Contract Renewal Record",
        "parenttype": "ERP Contract",
        "parentfield": "contract_renewal_records",
        "parent": contract_name,
        "renewal_date": frappe.utils.today(),
        "renewal_start_date": new_start_date,
        "renewal_end_date": new_end_date or None,
        "renewed_contract": new_doc.name,
    }).insert(ignore_permissions=True)

    return new_doc.name
