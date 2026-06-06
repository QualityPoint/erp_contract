# Copyright (c) 2026, QualityPoint and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.user import get_users_with_role


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_approval_roles() -> list[dict]:
    """Return the ordered approval chain from Contract Settings, or [] if disabled."""
    if not frappe.db.get_single_value("Contract Settings", "apply_hierarchical_approvals"):
        return []
    return frappe.get_all(
        "Contract Approval Role",
        filters={"parent": "Contract Settings", "parentfield": "roles"},
        fields=["role", "precedence"],
        order_by="precedence asc",
    )


def _get_follow_via_email() -> bool:
    return bool(frappe.db.get_single_value("Contract Settings", "follow_via_email"))


# ---------------------------------------------------------------------------
# Request Approval  (whitelisted — triggered from the JS "Request Approval" button)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def request_approval(contract_name: str) -> None:
    """
    Initiate (or re-initiate after rejection) the hierarchical approval chain.

    Populates the approvals child table via direct DB writes — decoupled from
    the submit transaction so the chain rows are committed immediately and are
    not lost to a rollback.  Safe to call on draft and submitted contracts.
    """
    contract = frappe.get_doc("ERP Contract", contract_name)
    frappe.has_permission("ERP Contract", "write", contract, throw=True)

    if contract.docstatus == 2:
        frappe.throw(_("Cannot request approval on a cancelled contract."))
    if contract.approval_status == "Approved":
        frappe.throw(_("This contract has already been approved."))
    if any(r.approval_status == "Pending" for r in contract.get("approvals", [])):
        frappe.throw(_("An approval step is already pending. Cannot re-initiate the chain."))

    roles = get_approval_roles()
    if not roles:
        frappe.throw(_("No approval roles are configured in Contract Settings."))

    _populate_approval_chain(contract, roles)


# ---------------------------------------------------------------------------
# Population  (internal — called from request_approval only)
# ---------------------------------------------------------------------------

def _populate_approval_chain(contract, roles: list[dict]) -> None:
    """
    Build the approvals child table using direct DB inserts, bypassing the
    document save cycle so validators are not re-run and the operation stays
    in its own committed request.  Clears any previously rejected/waiting rows.

    Each row stores the *role* that is authorised to act on the step; the
    acting user is stamped onto the row only when someone approves or rejects.
    """
    # Validate the chain up-front before touching the DB.
    seen: set[int] = set()
    new_rows: list[dict] = []
    for i, row in enumerate(roles):
        p = int(row.precedence)
        if p in seen:
            frappe.throw(
                _("Duplicate precedence {0} in Contract Settings approval roles.").format(p)
            )
        seen.add(p)

        # The role must have at least one enabled user, otherwise the step
        # could never be acted upon.
        if not get_users_with_role(row.role):
            frappe.throw(
                _("No active user found for approval role \"{0}\" (precedence {1}). "
                  "Assign this role to at least one user before requesting approval.").format(
                    row.role, row.precedence
                )
            )
        new_rows.append({
            "idx": i + 1,
            "precedence": p,
            "role": row.role,
            "approval_status": "Pending" if i == 0 else "Waiting",
        })

    # Clear stale rows (empty chain or previously rejected chain)
    frappe.db.delete("Contract Approver", {"parent": contract.name, "parentfield": "approvals"})

    for row_data in new_rows:
        child = frappe.new_doc("Contract Approver")
        child.update(row_data)
        child.parent = contract.name
        child.parenttype = "ERP Contract"
        child.parentfield = "approvals"
        child.insert(ignore_permissions=True)

    frappe.db.set_value(
        "ERP Contract", contract.name,
        "approval_status", "Pending Approval",
        update_modified=False,
    )

    # Reload so in-memory approvals reflect the newly inserted rows with DB names
    contract.reload()

    first = min(contract.approvals, key=lambda r: r.precedence)
    _share_with_role(contract, first.role)
    _notify_approvers(contract, first.role)


# ---------------------------------------------------------------------------
# Guard  (called from before_submit as the final gate)
# ---------------------------------------------------------------------------

