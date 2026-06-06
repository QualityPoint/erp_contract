# on_submit Sync — Catching Pre-Existing Payments

**Location**: `ERPContract.on_submit()` in  
`erp_contract/erp_contract/doctype/erp_contract/erp_contract.py`  
**Layer**: Handler (Layer 1)  
**Trigger**: ERP Contract `on_submit`

---

## The Problem This Solves

`doc_events` only fire when a Payment Entry or Journal Entry is submitted or cancelled.
They have no awareness of the contract — they react to the payment voucher's lifecycle.

This creates a gap: if a payment was made against a Sales Order **before** the ERP
Contract was created and submitted, those advance-ledger rows already exist. No
voucher event will ever fire for them again. Without an `on_submit` hook, the contract
would permanently show `payment_status = "Unpaid"` and `per_payment = 0` even though the
SO has been partially or fully paid.

### Timeline of the gap

```
Day 1  Customer pays 50% via Payment Entry against the SO
         └─ Advance Payment Ledger Entry written: against_voucher_no = "SAL-ORD-2026-0001"

Day 5  ERP Contract created and linked to SAL-ORD-2026-0001

Day 6  Contract submitted
         └─ Without on_submit hook → payment_status = "Unpaid"  ← WRONG
         └─ With on_submit hook    → payment_status = "Partially Paid" ← CORRECT
```

---

## The Code

```python
def on_submit(self):
    self.update_contract_status()
    if self.sales_order:
        recalculate_contract_payment({self.sales_order})
```

---

## Guard Conditions

### `self.sales_order`

`recalculate_contract_payment()` reads the advance ledger keyed by `sales_order`. Without a
linked SO there are no entries to find. The guard avoids a pointless DB round-trip.

---

## What This Handler Does NOT Do

- It does not query the advance ledger directly.
- It does not set `per_payment` or `payment_status` directly.
- It does not know about Payment Entry or Journal Entry structures.

All of that is delegated to `recalculate_contract_payment()` in `utils/payment.py`.

---

## Relationship to `doc_events` Handlers

The `on_submit` hook and the `doc_events` handlers are **complementary**, not overlapping:

| Handler | Covers |
|---|---|
| `on_submit` | Payments that existed before the contract was submitted |
| PE `doc_events` handler | Payments made (or cancelled) after contract submission via Payment Entry |
| JE `doc_events` handler | Payments made (or cancelled) after contract submission via Journal Entry |

All three call the same `recalculate_contract_payment()` function. The result is idempotent
— calling it multiple times for the same SO produces the same output.
