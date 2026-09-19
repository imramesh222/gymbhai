from app.core.permissions import (
    ALL_PERMISSIONS,
    PRESETS,
    Permission,
    effective_permissions,
    parse_permissions,
    ungrantable,
)


def test_the_owner_has_everything_whatever_is_stored() -> None:
    assert effective_permissions(is_owner=True, stored=[]) == ALL_PERMISSIONS


def test_staff_have_exactly_what_was_ticked() -> None:
    assert effective_permissions(is_owner=False, stored=["members.view"]) == {
        Permission.MEMBERS_VIEW
    }


def test_unknown_stored_keys_are_ignored_not_fatal() -> None:
    assert parse_permissions(["members.view", "retired.permission"]) == {
        Permission.MEMBERS_VIEW
    }


def test_presets_are_starting_points_within_the_catalogue() -> None:
    assert set(PRESETS) == {"manager", "front_desk", "blank"}
    for preset in PRESETS.values():
        assert preset <= ALL_PERMISSIONS
    assert Permission.STAFF_MANAGE not in PRESETS["manager"]
    assert PRESETS["blank"] == frozenset()


def test_every_permission_in_plan_section_2_1_exists() -> None:
    # Guards against a key being dropped by accident: 29 ticks on the form.
    assert len(ALL_PERMISSIONS) == 29


def test_staff_can_only_grant_what_they_hold() -> None:
    granter = frozenset({Permission.STAFF_MANAGE, Permission.MEMBERS_VIEW})
    refused = ungrantable(
        granter,
        granter_is_owner=False,
        requested=["members.view", "payments.void"],
    )
    assert refused == ["payments.void"]


def test_staff_can_never_grant_manage_staff() -> None:
    granter = frozenset({Permission.STAFF_MANAGE})
    assert ungrantable(granter, granter_is_owner=False, requested=["staff.manage"]) == [
        "staff.manage"
    ]


def test_the_owner_can_grant_anything_known() -> None:
    assert (
        ungrantable(
            frozenset(), granter_is_owner=True, requested=[p.value for p in Permission]
        )
        == []
    )


def test_unknown_keys_are_never_grantable() -> None:
    assert ungrantable(frozenset(), granter_is_owner=True, requested=["root"]) == [
        "root"
    ]
