# Field Resets on Renewal

## Write Strategy

The document is **submitted** (`docstatus=1`), so Frappe normally blocks writes to fields that lack `allow_on_submit`. Of the 27 fields modified on renewal, **19 do not have `allow_on_submit`**.

**Solution: `ignore_validate_update_after_submit` flag**

```python
doc = frappe.get_doc("ERP Contract", name)
doc.flags.ignore_validate_update_after_submit = True

# apply all changes on the doc object (see groups below)

doc.save()
```

Why this approach:
- Bypasses `allow_on_submit` enforcement for all fields in one `save()`.
- Still triggers `before_update_after_submit`, which calls `update_contract_status()` — status recalculates to `"Unsigned"` automatically because `is_signed` is set to `0` before `save()`. **Do NOT set status manually.**
- Child table clears (`payment_schedule = []`) and appends (`contract_records.append(...)`) work cleanly through the ORM in one transaction.
- **Do NOT use `frappe.db.set_value` in bulk** — it bypasses `before_update_after_submit` entirely, breaking automatic status recalculation.

---

Groups below reflect separation of concern.

## 1. New Period (from Dialog)

| Field | New Value | allow_on_submit |
|---|---|---|
| `contract_date` | `dialog.contract_date` | ✗ |
| `start_date` | `dialog.start_date` | ✗ |
| `end_date` | `dialog.end_date` | ✗ |
| `duration_uom` | `dialog.duration_uom` | ✗ |
| `contract_duration` | `dialog.contract_duration` | ✗ |

## 2. Signature

| Field | Reset Value | allow_on_submit |
|---|---|---|
| `is_signed` | `0` | ✓ |
| `signed_contract` | `""` (moved to archive row) | ✓ |
| `signee` | `""` | ✓ |
| `signed_on` | `None` | ✓ |
| `ip_address` | `""` | ✓ |
| `signee_customer` | `""` | ✗ |
| `signed_by_customer` | `""` | ✓ |

## 3. Sales Order & Financial

| Field | Reset Value | allow_on_submit |
|---|---|---|
| `sales_order` | `""` | ✗ |
| `currency` | `""` | ✗ |
| `net_total` | `0` | ✗ |
| `net_total_in_words` | `""` | ✗ |
| `total_taxes_and_charges` | `0` | ✗ |

## 4. Advance Payment

| Field | Reset Value | allow_on_submit |
|---|---|---|
| `advance_payment_entry` | `""` | ✗ |
| `advance_amount` | `0` | ✗ |
| `advance_amount_in_words` | `""` | ✗ |

## 5. Installment Payment

| Field | Reset Value | allow_on_submit |
|---|---|---|
| `apply_installment_payment` | `0` | ✗ |
| `due_start_date` | `None` | ✗ |
| `payment_periodicity` | `""` | ✗ |
| `amount_due` | `0` | ✗ |
| `installment_count` | `0` | ✗ |
| `payment_schedule` | `[]` (child table cleared) | ✗ |

## 6. Payment Status

| Field | Reset Value | allow_on_submit |
|---|---|---|
| `per_payment` | `0` | ✓ |
| `payment_status` | `"Unpaid"` | ✓ |

## 7. Renewal Flag

| Field | Value | allow_on_submit |
|---|---|---|
| `is_renewed` | `1` (set once, never reverted) | ✓ |

## 8. Status (auto-derived, not set directly)

`status` is **not** set in the renewal method. It is recalculated automatically by `before_update_after_submit` → `update_contract_status()` → `get_contract_status()`. Because `is_signed` is `0` at save time, the result is always `"Unsigned"`.

See [status.md](status.md) for the full decision tree.

## 9. Not Reset

- `contract_terms` — kept as-is.
- `company` / `customer` and all party/representative fields — kept as-is.
- `contract_type`, `contract_category`, `naming_series` — kept as-is.
- `remarks` — kept as-is (historical remarks preserved).

## 10. Lifecycle Hook Note

`before_validate` and `validate` do **not** run during `update_after_submit`. The renewal method must therefore apply all field clears explicitly — it cannot rely on `clear_installment_fields()` or `clear_duration_fields()` being called automatically.