def assert_approval_chain_complete(contract) -> None:
    """
    Raise if hierarchical approvals are enabled and the chain is not fully approved.
    Also raises if the feature is on but the chain was never initiated — this
    prevents bypassing approval by submitting directly without clicking
    "Request Approval".
    """
    if not get_approval_roles():
        return

    approvals = contract.get("approvals", [])
    if not approvals:
        frappe.throw(
            _("This contract requires hierarchical approval before submission. "
              "Please use the \"Request Approval\" button first."),
            title=_("Approval Required"),
        )

    for row in approvals:
        if row.approval_status != "Approved":
            frappe.throw(
                _("Contract cannot be submitted until all approvals are granted. "
                  "Step {0} ({1}) is still \"{2}\".").format(
                    row.precedence, row.role, row.approval_status
                ),
                title=_("Pending Approvals"),
            )


# ---------------------------------------------------------------------------
# Approve / Reject  (whitelisted — called from JS buttons)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def approve_contract(contract_name: str, signature: str | None = None) -> dict:
    """
    Record approval by the current user on the active Pending step.

    Any user who currently holds the step's role may approve; the acting user
    is stamped onto the row.  Advances the chain to the next step, or marks the
    contract Approved when done.

    Returns:
        chain_complete (bool): True when all steps are approved.
        next_role      (str | None): role of the next pending step, or None.
    """
    contract = frappe.get_doc("ERP Contract", contract_name)
    _assert_can_act(contract)

    pending_row = _get_pending_row(contract)
    _assert_can_approve(pending_row)

    frappe.db.set_value(
        "Contract Approver", pending_row.name,
        {
            "approval_status": "Approved",
            "user": frappe.session.user,
            "approved_on": now_datetime(),
            "signature": signature or "",
        },
        update_modified=False,
    )

    next_row = _next_row(contract, pending_row.precedence)
    if next_row:
        frappe.db.set_value(
            "Contract Approver", next_row.name,
            {"approval_status": "Pending"},
            update_modified=False,
        )
        _share_with_role(contract, next_row.role)
        _notify_approvers(contract, next_row.role)
        return {"chain_complete": False, "next_role": next_row.role}

    frappe.db.set_value(
        "ERP Contract", contract_name,
        {"approval_status": "Approved"},
        update_modified=False,
    )
    _notify_owner(contract, approved=True)
    return {"chain_complete": True, "next_role": None}


@frappe.whitelist()
def reject_contract(contract_name: str, reason: str) -> None:
    """
    Record rejection by the current user on the active Pending step.
    Halts the chain and marks the contract Rejected.
    """
    if not reason or not reason.strip():
        frappe.throw(_("A rejection reason is required."))

    contract = frappe.get_doc("ERP Contract", contract_name)
    _assert_can_act(contract)

    pending_row = _get_pending_row(contract)
    _assert_can_approve(pending_row)

    frappe.db.set_value(
        "Contract Approver", pending_row.name,
        {
            "approval_status": "Rejected",
            "user": frappe.session.user,
            "approved_on": now_datetime(),
            "rejection_reason": reason.strip(),
        },
        update_modified=False,
    )
    frappe.db.set_value(
        "ERP Contract", contract_name,
        {"approval_status": "Rejected"},
        update_modified=False,
    )
    _notify_owner(contract, approved=False, reason=reason.strip())


# ---------------------------------------------------------------------------
# Client-side context  (whitelisted — powers JS button visibility)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_approval_context(contract_name: str) -> dict:
    """
    Return everything the JS layer needs to render the approval UI.

    Keys:
        is_approver     — current user holds the role of the active Pending step
        can_request     — "Request Approval" button should be shown
        pending_row     — name of the Pending Contract Approver row (or None)
        approval_status — contract-level status string
        chain           — list of step dicts sorted by precedence
    """
    contract = frappe.get_doc("ERP Contract", contract_name)
    rows = contract.get("approvals", [])

    pending_row = next((r for r in rows if r.approval_status == "Pending"), None)
    user_roles = set(frappe.get_roles(frappe.session.user))
    is_approver = bool(pending_row and pending_row.role in user_roles)

    # can_request is True when: feature is on, not cancelled, not approved,
    # and no step is actively pending (covers both empty chain and rejected chain)
    can_request = (
        bool(get_approval_roles())
        and contract.docstatus != 2
        and contract.approval_status != "Approved"
        and pending_row is None
    )

    return {
        "is_approver": is_approver,
        "can_request": can_request,
        "pending_row": pending_row.name if pending_row else None,
        "approval_status": contract.approval_status or "Not Requested",
        "chain": [
            {
                "precedence": r.precedence,
                "role": r.role,
                "user": r.user,
                "approval_status": r.approval_status,
            }
            for r in sorted(rows, key=lambda r: r.precedence)
        ],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_pending_row(contract):
    """Return the single Pending row, or throw if none exists."""
    rows = [r for r in contract.get("approvals", []) if r.approval_status == "Pending"]
    if not rows:
        frappe.throw(_("No pending approval step found on this contract."))
    return rows[0]


def _next_row(contract, current_precedence: int):
    """Return the lowest-precedence Waiting row strictly above current_precedence, or None."""
    waiting = sorted(
        [
            r for r in contract.get("approvals", [])
            if r.approval_status == "Waiting" and r.precedence > current_precedence
        ],
        key=lambda r: r.precedence,
    )
    return waiting[0] if waiting else None


def _assert_can_act(contract) -> None:
    """Raise if the contract is cancelled or its approval chain is already decided."""
    if contract.docstatus == 2:
        frappe.throw(_("Cannot act on a cancelled contract."))
    if contract.approval_status in ("Approved", "Rejected"):
        frappe.throw(
            _("This contract has already been {0}.").format(
                contract.approval_status.lower()
            )
        )


def _assert_can_approve(pending_row) -> None:
    """Raise PermissionError unless the current user holds the step's role."""
    if pending_row.role not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            _("Only a user with the \"{0}\" role can act on this approval step.").format(
                pending_row.role
            ),
            frappe.PermissionError,
        )


