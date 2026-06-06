# Archiving to Contract Records

Before applying the new period, the current period's data is **appended** (never replaced) to the `contract_records` child table.

## Mapping — Current Doc → Contract Record Row

| Contract Record field | Source |
|---|---|
| `contract_date` | `doc.contract_date` |
| `start_date` | `doc.start_date` |
| `end_date` | `doc.end_date` |
| `duration_uom` | `doc.duration_uom` |
| `contract_duration` | `doc.contract_duration` |
| `archived_contract` | `doc.signed_contract` (moved, not copied) |
| `sales_order` | `doc.sales_order` (the old period's Sales Order) |

## Behavior

- Rows are **appended** — existing records are preserved across multiple renewals.
- `archived_contract` receives the file path from `signed_contract`. After the move, `signed_contract` is cleared (see field_resets.md §2).
- `sales_order` preserves the old period's Sales Order link. The live `sales_order` is then **replaced** (not cleared) with the new period's Sales Order chosen in the dialog — so each period's Sales Order remains traceable.
- All `Contract Record` fields have `allow_on_submit: 1`. However, since the parent uses `ignore_validate_update_after_submit`, this is enforced at the child level regardless.
- The `append` call must happen **before** `doc.save()` so the new row is persisted in the same transaction.

## Python Snippet

```python
doc.append("contract_records", {
    "contract_date": doc.contract_date,
    "start_date": doc.start_date,
    "end_date": doc.end_date,
    "duration_uom": doc.duration_uom,
    "contract_duration": doc.contract_duration,
    "archived_contract": doc.signed_contract,
    "sales_order": doc.sales_order,
})
```
