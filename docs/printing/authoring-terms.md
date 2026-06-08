# Authoring Terms

Each term is a Jinja template. Reference the contract's fields by **fieldname**
(top-level — **no `doc.` prefix**). Context is the contract document.

## Fields

```jinja
{{ customer_name }} — {{ net_total }} — {{ start_date }} — {{ sales_order }}
```

See every field via **Customize Form → ERP Contract**.

## Helpers

| Helper | Purpose |
|---|---|
| `{{ frappe.utils.in_words(net_total) }}` | amount in words (Arabic when the user's language is Arabic) |
| `{{ frappe.utils.formatdate(start_date) }}` | date in the user's locale |
| `{{ "{:,.0f}".format(net_total) }}` | number with thousands separators |
| `{{ frappe_icon("saudi-riyal") }}` | inline icon — see [icons.md](icons.md) |

## Linked documents

Link fields hold only a name; fetch the document to read its fields:

```jinja
{% if sales_order %}{% set so = frappe.get_doc("Sales Order", sales_order) %}
Sales Order {{ so.name }} dated {{ frappe.utils.formatdate(so.transaction_date) }}
{% endif %}
```

## Gotchas

- **Bare names, not `doc.`** — the context is the contract's field dict; `doc` is undefined.
- **Guard empty numbers** — wrap with `frappe.utils.flt(...)`. `"{:,.0f}".format(None)` errors when a field is empty.
- **Keep `{% %}` on one line** — a standalone `{% set %}`/`{% if %}` line (especially if an old Text Editor wrapped it in its own `<p>`) leaves an **empty paragraph → blank line** after render. Put control logic on a single line.
- **Code field, not Text Editor** — the term field is Code, so it stores your Jinja/HTML byte-for-byte. Never author term Jinja in a Text Editor (it escapes/wraps/sanitizes it).

More symptoms in [troubleshooting.md](troubleshooting.md).
