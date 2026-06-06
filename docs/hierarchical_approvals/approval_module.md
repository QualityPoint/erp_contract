# `utils/approval.py` — Approval Module

**File**: `erp_contract/utils/approval.py`  
**Layer**: Core business logic  
**Concern**: All approval state transitions, role resolution, notifications, doc sharing

This module is the single owner of approval logic. Nothing outside it reads or
writes approval state directly.

---

## Public API

### `get_approval_roles() → list[dict]`

Reads `Contract Settings` and returns the ordered role chain.  
Returns `[]` if `apply_hierarchical_approvals = 0` — callers treat an empty
list as "feature disabled".

```python
[
    {"role": "Financial Approver", "precedence": 1},
    {"role": "Legal Approver",     "precedence": 2},
    {"role": "Manager",            "precedence": 3},
]
```

---

### `request_approval(contract_name)` `@frappe.whitelist()`

Called from the JS **"Request Approval"** button.

1. Checks the caller has `write` permission on the contract.
2. Raises if the contract is cancelled, already approved, or has an active Pending step.
3. Fetches roles from `get_approval_roles()` — raises if none configured.
4. Calls `_populate_approval_chain(contract, roles)`.

This is intentionally decoupled from the Frappe submit transaction. Because it
runs as its own HTTP request, the chain rows are committed to the DB immediately
and cannot be lost to a `frappe.db.rollback()` triggered by `on_submit`.

Re-calling after a rejection is allowed: the previous rejected rows are cleared
and the chain restarts from precedence 1.

---

### `assert_approval_chain_complete(contract)`

Called from `ERPContract.on_submit()` as the final gate.

- If the feature is off → no-op.
- If the approvals table is empty (chain was never initiated) → throws, blocking submission.
- If any row is not `"Approved"` → throws, identifying the blocking step.

The empty-chain guard prevents bypassing approval by clicking Submit directly
without having clicked "Request Approval" first.

---

### `approve_contract(contract_name, signature)` `@frappe.whitelist()`

Called from the JS **Approve** button.

1. `_assert_can_act` — contract must not be cancelled or already decided.
2. `_get_pending_row` — finds the single `"Pending"` row; throws if none.
3. `_assert_can_approve` — session user must hold `row.role`; throws `PermissionError` otherwise.
4. Sets `approval_status = "Approved"`, stamps the acting `user`, `approved_on`, `signature` on the row.
5. Calls `_next_row(contract, pending_row.precedence)` to find the next step.
   - If found: advances it to `"Pending"`, shares doc with the next role's holders, notifies them.
   - If none: sets `contract.approval_status = "Approved"`, notifies owner.
6. Returns `{"chain_complete": bool, "next_role": str | None}`.

The acting user is **not** chosen in advance — any current holder of the step's
role may approve, and whoever does is recorded in the row's `user` field.

---

### `reject_contract(contract_name, reason)` `@frappe.whitelist()`

Called from the JS **Reject** button.

1. Same guards as `approve_contract` (including the `_assert_can_approve` role check).
2. Sets `approval_status = "Rejected"`, stamps the acting `user`, `approved_on`, `rejection_reason` on the row.
3. Sets `contract.approval_status = "Rejected"`.
4. Notifies the contract owner.

`reason` is mandatory — throws if empty or whitespace-only.

---

### `get_approval_context(contract_name)` `@frappe.whitelist()`

Called on every `refresh` of a non-new, non-cancelled contract form.

Returns:

```python
{
    "is_approver": True,           # current user holds the active Pending step's role
    "can_request": True,           # "Request Approval" button should be shown
    "pending_row": "row-name",     # Contract Approver row name (or None)
    "approval_status": "Pending Approval",
    "chain": [
        {"precedence": 1, "role": "Financial Approver", "user": "actor@co", "approval_status": "Approved"},
        {"precedence": 2, "role": "Legal Approver",     "user": "",         "approval_status": "Pending"},
        ...
    ]
}
```

`user` is the actor who approved/rejected the step. It is blank for steps that
have not yet been acted on (`Pending` / `Waiting`).