def _share_with_role(contract, role: str) -> None:
    """Grant read access to every current holder of the role who lacks it."""
    if not role:
        return
    for user in get_users_with_role(role):
        if not user:
            continue
        if not frappe.has_permission(doc=contract, ptype="read", user=user):
            frappe.share.add_docshare(
                contract.doctype, contract.name, user,
                read=1,
                flags={"ignore_share_permission": True},
            )


def _notify_approvers(contract, role: str) -> None:
    """
    Notify the holders of ``role`` that it is their turn to act.

    follow_via_email = 1 → email every user who holds the role.
    follow_via_email = 0 → in-app Notification Log to every user who holds the role.

    Notification failures are logged but never propagated, so a mail/queue
    error can never roll back the recorded approval decision.
    """
    holders = [u for u in get_users_with_role(role) if u]
    if not holders:
        return

    link = frappe.utils.get_link_to_form("ERP Contract", contract.name)
    subject = _("Action Required: Contract {0} awaits your approval").format(contract.name)
    message = _(
        "Contract <b>{0}</b> requires approval from the <b>{1}</b> role.<br><br>"
        "Please open the contract and click <b>Approve</b> or <b>Reject</b>."
    ).format(link, role)

    try:
        if _get_follow_via_email():
            emails = [frappe.db.get_value("User", u, "email") or u for u in holders]
            if emails:
                frappe.sendmail(recipients=emails, subject=subject, message=message)
        else:
            for user in holders:
                _create_notification_log(subject, message, user, contract)
    except Exception:
        frappe.log_error(
            title="ERP Contract approval notification failed",
            message=frappe.get_traceback(),
        )


def _notify_owner(contract, approved: bool, reason: str = "") -> None:
    """
    Notify the contract owner of the final outcome (approved or rejected).
    Respects the follow_via_email setting.  Failures are logged, never raised.
    """
    link = frappe.utils.get_link_to_form("ERP Contract", contract.name)

    if approved:
        subject = _("Contract {0} has been fully approved").format(contract.name)
        message = _(
            "All approval steps for contract <b>{0}</b> have been completed.<br>"
            "The contract is now ready for submission."
        ).format(link)
    else:
        subject = _("Contract {0} was rejected").format(contract.name)
        message = _("Contract <b>{0}</b> was rejected.<br>Reason: {1}").format(link, reason)

    try:
        if _get_follow_via_email():
            owner_email = frappe.db.get_value("User", contract.owner, "email") or contract.owner
            frappe.sendmail(recipients=[owner_email], subject=subject, message=message)
        else:
            _create_notification_log(subject, message, contract.owner, contract)
    except Exception:
        frappe.log_error(
            title="ERP Contract approval notification failed",
            message=frappe.get_traceback(),
        )


def _create_notification_log(subject: str, message: str, user: str, contract) -> None:
    """Insert a Frappe in-app Notification Log (bell icon notification)."""
    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": subject,
        "email_content": message,
        "for_user": user,
        "type": "Alert",
        "document_type": "ERP Contract",
        "document_name": contract.name,
    }).insert(ignore_permissions=True)
