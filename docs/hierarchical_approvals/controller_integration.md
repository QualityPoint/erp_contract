# Controller Integration

**File**: `erp_contract/erp_contract/doctype/erp_contract/erp_contract.py`  
**Concern**: Hook the approval chain into the document lifecycle

The controller owns two things regarding approvals:

1. **When** to trigger chain population (`before_submit`)
2. **When** to gate submission (`on_submit`)

It delegates **all** logic to `utils/approval.py`.

---

## `before_submit`

```python
def before_submit(self):
    populate_approval_chain(self)
```

Frappe calls `before_submit` exactly once, immediately before the document
is saved with `docstatus=1`. This is the correct moment to:
- Resolve role → user mappings (users must exist at submission time)
- Freeze the chain (roles in Settings may change later — the rows on the contract are immutable after this point)
- Share the doc with the first approver

If `apply_hierarchical_approvals = 0`, `populate_approval_chain` is a no-op
and `before_submit` completes in microseconds.

---

## `on_submit`

```python
def on_submit(self):
    assert_approval_chain_complete(self)   # gate: throws if chain not complete
    self.update_contract_status()
    if self.sales_order:
        recalculate_contract_payment({self.sales_order})
```

`assert_approval_chain_complete` runs **before** any other `on_submit` work.
If the chain has unapproved steps, it throws and the submit is aborted — no
status update, no payment sync.

**Why doesn't `on_submit` do the approval?**  
Because `on_submit` runs immediately when the user clicks Submit. The approval
chain is an asynchronous process that may take days. The flow is:

```
Submit button clicked
  → before_submit: chain populated, doc shared with step-1 approver
  → on_submit: assert chain is complete
              ↑ this throws because step-1 is still "Pending"
              ↑ submit is blocked until all steps are Approved
  ...days pass...
  → all steps Approved via approve_contract() API
  → user clicks Submit again
  → on_submit: assert passes → contract fully submitted
```

---

## Import

```python
from erp_contract.utils.approval import populate_approval_chain, assert_approval_chain_complete
```

Only two symbols are imported. `approve_contract`, `reject_contract`, and
`get_approval_context` are whitelisted on `utils/approval.py` itself — they
are called directly from JS, not from the controller.
