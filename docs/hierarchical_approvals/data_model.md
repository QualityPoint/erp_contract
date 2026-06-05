# Data Model

Three doctypes carry the hierarchical approval feature.

---

## `Contract Settings` (Single)

| Field | Type | Purpose |
|---|---|---|
| `apply_hierarchical_approvals` | Check | Master switch — enables the feature globally |
| `roles` | Table → `Contract Approval Role` | Ordered list of roles that must approve |

---

## `Contract Approval Role` (Child of Contract Settings)

Defines **one step** in the company's approval chain.

| Field | Type | Notes |
|---|---|---|
| `role` | Link → Role | The Frappe role whose holder approves at this step |
| `precedence` | Select (1–6) | Execution order; lower = earlier; must be unique |

**Invariants enforced at runtime:**
- Duplicate `precedence` values → `frappe.throw` in `populate_approval_chain`.
- Role with no enabled user → `frappe.throw` before any rows are written.

---

## `Contract Approver` (Child of ERP Contract)

One row per approval step, populated on `before_submit`. All fields are
`read_only = 1` — they are written only by `utils/approval.py`, never by
users directly.

| Field | Type | Written by | Notes |
|---|---|---|---|
| `precedence` | Int | `populate_approval_chain` | Copied from settings; frozen at submission time |
| `role` | Link → Role | `populate_approval_chain` | Copied from settings |
| `user` | Link → User | `populate_approval_chain` | First enabled user with the role |
| `approval_status` | Select | `populate_approval_chain`, `approve_contract`, `reject_contract` | `Waiting / Pending / Approved / Rejected` |
| `approved_on` | Datetime | `approve_contract`, `reject_contract` | Set to `now_datetime()` on action |
| `rejection_reason` | Small Text | `reject_contract` | Only populated on rejection |
| `signature` | Signature | `approve_contract` | Optional; captured via dialog |

**Status transition table:**

| From | Event | To |
|---|---|---|
| `Waiting` | previous step approved | `Pending` |
| `Pending` | approver clicks Approve | `Approved` |
| `Pending` | approver clicks Reject | `Rejected` |

`Waiting` → `Pending` is the only automated transition.
`Approved` and `Rejected` are terminal — no further transitions.

---

## `ERP Contract` (additions)

| Field | Type | `allow_on_submit` | Notes |
|---|---|---|---|
| `approvals` | Table → `Contract Approver` | 1 | Populated by `before_submit` |
| `approvals_section` | Section Break | 1 | Container |
| `approval_status` | Select | 1 | Contract-level status: `Pending Approval / Approved / Rejected` |

`approval_status` on the contract is set to `"Approved"` only when every row
in `approvals` is `"Approved"`. It is set to `"Rejected"` as soon as any row
is rejected. It starts as `"Pending Approval"` (the field default) when the
chain is populated but not yet complete.
