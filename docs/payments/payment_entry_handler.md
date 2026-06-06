# Payment Entry Handler

**File**: `erp_contract/overrides/payment_entry.py`  
**Layer**: Handler (Layer 1)  
**Triggered by**: `Payment Entry` — `on_submit`, `on_cancel`

---

## Purpose

This module is the **entry point** for payment tracking when a Payment Entry is submitted or
cancelled. Its sole job is to read the Payment Entry document, identify which Sales Orders it
references, and hand that list off to the aggregation layer.

It contains **no aggregation logic** and performs **no DB writes**.

---

## Full Source

```python
import frappe
from erp_contract.utils.payment import recalculate_contract_payment


def update_contract_payment_status(doc, method=None):
    sales_orders = {
        ref.reference_name
        for ref in doc.get("references", [])
        if ref.reference_doctype == "Sales Order" and ref.reference_name
    }

    if not sales_orders:
        return

    recalculate_contract_payment(sales_orders)
```

---

## How It Works

### Step 1 — Extract Sales Order names

Payment Entry stores its linked documents in the `Payment Entry Reference` child table,
accessible as `doc.references`. Each row has:

| Field | Example value |
|---|---|
| `reference_doctype` | `"Sales Order"` |
| `reference_name` | `"SAL-ORD-2026-0001"` |
| `allocated_amount` | `5000.00` |

The handler filters for rows where `reference_doctype == "Sales Order"` and collects
`reference_name` values into a **set** (deduplication is automatic — a PE can reference
the same SO more than once across rows, but we only want to recalculate once per SO).

### Step 2 — Early exit

If no Sales Orders are found in the references (e.g. the PE is for a direct invoice or
expense), the function returns immediately. No unnecessary DB queries are made.

### Step 3 — Delegate to aggregation

The set of SO names is passed to `recalculate_contract_payment()`. From this point the
handler has no further responsibility.

---

## Why This Handler Does Not Aggregate

The PE document carries `allocated_amount` per reference row, which might seem like a
natural place to read the paid amount. However:

1. **Allocation ≠ actual payment**: `allocated_amount` reflects what the PE allocated to
   the SO at submission time, but does not account for later cancellations or reconciliation
   adjustments.
2. **Double-counting risk**: Summing `allocated_amount` across PE references would miss JE
   payments entirely, causing the contract to show a lower payment percentage than reality.
3. **The advance ledger is the canonical source**: ERPNext's own Sales Order payment
   tracking ignores the PE document's amounts and reads the `Advance Payment Ledger Entry`
   against the order (= `SO.advance_paid`) instead — we follow the same discipline.

---

## Cancellation Behaviour

On cancellation, the same function is called again. The `recalculate_contract_payment()`
aggregation reads the `Advance Payment Ledger Entry` with `delinked = 0` — when a PE is
cancelled, its advance-ledger rows are marked `delinked = 1` and automatically excluded. The
recalculated total will be lower (or zero), and `payment_status` on the contract will update
accordingly.

No special cancellation logic is needed in this handler.

---

## Hooked By

```python
# hooks.py
doc_events = {
    "Payment Entry": {
        "on_submit": "erp_contract.overrides.payment_entry.update_contract_payment_status",
        "on_cancel": "erp_contract.overrides.payment_entry.update_contract_payment_status",
    },
}
```
