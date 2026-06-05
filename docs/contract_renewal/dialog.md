# Renewal Dialog

## Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `contract_date` | Date | Yes | Date of new contract conclusion |
| `start_date` | Date | Yes | New period start |
| `end_date` | Date | Yes | New period end |
| `duration_uom` | Select (Day/Month/Year) | Yes | Same options as the main form |
| `contract_duration` | Float | — | Read-only; auto-calculated |

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

- `start_date` must not be before the current `end_date` of the contract (prevents overlapping periods).
- `end_date` must be after `start_date` (already enforced by `calculate_contract_duration`).
