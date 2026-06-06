# Controller Integration

**File**: `erp_contract/erp_contract/doctype/erp_contract/erp_contract.py`  
**Concern**: Hook the approval gate into the document submit lifecycle

The controller owns exactly **one** approval-related responsibility:

- **Gate submission** (`before_submit`) — prevent the contract from being fully
  submitted until the approval chain is complete.

It delegates **all** logic to `utils/approval.py`.

---

## `before_submit`

```python
def before_submit(self):
    assert_approval_chain_complete(self)   # gate: throws if chain not complete
    self.update_contract_status()

def on_submit(self):
    if self.sales_order:
        recalculate_contract_payment({self.sales_order})
```

The gate lives in `before_submit` so it runs before `docstatus` flips to 1 — if
it throws, nothing has been mutated. It is safe here (unlike chain *population*,
see below) because `assert_approval_chain_complete` only **reads** and may
`throw`; it never writes, so it has nothing to lose to a rollback.

`assert_approval_chain_complete` raises in two cases:

1. **Chain never initiated** — the approvals table is empty but the feature is
   enabled. This blocks users who click Submit without having clicked
   "Request Approval" first.
2. **Chain not fully approved** — at least one row is not `"Approved"`.

If the chain is complete (all rows `"Approved"`), control passes normally to
`update_contract_status()` and payment recalculation.

---

## Why Chain *Population* Is Not in the Submit Lifecycle

The gate (a read-only assertion) is safe in `before_submit`. Chain
**population** is not — the original design placed `populate_approval_chain`
inside `before_submit`, which was **non-functional** because of Frappe's
transaction model:

```
before_submit  → chain rows written to DB (same transaction)
                 frappe.throw() because rows are Pending/Waiting
                 ↑ exception propagates to HTTP handler
                 ↑ frappe.db.rollback() called
                 ↑ ALL changes (rows + docstatus=1) are rolled back
```

The chain was erased on every submit attempt, making the feature impossible
to use. The fix moves chain population entirely out of the submit lifecycle
into `request_approval()` — a separate whitelisted API with its own committed
HTTP request that cannot be rolled back by the submit transaction.

---

## Import

```python
from erp_contract.utils.approval import assert_approval_chain_complete
```

Only one symbol is imported. `request_approval`, `approve_contract`,
`reject_contract`, and `get_approval_context` are whitelisted on
`utils/approval.py` itself — they are called directly from JS.

---

## Full Submit Flow

```
User clicks "Request Approval" (on draft or submitted form)
  → request_approval() committed as its own HTTP request
  → chain rows + approval_status = "Pending Approval" persisted

Approvers act one by one via approve_contract() / reject_contract()
  → each call is its own committed HTTP request

After all steps Approved:
  → contract.approval_status = "Approved"

User clicks Submit
  → before_submit: assert_approval_chain_complete → passes; update_contract_status()
  → on_submit: recalculate_contract_payment()
  → contract fully submitted (docstatus=1)
```
