# Architecture

## Source vs. render

Term text is a **template**, not content. It is stored **raw** and rendered **only at
print time**.

| Stage | Renders Jinja? | Role |
|---|---|---|
| ERP Contract Terms Template | no — `validate_template` syntax check only | author the raw Jinja |
| ERP Contract Term (child) | no — controller is `pass` | store raw, editable per contract |
| ERP Contract `validate` | no — render-on-save was removed | `validate_template` syntax check only |
| Print Format Custom HTML | **yes** | the only render point |

## Where the source lives

- Author in the **ERP Contract Terms Template** (reusable).
- Selecting it copies the rows **raw** into the contract — `get_terms_template` returns
  the template verbatim, it does not render.
- The Template and the Contract share the **same child doctype**, `ERP Contract Term`,
  so a field change applies to both.

## Field type

`terms_and_conditions_primary` / `_foreign` are **Code** fields (`options: Jinja`):
stored verbatim, never sanitized, never auto-rendered — the same kind of field a
Print Format uses for its own `html`.

## Key files

| File | Responsibility |
|---|---|
| `erp_contract/utils/contract.py` → `get_terms_template` | return template rows **raw** |
| `…/doctype/erp_contract/erp_contract.py` → `validate_contract_terms` | Jinja **syntax** check |
| `erp_contract/utils/jinja_methods.py` → `frappe_icon` | inline-icon helper |
| `erp_contract/hooks.py` → `jinja` | expose the helper to Jinja |

See [authoring-terms.md](authoring-terms.md) and [print-format.md](print-format.md).
