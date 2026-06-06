# Data Model

Three doctypes carry the hierarchical approval feature.

---

## `Contract Settings` (Single)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `apply_hierarchical_approvals` | Check | 0 | Master switch — enables the feature globally |
| `follow_via_email` | Check | 0 | Notification mode (visible only when master switch is on): **1** → email every user who holds the role; **0** → in-app Notification Log to the assigned approver only |
| `roles` | Table → `Contract Approval Role` | — | Ordered list of roles that must approve (visible only when master switch is on) |

---

## `Contract Approval Role` (Child of Contract Settings)

Defines **one step** in the company's approval chain.

| Field | Type | Notes |
|---|---|---|
| `role` | Link → Role | The Frappe role whose holder approves at this step |
| `precedence` | Select (1–6) | Execution order; lower = earlier; must be unique |

**Invariants enforced at two layers:**
- At **settings save** (`ContractSettings.validate`): duplicate `precedence`,
  duplicate `role`, or a role with no enabled user → `frappe.throw`.
- At **request time** (`_populate_approval_chain`, defensive re-check): duplicate
  `precedence` or a role with no enabled user → `frappe.throw` before any rows
  are written.

---

## `Contract Approver` (Child of ERP Contract)

One row per approval step, populated by `request_approval()`. All fields are
`read_only = 1` — they are written only by `utils/approval.py`, never by
users directly.

| Field | Type | Written by | Notes |
|---|---|---|---|
| `precedence` | Int | `populate_approval_chain` | Copied from settings; frozen at submission time |
| `role` | Link → Role | `populate_approval_chain` | Copied from settings; the **authority** for the step — any current holder may act |
| `user` | Link → User | `approve_contract`, `reject_contract` | The actor who approved/rejected; **blank** until the step is acted on (no pre-assignment) |
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
| `approvals` | Table → `Contract Approver` | 1 | Populated by `request_approval()` |
| `approvals_section` | Section Break | 1 | Container |
| `approval_status` | Select | 1 | Contract-level status: `Not Requested / Pending Approval / Approved / Rejected` |

`approval_status` starts as `"Not Requested"` (the field default) — a fresh
contract reads as "not requested" rather than misleadingly "pending". It becomes
`"Pending Approval"` when `request_approval()` populates the chain, `"Approved"`
only when every row in `approvals` is `"Approved"`, and `"Rejected"` as soon as
any row is rejected.
