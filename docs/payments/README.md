# ERP Contract — Payment Tracking

## Overview

ERP Contract tracks payment progress at the contract level by listening to the Frappe GL
layer rather than querying individual document references. This mirrors exactly the pattern
ERPNext uses for Sales Order advance payment tracking.

---

## How It Works (End-to-End)

There are two independent trigger paths. Both converge at the same aggregation function.

### Path A — Contract submission (catches pre-existing payments)

```
User submits ERP Contract
        │
        ▼
ERPContract.on_submit()
        │  guard: self.sales_order
        │
        ▼
utils/payment.py :: recalculate_contract_payment({self.sales_order})
        │
        ├─ Reads Advance Payment Ledger Entry total against the SO (= SO.advance_paid)
        │
        └─ Writes per_payment + payment_status on this contract
```

**Why this path is necessary**: Payments against the linked Sales Order may have been
recorded before the contract was submitted. Without this path those advance entries would
never trigger a `doc_event`, and the contract would show `Unpaid / 0%` indefinitely.

### Path B — Payment recorded after contract is submitted

```
User submits / cancels a Payment Entry or Journal Entry
        │
        ▼
Frappe GL layer writes / delinks the advance ledger row against the SO
        │
        ▼
doc_events (hooks.py) fires the matching override handler
        │
        ├─ Payment Entry  → overrides/payment_entry.py
        │                   reads PE.references table for Sales Order names
        │
        └─ Journal Entry  → overrides/journal_entry.py
                            reads JE.accounts table for Sales Order names
        │
        ▼ (both converge here)
utils/payment.py :: recalculate_contract_payment(sales_orders)
        │
        ├─ Reads Advance Payment Ledger Entry total against each SO (= SO.advance_paid)
        │
        └─ Writes per_payment + payment_status on every matching ERP Contract
```

---

## Full Payment Lifecycle Coverage

### Contract-level fields (`per_payment`, `payment_status`)

| Event | Trigger path | Handler |
|---|---|---|
| Contract submitted (SO has existing payments) | `ERPContract.on_submit` | `recalculate_contract_payment` |
| Payment Entry submitted after contract | `doc_events` → PE handler | `recalculate_contract_payment` |
| Journal Entry submitted after contract | `doc_events` → JE handler | `recalculate_contract_payment` |
| Payment Entry cancelled | `doc_events` → PE handler | `recalculate_contract_payment` |
| Journal Entry cancelled | `doc_events` → JE handler | `recalculate_contract_payment` |

### Installment row fields (`paid_amount`, `installment_per_payment`, `installment_payment_status`)

Only applies when `apply_installment_payment = 1`.

| Event | Trigger path | Handler |
|---|---|---|
| Contract submitted (SO has existing payments) | `ERPContract.on_submit` → `recalculate_contract_payment` | `recalculate_installment_payment` |
| Payment Entry submitted after contract | `doc_events` → PE handler → `recalculate_contract_payment` | `recalculate_installment_payment` |
| Journal Entry submitted after contract | `doc_events` → JE handler → `recalculate_contract_payment` | `recalculate_installment_payment` |
| Payment Entry cancelled | `doc_events` → PE handler → `recalculate_contract_payment` | `recalculate_installment_payment` |
| Journal Entry cancelled | `doc_events` → JE handler → `recalculate_contract_payment` | `recalculate_installment_payment` |
| Installment due date passes with no/partial payment | Daily scheduler | `update_overdue_installments` |

---

## Fields Updated on ERP Contract

### Always (both payment modes)

| Field | Type | Description |
|---|---|---|
| `per_payment` | Float | Percentage of `net_total` that has been paid (0–100+) |
| `payment_status` | Select | `Unpaid` / `Partially Paid` / `Fully Paid` |

### When `apply_installment_payment = 1` (per installment row)

| Field | Type | Description |
|---|---|---|
| `installment_percent` | Percent | Row's share of Amount Due (`installment_amount / amount_due * 100`); set at schedule generation and recomputed on save — **not** by payment events. See [installment_schedule.md](installment_schedule.md) |
| `paid_amount` | Currency | Amount absorbed by this row (waterfall) |
| `installment_per_payment` | Percent | `paid_amount / installment_amount * 100` (payment progress — distinct from `installment_percent`) |
| `installment_payment_status` | Select | `Unpaid` / `Partially Paid` / `Paid` / `Overdue` |

All fields are `allow_on_submit = 1` and written via
`frappe.db.set_value(..., update_modified=False)` — no document reload needed, no
`modified` timestamp change.

---

## Payment Status Rules

| Condition | Status |
|---|---|
| `total_paid <= 0` | `Unpaid` |
| `per_payment >= 100` | `Fully Paid` |
| otherwise | `Partially Paid` |

---

## Join Key

The entire payment tracking chain rests on a single field:

```
ERP Contract.sales_order  →  Sales Order.name
```

The `Advance Payment Ledger Entry` records payments **against a Sales Order**, so an ERP
Contract must have its `sales_order` field populated for payment tracking to work. Contracts
without a linked Sales Order are never touched by the payment recalculation. Sales Invoices
are deliberately **not** consulted — the Sales Order is the only reliable anchor.

---

## Files in This Directory

| File | What it covers |
|---|---|
| [README.md](README.md) | This overview |
| [architecture.md](architecture.md) | Layer breakdown and separation of concerns |
| [payment_entry_handler.md](payment_entry_handler.md) | `overrides/payment_entry.py` explained |
| [journal_entry_handler.md](journal_entry_handler.md) | `overrides/journal_entry.py` explained |
| [aggregation.md](aggregation.md) | Core advance-ledger aggregation algorithm in `utils/payment.py` |
| [hooks.md](hooks.md) | How `doc_events` in `hooks.py` wires everything together |
| [on_submit_sync.md](on_submit_sync.md) | Why and how `on_submit` syncs pre-existing payments |
| [installment_schedule.md](installment_schedule.md) | How the installment schedule is generated and `installment_percent` is kept in sync |
| [installment_payment.md](installment_payment.md) | Waterfall distribution algorithm for installment rows |
| [overdue_scheduler.md](overdue_scheduler.md) | Daily scheduler that marks installment rows as Overdue |
| [create_payment_buttons.md](create_payment_buttons.md) | `Create → Payment` / `Payment Request` buttons (made against the linked Sales Order) |
