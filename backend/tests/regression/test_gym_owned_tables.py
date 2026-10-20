"""Every gym-owned table has gym_id (CLAUDE.md, PLAN.md §6).

A new table fails this test until it either has a non-null, indexed gym_id,
or is listed below with the reason it has none.
"""

from app.db.base import Base

NOT_GYM_OWNED = {
    # The tenants themselves.
    "gyms",
    # gym_id is null for platform admins; every other row has one (DB check).
    "staff_users",
    # Belong to a staff user, which carries the gym.
    "staff_branch_access",
    "staff_sessions",
    "staff_recovery_codes",
    # Staff sign-in tries: written before anyone is known, often for no account.
    "login_attempts",
    # Belong to a staff user, or to no account at all when the email or phone
    # typed is unknown.
    "staff_password_resets",
    # Belongs to a member, who carries the gym.
    "member_sessions",
    # Belongs to a staff user, who carries the gym (§18.6).
    "staff_push_subscriptions",
    # Belongs to a plan, which carries the gym.
    "plan_branches",
    # gym_id is null for platform-level actions.
    "activity_log",
    # What's new in GymBhai: ours, the same for every gym (§16.5, 10.4).
    "changelog_entries",
    # Our own price list, shared by every gym.
    "platform_plans",
    # The worker queue; a job's payload names the gym it is for.
    "jobs",
    # "This daily task has been queued for this date": the worker's, not a gym's.
    "scheduled_runs",
}


def test_gym_owned_tables_have_an_indexed_gym_id() -> None:
    for name, table in Base.metadata.tables.items():
        if name in NOT_GYM_OWNED:
            continue
        assert "gym_id" in table.c, f"{name} has no gym_id"
        column = table.c.gym_id
        assert not column.nullable, f"{name}.gym_id must not be null"
        assert any(index.columns.keys()[0] == "gym_id" for index in table.indexes), (
            f"{name}.gym_id is not indexed"
        )


def test_exemption_list_has_no_stale_entries() -> None:
    assert NOT_GYM_OWNED - set(Base.metadata.tables) == set()
