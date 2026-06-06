# Installment Payment Distribution

**Function**: `recalculate_installment_payment(contract_name, total_paid=None, advance_amount=None)`  
**File**: `erp_contract/utils/payment.py`  
**Layer**: Core business logic (Layer 2)  
**Called by**: `recalculate_contract_payment()` (for installment contracts), or standalone

---

## Purpose

When `apply_installment_payment = 1`, payment progress must be tracked per installment row,
not just at the contract level. This function takes the total amount paid against the linked
Sales Order and distributes it across `Installment Schedule` rows in chronological order.

---

## The Advance Deduction Problem

The advance ledger total against the Sales Order (`total_paid`) includes **all** payments
against the order, including the advance payment. But the `payment_schedule` child table
rows only sum to:

```
net_total - advance_amount
```

The advance already has its own bucket (`advance_amount` field + `advance_payment_entry`
link). If you distribute `total_paid` directly into the installment rows without subtracting
the advance, the first rows would absorb money that should belong to the advance bucket —
overstating their paid amounts.

**Correct formula:**

```
installment_pool = max(0, total_paid - advance_amount)
```

This is the amount available to flow through the waterfall.

---

## The Waterfall Algorithm

```
installment_pool = max(0, total_paid - advance_amount)

rows sorted by installment_due_date ASC (earliest first):

  for each row:
      absorbed = min(remaining_pool, installment_amount)
      remaining_pool -= absorbed

      per = absorbed / installment_amount * 100

      if absorbed == 0:               → Unpaid
      elif per >= 100:                → Paid
      else:                           → Partially Paid
```

### Example

```
advance_amount  = 1000
total_paid      = 3500  (includes the 1000 advance)
installment_pool = 2500

Rows (by due date):
  Row 1: installment_amount = 1000  → absorbed = 1000  → Paid       (remaining: 1500)
  Row 2: installment_amount = 1000  → absorbed = 1000  → Paid       (remaining: 500)
  Row 3: installment_amount = 1000  → absorbed = 500   → Partially Paid (remaining: 0)
  Row 4: installment_amount = 1000  → absorbed = 0     → Unpaid
```

### Why chronological order?

- It matches the natural expectation: earlier debts are cleared before later ones.
- It is deterministic and reproducible — any re-run of the function produces the same result.
- No user input is required to assign a payment to a specific row.

There is intentionally **no mechanism to assign a payment to a specific row** — the
waterfall is the contract's distribution rule.

## Date-Aware Status Logic

The waterfall sets `installment_payment_status` based on **both** the payment amount
**and** whether the row's due date has passed. This means `Overdue` is set in real-time
by the waterfall — not just by the daily scheduler.

| `absorbed` | `per >= 100` | `due_date < today` | Status |
|---|---|---|---|
| > 0 | Yes | any | `Paid` |
| > 0 | No | Yes | `Overdue` |
| > 0 | No | No | `Partially Paid` |
| 0 | — | Yes | `Overdue` |
| 0 | — | No | `Unpaid` |

### Why this matters

Without date-aware logic, cancelling a payment on an `Overdue` row would silently reset
it to `Unpaid` for up to 24 hours (until the daily scheduler corrected it). With this
logic, the status is always correct immediately after any payment event.

All three fields are `allow_on_submit = 1` and `read_only = 1` on the
`Installment Schedule` doctype.

| Field | Type | Written value |
|---|---|---|
| `paid_amount` | Currency | Amount absorbed by this row |
| `installment_per_payment` | Percent | `absorbed / installment_amount * 100`, 2dp |
| `installment_payment_status` | Select | `Unpaid` / `Partially Paid` / `Paid` |

Written via `frappe.db.set_value(..., update_modified=False)` — no timestamp noise.

> **Note**: `"Overdue"` is set both here (real-time, by the waterfall when
> `due_date < today` and absorbed amount is zero or partial) **and** by the daily
> scheduler (`update_overdue_installments`). The waterfall owns real-time Overdue;
> the scheduler is a safety net for rows that have never had a payment event.
> See [overdue_scheduler.md](overdue_scheduler.md).

---

## Standalone Call Support

When called without `total_paid` / `advance_amount` (e.g. from a future "Recalculate
Payments" button), the function re-reads the SO advance ledger and `advance_amount` from the
contract document itself:

```python
recalculate_installment_payment("ERP-CON-2026-0001")
# → fetches contract.sales_order, contract.advance_amount
# → reads Advance Payment Ledger Entry total against the SO
# → runs waterfall
```

When called from `recalculate_contract_payment()`, the values are passed in directly to
avoid a second DB round-trip.

---

## Relationship to Contract-Level Fields

`recalculate_installment_payment()` does **not** touch `per_payment` or `payment_status`
on the parent ERP Contract. Those are always written by `recalculate_contract_payment()`
first, then this function is called for the row-level detail.

Both levels are always in sync because they are updated in the same call chain.
