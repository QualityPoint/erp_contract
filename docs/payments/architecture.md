# Architecture & Separation of Concerns

## Guiding Principle

Each component has **one reason to change**. If ERPNext changes how Journal Entry stores
references, only `overrides/journal_entry.py` needs updating. If the aggregation formula
changes, only `utils/payment.py` needs updating. If Frappe changes how hooks are declared,
only `hooks.py` needs updating.

---

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Frappe / ERPNext core                    │
│                                                             │
│   Payment Entry                 Journal Entry               │
│   (on_submit / on_cancel)       (on_submit / on_cancel)     │
└──────────────┬───────────────────────────┬──────────────────┘
               │  doc_events (hooks.py)    │
               ▼                           ▼
┌──────────────────────┐   ┌──────────────────────────────────┐
│  LAYER 1 — Handlers  │   │  LAYER 1 — Handlers              │
│                      │   │                                  │
│  overrides/          │   │  overrides/                      │
│    payment_entry.py  │   │    journal_entry.py              │
│                      │   │                                  │
│  Concern:            │   │  Concern:                        │
│  Extract SO names    │   │  Extract SO names                │
│  from PE.references  │   │  from JE.accounts                │
└──────────┬───────────┘   └──────────────┬───────────────────┘
           │                              │
           └──────────────┬───────────────┘
                          │  shared set of SO names
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2 — Aggregation                                      │
│                                                             │
│  utils/payment.py :: recalculate_contract_payment()        │
│                                                             │
│  Concern:                                                   │
│  Query Payment Ledger Entry (PLE) for total paid against   │
│  each SO; compute per_payment + payment_status;            │
│  write to ERP Contract via frappe.db.set_value()           │
└─────────────────────────────────────────────────────────────┘
```

---

## Responsibilities by File

### `utils/contract_status.py`

- **Layer**: Contract status logic
- **Contains**: `get_contract_status`, `update_status_for_contracts`
- **Imports from**: nothing in erp_contract (pure frappe)
- **Change trigger**: Contract status rules change, new statuses added.

---

### `utils/contract.py`

- **Layer**: Contract-specific utilities
- **Contains**: `calculate_contract_duration`, `get_default_terms_template`, `get_terms_template`, `get_renewal_settings`, `format_currency_in_words`
- **Imports from**: nothing in erp_contract (pure frappe)
- **Change trigger**: Duration calculation strategy changes, contract terms rendering changes, currency formatting changes.

---

### `utils/party.py`

- **Layer**: Generic party/document lookups
- **Contains**: `get_default_address`, `get_default_company_official`, `get_default_contact`, `get_reference_document_price_details`
- **Imports from**: `contract.format_currency_in_words`
- **Change trigger**: Address/contact lookup logic changes, price detail fields change.

---

### `utils/payment.py`

- **Layer**: Core payment logic + installment distribution + overdue scheduler
- **Contains**: `recalculate_contract_payment`, `recalculate_installment_payment`, `update_overdue_installments`, `get_advance_payment_entries`, `get_payment_entry_details`, `create_payment_schedule`
- **Imports from**: `contract.format_currency_in_words`
- **Change trigger**: PLE aggregation changes, waterfall algorithm changes, overdue rules change.

---

### `erp_contract/doctype/erp_contract/erp_contract.py :: on_submit()`

- **Layer**: Handler — ERP Contract controller  
- **Responsibility**: When a contract is submitted and `sales_order` is set, call
  `recalculate_contract_payment` with `{self.sales_order}` to sync any payments that were
  already recorded against the SO before this contract existed.  
- **Rule**: No aggregation logic. No PLE queries. One guard check + one delegation call.  
- **Change trigger**: New conditions are added to the guard.

---

### `hooks.py`

- **Layer**: Configuration / wiring  
- **Responsibility**: Declare which Frappe events trigger which Python functions.  
- **Rule**: No business logic. Only path strings.  
- **Change trigger**: Frappe event model changes, or a new voucher type needs to be observed.

---

### `overrides/payment_entry.py`

- **Layer**: Handler — Payment Entry  
- **Responsibility**: Extract the set of `Sales Order` names referenced in a submitted or
  cancelled Payment Entry, by reading the `Payment Entry Reference` child table
  (`doc.references`).  
- **Rule**: No aggregation logic. No DB writes. Only extraction + delegation.  
- **Change trigger**: ERPNext changes the structure of `Payment Entry Reference`.

---

### `overrides/journal_entry.py`

- **Layer**: Handler — Journal Entry  
- **Responsibility**: Extract the set of `Sales Order` names referenced in a submitted or
  cancelled Journal Entry, by reading the `Journal Entry Account` child table
  (`doc.accounts`), filtering on `reference_type == "Sales Order"`.  
- **Rule**: No aggregation logic. No DB writes. Only extraction + delegation.  
- **Change trigger**: ERPNext changes the structure of `Journal Entry Account`.

---

### `utils/payment.py :: recalculate_installment_payment()`

- **Layer**: Core business logic — installment distribution  
- **Responsibility**: Given a contract name and the total paid amount, subtract the advance
  bucket and distribute the remaining `installment_pool` across `Installment Schedule` rows
  in chronological order (waterfall). Writes `paid_amount`, `installment_per_payment`, and
  `installment_payment_status` per row.  
- **Rule**: Does not query PLE directly when called from `recalculate_contract_payment()`
  (values are passed in). Sets `Overdue` in real-time when absorbed amount is zero or
  partial and `due_date < today` — the daily scheduler is only a safety net.  
- **Change trigger**: Distribution strategy changes, new fields added to installment rows.

---

### `utils/payment.py :: update_overdue_installments()` (daily scheduler)

- **Layer**: Scheduler task  
- **Responsibility**: Safety-net scan — marks installment rows `Overdue` when `due_date <
  today` and status is `Unpaid` or `Partially Paid`. Catches rows that have never had a
  payment event fire (e.g. a contract where no payment has ever been made).  
- **Rule**: Only touches `installment_payment_status`. Does not touch `paid_amount` or
  `installment_per_payment`. Does not interact with PLE.  
- **Change trigger**: Overdue definition changes (e.g. grace days before marking overdue).

---

### `utils/payment.py :: recalculate_contract_payment()`

- **Layer**: Core business logic — aggregation  
- **Responsibility**: Given a set of Sales Order names, query `Payment Ledger Entry` to
  compute the total amount paid against each SO, then update `per_payment` and
  `payment_status` on every linked submitted ERP Contract.  
- **Rule**: No knowledge of which voucher type triggered the call. Only receives SO names.  
- **Change trigger**: PLE schema changes, payment status rules change, or `per_payment`
  formula changes.

---

## Why Not One Big Function?

A single function receiving `doc` and branching on `doc.doctype` would conflate three
concerns:

1. How PE stores references (structural knowledge of PE)
2. How JE stores references (structural knowledge of JE)
3. How to aggregate payments (business logic)

Any change to ERPNext's PE structure would require editing the same function that contains
the aggregation formula — violating SRP. The current design makes each concern independently
testable and independently changeable.

---

## Why Payment Ledger Entry (PLE)?

PLE is the GL-layer record written by **all** voucher types (PE, JE, reconciliation
write-offs). Querying it directly means:

- One query covers PE and JE paid amounts together — no double-counting.
- Cancellation is automatic: PLE rows for cancelled entries have `delinked = 1`,
  excluded by the `delinked = 0` filter.
- Exactly mirrors ERPNext's own `calculate_total_advance_from_ledger()` +
  `set_total_advance_paid()` used on Sales Order — the most battle-tested pattern available.

The alternative — querying `Payment Entry Reference` directly — would miss JE payments
entirely and require manual cancellation handling.

---

## Comparison with ERPNext Sales Order Pattern

| Aspect | ERPNext Sales Order | ERP Contract |
|---|---|---|
| Source of truth | Payment Ledger Entry | Payment Ledger Entry |
| Trigger mechanism | `advance_payment_receivable_doctypes` scheduler | `doc_events` on PE / JE |
| Aggregation function | `calculate_total_advance_from_ledger()` | `recalculate_contract_payment()` |
| Write strategy | `frappe.db.set_value` | `frappe.db.set_value` |
| Cancel handling | `delinked = 0` filter | `delinked = 0` filter |
| JE coverage | ✓ (via GL entries) | ✓ (via JE handler + PLE) |
