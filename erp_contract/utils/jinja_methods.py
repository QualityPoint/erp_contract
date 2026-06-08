# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

"""Custom Jinja methods exposed to templates via the ``jinja`` hook.

Usable inside any Frappe Jinja template (contract terms, print formats, etc.)
as ``{{ method_name() }}``.

These helpers keep contract terms free of ``{% %}`` control blocks and let the
terms render identically in the Desk form preview and in PDF print output.
"""

import functools
import re

import frappe


@functools.lru_cache(maxsize=1)
def _lucide_icons():
    """Parse Frappe's Lucide sprite once into ``{name: (viewBox, inner_svg)}``.

    Cached for the process lifetime (the sprite only changes on a Frappe upgrade,
    which restarts the workers).
    """
    from pathlib import Path

    sprite = Path(
        frappe.get_app_path("frappe", "public", "icons", "lucide", "icons.svg")
    ).read_text()
    return {
        m.group(1): (m.group(2), m.group(3).strip())
        for m in re.finditer(
            r'<symbol id="icon-([^"]+)"[^>]*viewBox="([^"]+)"[^>]*>(.*?)</symbol>',
            sprite,
            re.S,
        )
    }


def frappe_icon(name, size="1em", color="currentColor", stroke_width=2):
    """Render any Frappe Lucide icon as a self-contained inline SVG.

    Unlike ``frappe.utils.icon()`` (JS-only, emits ``<use href="#icon-...">`` which
    is blank in PDF because the sprite isn't loaded there), this inlines the icon's
    paths, so it renders in both the Desk form preview and wkhtmltopdf/Chrome PDF.

    ``color`` defaults to ``currentColor`` so the icon follows the surrounding text
    colour (verified to work in wkhtmltopdf).

    Usage in a contract term / print format: ``{{ frappe_icon("saudi-riyal") }}``
    """
    view_box, inner = _lucide_icons().get(name, (None, None))
    if not inner:
        return ""
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{view_box}' fill='none' "
        f"stroke='{color}' stroke-width='{stroke_width}' stroke-linecap='round' "
        f"stroke-linejoin='round' style='width:{size};height:{size};vertical-align:-0.12em'>"
        f"{inner}</svg>"
    )
