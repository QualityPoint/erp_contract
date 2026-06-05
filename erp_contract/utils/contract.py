# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def format_currency_in_words(amount, currency):
    """Convert a numeric amount to its written representation in the active locale."""
    from frappe.utils.data import in_words
    from decimal import Decimal

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
        return (
            f"{integer_words} {_(currency_name, context='Currency')} "
            f"{_('and')} {fractional_words} {_(fraction_name, context='Currency')} {_('only.')}"
        )

    return f"{integer_words} {_(currency_name, context='Currency')} {_('only.')}"


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
    """Get the default ERP Contract Terms Template."""
    return frappe.db.get_value(
        "ERP Contract Terms Template",
        {"is_default": 1},
        "name",
    )


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
        template_doc = frappe.get_doc("ERP Contract Terms Template", template_name)

        template_terms = []
        for terms in template_doc.get("terms", []):
            primary = terms.terms_and_conditions_primary or ""
            foreign = terms.terms_and_conditions_foreign or ""

            if doc:
                primary = frappe.render_template(primary, doc)
                foreign = frappe.render_template(foreign, doc) if foreign else ""

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
        frappe.throw(
            _("Could not load terms template {0}. See error log for details.").format(template_name)
        )


@frappe.whitelist()
def get_renewal_settings():
    """Return Contract Settings renewal fields for client-side grace period calculation."""
    return {
        "renewal_grace_period": frappe.db.get_single_value("Contract Settings", "renewal_grace_period") or 1,
        "grace_period_uom": frappe.db.get_single_value("Contract Settings", "grace_period_uom") or "Month",
    }
