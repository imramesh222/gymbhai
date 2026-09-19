"""Staff permissions (PLAN.md §2.1).

There are no roles. The owner has every permission, always; everyone else has
exactly the keys the owner ticked. Keys are stored as strings on the staff row,
so renaming one is a data migration, not a code change.
"""

from collections.abc import Iterable
from enum import StrEnum


class Permission(StrEnum):
    # Members
    MEMBERS_VIEW = "members.view"
    MEMBERS_ADD = "members.add"
    MEMBERS_EDIT = "members.edit"
    MEMBERS_ARCHIVE = "members.archive"
    MEMBERS_APP_ACCESS = "members.app_access"
    # Memberships
    MEMBERSHIPS_SELL = "memberships.sell"
    MEMBERSHIPS_EDIT = "memberships.edit"
    MEMBERSHIPS_EXTEND = "memberships.extend"
    MEMBERSHIPS_EXTEND_ALL = "memberships.extend_all"
    MEMBERSHIPS_FREEZE = "memberships.freeze"
    MEMBERSHIPS_CANCEL = "memberships.cancel"
    MEMBERSHIPS_DELETE = "memberships.delete"
    # Money
    PAYMENTS_COLLECT = "payments.collect"
    PAYMENTS_APPROVE_APP = "payments.approve_app"
    PAYMENTS_EDIT = "payments.edit"
    PAYMENTS_VOID = "payments.void"
    PAYMENTS_REFUND = "payments.refund"
    REPORTS_MONEY = "reports.money"
    # Door
    DOOR_CHECK_IN = "door.check_in"
    DOOR_OVERRIDE = "door.override"
    # Messages
    MESSAGES_NOTICES = "messages.notices"
    MESSAGES_SMS = "messages.sms"
    # Gym setup
    SETUP_PLANS = "setup.plans"
    SETUP_PAYMENT_METHODS = "setup.payment_methods"
    SETUP_REMINDERS = "setup.reminders"
    SETUP_CHECK_IN_RULES = "setup.check_in_rules"
    SETUP_DEVICES = "setup.devices"
    SETUP_GYM = "setup.gym"
    # Staff
    STAFF_MANAGE = "staff.manage"


ALL_PERMISSIONS = frozenset(Permission)

# Nobody but the owner can hand this out (PLAN.md §2.1).
OWNER_ONLY_GRANT = frozenset({Permission.STAFF_MANAGE})

# Starting points on the staff form. The owner changes them freely afterwards;
# nothing remembers which preset an account started from.
PRESETS: dict[str, frozenset[Permission]] = {
    # "Almost everything": not staff management, and not the two actions the
    # plan keeps with the owner by default — voiding payments and deleting
    # memberships.
    "manager": ALL_PERMISSIONS
    - {
        Permission.STAFF_MANAGE,
        Permission.PAYMENTS_VOID,
        Permission.MEMBERSHIPS_DELETE,
    },
    "front_desk": frozenset(
        {
            Permission.MEMBERS_VIEW,
            Permission.MEMBERS_ADD,
            Permission.MEMBERS_EDIT,
            Permission.MEMBERSHIPS_SELL,
            Permission.PAYMENTS_COLLECT,
            Permission.DOOR_CHECK_IN,
        }
    ),
    "blank": frozenset(),
}


def parse_permissions(keys: Iterable[str]) -> frozenset[Permission]:
    """Stored keys to permissions, dropping any this build no longer knows."""
    known = {p.value for p in Permission}
    return frozenset(Permission(k) for k in keys if k in known)


def effective_permissions(
    *, is_owner: bool, stored: Iterable[str]
) -> frozenset[Permission]:
    if is_owner:
        return ALL_PERMISSIONS
    return parse_permissions(stored)


def ungrantable(
    granter: frozenset[Permission], *, granter_is_owner: bool, requested: Iterable[str]
) -> list[str]:
    """Which of `requested` the granter may not give, sorted. Empty means allowed.

    Staff with Manage staff can only give permissions they hold themselves, and
    never Manage staff. Unknown keys are never grantable.
    """
    requested = set(requested)
    known = {p.value for p in Permission}
    refused = requested - known
    for key in requested & known:
        permission = Permission(key)
        if granter_is_owner:
            continue
        if permission in OWNER_ONLY_GRANT or permission not in granter:
            refused.add(key)
    return sorted(refused)
