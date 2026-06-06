# Renewal Dialog

## Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `sales_order` | Link → Sales Order | Yes | The new period's Sales Order. Query filters to the contract's `company` / `customer`, `docstatus = 1`, and **excludes** any Sales Order already used by this contract (the current one plus every `sales_order` archived in `contract_records`). |
| `contract_date` | Date | Yes | Date of new contract conclusion |
| `start_date` | Date | Yes | New period start |
| `end_date` | Date | Yes | New period end |
| `duration_uom` | Select (Day/Month/Year) | Yes | Same options as the main form |
| `contract_duration` | Float | — | Read-only; display-only preview. The value persisted is **recomputed server-side**. |

## Duration Auto-Calculation

Mirrors the existing `calculate_contract_duration` utility in `erp_contract/utils/contract.py`.

On client: trigger recalculation when `start_date`, `end_date`, or `duration_uom` changes in the dialog:

```js
frappe.call({
    method: "erp_contract.utils.contract.calculate_contract_duration",
    args: {
        start_date: dialog.get_value("start_date"),
        end_date: dialog.get_value("end_date"),
        duration_uom: dialog.get_value("duration_uom"),
    },
    callback(r) {
        dialog.set_value("contract_duration", r.message ?? 0);
    },
});
```

## Validation (server-side, inside the whitelist method)

The client value of `contract_duration` is **never trusted** — `renew_contract`
recomputes it from the dates via `calculate_contract_duration`, which is also what
enforces the `end_date >= start_date` rule (it throws otherwise).

- **`start_date` must be strictly after the current `end_date`** of the contract
  (`start_date <= current_end` is rejected — no overlap and no same-day handover).
  This is also pre-checked client-side in the dialog's `primary_action` for fast feedback.
- `end_date >= start_date` — enforced via `calculate_contract_duration`.
- **`sales_order` is required** and must:
  - exist and be **submitted** (`docstatus = 1`);
  - belong to the same `company` and `customer` as the contract;
  - **not already be used by this contract** — neither the current `sales_order`
    nor any `sales_order` in `contract_records`;
  - **not be linked to any other submitted ERP Contract** (mirrors
    `validate_sales_order_uniqueness`, which is otherwise skipped during
    `update_after_submit`).
