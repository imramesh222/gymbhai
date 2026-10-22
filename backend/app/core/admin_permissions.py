"""What a platform admin (us) may do in /admin (PLAN.md §2, §7).

As in a gym (§2.1), no roles: the super admin has everything and alone adds
and changes admins; every other admin has exactly the keys the super admin
ticked. Seeing the gyms and the numbers needs no key. Stored on the admin's
`staff_users.permissions`, like a gym's staff.
"""

from enum import StrEnum

from app.models.staff import StaffUser


class AdminPermission(StrEnum):
    # Payments gyms send us, giving a subscription or message credits, and
    # the free months for a gym that sent us a gym (§5.7, §16.5 10.5).
    BILLING = "admin.billing"
    # Suspending a gym, and resetting an owner's password or two-step sign-in.
    GYM_ACCOUNTS = "admin.gym_accounts"
    # Our plans and prices, and the prices of messages and gyms' own apps.
    PRICING = "admin.pricing"
    # Gyms' own phone apps (§20.3).
    APPS = "admin.apps"
    # What's new (§16.5, 10.4).
    CHANGELOG = "admin.changelog"
    # Adding admins and changing what they may do: the super admin's alone.
    ADMINS = "admin.admins"


GRANTABLE = frozenset(AdminPermission) - {AdminPermission.ADMINS}


def effective(staff: StaffUser) -> set[str]:
    """Every key for the super admin; the ticked ones for anyone else."""
    if staff.is_super_admin:
        return {p.value for p in AdminPermission}
    return {p for p in staff.permissions if p in GRANTABLE}