`is_approver` is `True` when there is an active `Pending` step and the current
user holds that step's role.

`can_request` is `True` when: roles are configured, contract is not cancelled,
`approval_status` is not `"Approved"`, and no step is currently `"Pending"`.
This covers both the initial state (empty chain) and a rejected chain.

---

## Private Helpers

| Function | Signature | Purpose |
|---|---|---|
| `_get_follow_via_email` | `() → bool` | Reads `Contract Settings.follow_via_email` |
| `_populate_approval_chain` | `(contract, roles)` | Validates the chain, clears stale rows, inserts new ones via direct DB writes, shares doc with the first role's holders, notifies them |
| `_get_pending_row` | `(contract)` | Returns the single `Pending` row or throws |
| `_next_row` | `(contract, current_precedence)` | Returns the lowest-precedence `Waiting` row **strictly above** `current_precedence`, or `None` |
| `_assert_can_act` | `(contract)` | Raises if `docstatus == 2` or `approval_status` is already decided |
| `_assert_can_approve` | `(pending_row)` | Raises `PermissionError` if the session user does **not** hold `row.role` |
| `_share_with_role` | `(contract, role)` | Adds a `read=1` share for every current holder of the role who lacks read access |
| `_notify_approvers` | `(contract, role)` | Notifies all holders of the role (respects `follow_via_email`); failures logged, never raised |
| `_notify_owner` | `(contract, approved, reason)` | Notifies the contract owner of the outcome (respects `follow_via_email`); failures logged, never raised |
| `_create_notification_log` | `(subject, message, user, contract)` | Inserts a Frappe `Notification Log` row (in-app bell notification) |

---

## Notification Logic (`follow_via_email`)

```
_notify_approvers(contract, role)            # wrapped in try/except → log only
    │    holders = get_users_with_role(role)  ← ALL users with the role
    │
    ├─ follow_via_email = 1
    │    fetch email for each holder
    │    frappe.sendmail(recipients=[all emails])   # queued, not now=True
    │
    └─ follow_via_email = 0
         for holder in holders:
             _create_notification_log(subject, message, holder, contract)
         ← in-app bell notification to EVERY role-holder

_notify_owner(contract, approved, reason)    # wrapped in try/except → log only
    │
    ├─ follow_via_email = 1
    │    fetch owner email from User record
    │    frappe.sendmail(recipients=[owner_email])
    │
    └─ follow_via_email = 0
         _create_notification_log(subject, message, contract.owner, contract)
```

Both notifiers are wrapped in `try/except` that routes any failure to
`frappe.log_error`. Because emails are **queued** (no `now=True`) and errors are
swallowed, a mail/SMTP problem can never roll back the approval transaction that
preceded it.

---

## `_populate_approval_chain` — Direct DB Writes

Unlike the original design (which used `contract.save()`), `_populate_approval_chain`
writes directly to the database to avoid triggering document validators and to keep
the operation cleanly scoped within the `request_approval` HTTP request:

```python
frappe.db.delete("Contract Approver", {"parent": contract.name, ...})

for row_data in new_rows:
    child = frappe.new_doc("Contract Approver")
    child.update(row_data)
    child.parent = contract.name
    child.insert(ignore_permissions=True)

frappe.db.set_value("ERP Contract", contract.name, "approval_status", "Pending Approval", ...)
contract.reload()
```

The `contract.reload()` at the end ensures the in-memory document reflects the
newly inserted rows (with their DB-assigned `name` fields) before the sharing
and notification steps resolve the first step (`min(... key=precedence)`) and
fan out to that role's holders.

---

## Why Not Frappe Workflow?

Frappe Workflow is powerful for fixed state machines. This feature requires:
- A **data-driven** chain (roles defined per company in settings, not hardcoded).
- A configurable notification mode (`follow_via_email`).
- Signature capture per step.
- A single `approval_status` field readable without Workflow knowledge.
- Re-initiation after rejection without amending the document.

A hand-rolled module is more explicit, easier to test, and does not conflict
with any future Workflow the client may add on ERP Contract.
