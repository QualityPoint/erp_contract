# `utils/approval.py` — Approval Module

**File**: `erp_contract/utils/approval.py`  
**Layer**: Core business logic  
**Concern**: All approval state transitions, role resolution, doc sharing, and notifications

This module is the single owner of approval logic. Nothing outside it reads or
writes approval state directly.

---

## Public API

### `get_approval_roles() → list[dict]`

Reads `Contract Settings` and returns the ordered role chain.  
Returns `[]` if `apply_hierarchical_approvals` is `0` — callers treat an empty
list as "feature disabled".

```python
[
    {"role": "Financial Approver", "precedence": 1},
    {"role": "Legal Approver",     "precedence": 2},
    {"role": "Manager",            "precedence": 3},
]
```

---

### `populate_approval_chain(contract)`

Called from `ERPContract.before_submit()`.

1. Calls `get_approval_roles()` — if empty, returns immediately (feature off).
2. Validates no duplicate precedence values.
3. For each role, calls `get_users_with_role(role)` from `frappe.utils.user`.
   - If no user has the role → `frappe.throw` (hard stop before any rows written).
4. Clears `contract.approvals` and appends fresh rows:
   - `precedence=1` row → `approval_status = "Pending"`
   - All other rows → `approval_status = "Waiting"`
5. Shares the document with the first approver via `frappe.share.add_docshare`.

**Why `before_submit` and not `validate`?**  
`validate` runs on every save including drafts. Role resolution should only
happen once — at the moment of submission. `before_submit` fires exactly once
and its changes are saved as part of the submit transaction.

---

### `assert_approval_chain_complete(contract)`

Called from `ERPContract.on_submit()`.

If the chain is non-empty and any row is not `"Approved"`, throws with a
descriptive message identifying the blocking step. This is the final
server-side gate preventing submission without full approval.

If the chain is empty (feature off), this is a no-op.

---

### `approve_contract(contract_name, signature)` `@frappe.whitelist()`

Called from the JS **Approve** button.

1. `_assert_can_act` — contract must be submitted and not already decided.
2. `_get_pending_row` — finds the single `"Pending"` row; throws if none.
3. `_assert_is_current_approver` — current session user must match `row.user`; throws `PermissionError` otherwise.
4. Sets `approval_status = "Approved"`, `approved_on`, `signature` on the row via `frappe.db.set_value(..., update_modified=False)`.
5. Finds next `"Waiting"` row (lowest precedence above current).
   - If found: sets it to `"Pending"`, shares doc, emails next approver.
   - If none: sets `contract.approval_status = "Approved"`, emails owner.
6. Returns `{"chain_complete": bool, "next_approver": str|None}`.

---

### `reject_contract(contract_name, reason)` `@frappe.whitelist()`

Called from the JS **Reject** button.

1. Same guards as `approve_contract`.
2. Sets `approval_status = "Rejected"`, `approved_on`, `rejection_reason` on the row.
3. Sets `contract.approval_status = "Rejected"`.
4. Emails the contract owner with the reason.

`reason` is mandatory — throws if empty.

---

### `get_approval_context(contract_name)` `@frappe.whitelist()`

Called on every `refresh` of a submitted contract.

Returns:

```python
{
    "is_approver": True,           # current user is the active Pending approver
    "pending_row": "row-name",     # Contract Approver row name (or None)
    "approval_status": "Pending Approval",
    "chain": [
        {"precedence": 1, "role": "Financial Approver", "user": "...", "approval_status": "Approved"},
        {"precedence": 2, "role": "Legal Approver",     "user": "...", "approval_status": "Pending"},
        ...
    ]
}
```

The JS layer uses `is_approver` to decide whether to render action buttons,
and `chain` to render the progress indicator.

---

## Private Helpers

| Function | Purpose |
|---|---|
| `_get_pending_row(contract)` | Returns the single `Pending` row or throws |
| `_next_row(contract, current_precedence)` | Returns the lowest-precedence `Waiting` row above `current_precedence`, or `None` |
| `_assert_can_act(contract)` | Raises if contract is not submitted or already decided |
| `_assert_is_current_approver(row)` | Raises `PermissionError` if session user ≠ row.user |
| `_share_with_user(contract, user)` | `frappe.share.add_docshare` with `submit=1` if user lacks submit permission |
| `_notify_approver(contract, user)` | Sends "it's your turn" email |
| `_notify_owner(contract, approved, reason)` | Sends final approval or rejection email to owner |

---

## Why Not Frappe Workflow?

Frappe Workflow is powerful for fixed state machines. This feature requires:
- A **data-driven** chain (roles defined per company in settings, not hardcoded in a Workflow doctype).
- Integration with the existing `on_submit` gate rather than replacing it.
- Signature capture per step.
- A single `approval_status` field on the contract that other code can read without Workflow knowledge.

A hand-rolled module is more explicit, easier to test, and does not conflict
with any future Workflow the client may add on ERP Contract.
