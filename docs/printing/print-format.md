# Rendering Terms in a Print Format

Terms are stored as raw Jinja, so the **print format** is what renders them.

## The Standard format can't do it

The Standard/auto format and the Print Format **Builder** only display stored field
values — they never run Jinja. A Code field shows as **raw source** there. To render the
terms you must use a **Custom (HTML / Jinja)** print format.

## Custom HTML snippet

Put this in the print format's Custom HTML where the terms should appear:

```jinja
{% for row in doc.contract_terms %}
{{ frappe.render_template(row.terms_and_conditions_primary, doc.as_dict()) | safe }}
{% endfor %}
```

- `{% for row … %}` — `terms_and_conditions_primary` lives in the `contract_terms` child
  table, so loop the rows.
- `doc.as_dict()` — passes the contract's fields as **top-level** context (the bare-name
  convention from [authoring-terms.md](authoring-terms.md)).
- `| safe` — output the HTML instead of escaping it.
- Foreign column: repeat with `row.terms_and_conditions_foreign`.

## Why it works

- The Code source is **unsanitized**, so full HTML/CSS/icons survive.
- Print output is **unsanitized**, so inline SVG (`frappe_icon`) renders.
- Engine is **wkhtmltopdf**: inline `<svg>` and `<img>` render; CSS-background SVG does not.

## Print preview = the print format

The "print preview" is just the selected print format rendered in the browser — same
engine, same output as the PDF. So a rendered preview requires this Custom HTML format;
the Standard preview will always show raw Jinja.
