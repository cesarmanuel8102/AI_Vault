from __future__ import annotations

import pytest

from ibkr_paper_30d.predecessor_retirement import (
    PredecessorLaunchInventory,
    PredecessorLaunchPath,
    PredecessorRetirementTombstone,
    authorize_launch_after_retirement,
    validate_retirement,
)


def _inventory(**overrides) -> PredecessorLaunchInventory:
    path = PredecessorLaunchPath(
        path_id="scheduled-day1",
        kind="SCHEDULED_TASK",
        enabled=False,
        can_reach_paper_port=False,
        launch_binding_sha256="1" * 64,
    )
    values = {
        "predecessor_epoch_id": "AUTONOMY_EPOCH_2",
        "complete": True,
        "scheduled_tasks": (path,),
        "at_logon_triggers": (),
        "services": (),
        "startup_entries": (),
        "managed_direct_invocations": (),
        "active_launch_receipt_sha256": "2" * 64,
        "historical_launch_receipt_sha256": ("2" * 64, "3" * 64),
    }
    values.update(overrides)
    return PredecessorLaunchInventory(**values)


def _observations():
    return {
        "scheduled-day1": {
            "rejected_before_execution_lock": True,
            "broker_connection_constructed": False,
            "broker_write_count": 0,
            "fallback_path_detected": False,
        }
    }


def test_complete_retired_inventory_produces_hash_bound_tombstone():
    inventory = _inventory()
    decision = validate_retirement(inventory, _observations())
    tombstone = PredecessorRetirementTombstone.create(
        inventory=inventory,
        decision=decision,
        target_successor_transition_sha256="4" * 64,
    )

    assert decision.status == "PASS"
    assert tombstone.predecessor_epoch_id == inventory.predecessor_epoch_id
    assert tombstone.historical_launch_receipt_sha256 == (
        "2" * 64,
        "3" * 64,
    )
    assert len(tombstone.sha256) == 64


@pytest.mark.parametrize(
    "inventory,observations,reason",
    [
        (_inventory(complete=False), _observations(), "INVENTORY_INCOMPLETE"),
        (
            _inventory(
                scheduled_tasks=(
                    PredecessorLaunchPath(
                        path_id="scheduled-day1",
                        kind="SCHEDULED_TASK",
                        enabled=True,
                        can_reach_paper_port=False,
                        launch_binding_sha256="1" * 64,
                    ),
                )
            ),
            _observations(),
            "PREDECESSOR_LAUNCH_PATH_ENABLED",
        ),
        (
            _inventory(
                managed_direct_invocations=(
                    PredecessorLaunchPath(
                        path_id="direct-day1",
                        kind="DIRECT_INVOCATION",
                        enabled=False,
                        can_reach_paper_port=True,
                        launch_binding_sha256="5" * 64,
                    ),
                )
            ),
            _observations(),
            "PREDECESSOR_PATH_CAN_REACH_4002",
        ),
        (_inventory(), {}, "LEGACY_REJECTION_EVIDENCE_MISSING"),
    ],
)
def test_incomplete_enabled_reachable_or_unproven_paths_block(
    inventory, observations, reason
):
    decision = validate_retirement(inventory, observations)
    assert decision.status == "BLOCK"
    assert reason in decision.reason_codes


def test_old_launch_receipts_must_reject_before_lock_and_broker():
    observations = _observations()
    observations["scheduled-day1"]["broker_connection_constructed"] = True
    observations["scheduled-day1"]["broker_write_count"] = 1

    decision = validate_retirement(_inventory(), observations)

    assert decision.status == "BLOCK"
    assert "LEGACY_LAUNCH_REACHED_BROKER" in decision.reason_codes
    assert "LEGACY_BROKER_WRITE_DETECTED" in decision.reason_codes


def test_tombstone_rejects_every_old_receipt_and_allows_exact_successor_supervision():
    inventory = _inventory()
    decision = validate_retirement(inventory, _observations())
    tombstone = PredecessorRetirementTombstone.create(
        inventory=inventory,
        decision=decision,
        target_successor_transition_sha256="4" * 64,
    )

    for receipt in (
        inventory.active_launch_receipt_sha256,
        *inventory.historical_launch_receipt_sha256,
    ):
        blocked = authorize_launch_after_retirement(
            tombstone,
            launch_binding_sha256=receipt,
            successor_transition_sha256="4" * 64,
            supervision_launch=False,
        )
        assert blocked.status == "BLOCK"
        assert blocked.broker_connection_permitted is False
        assert blocked.execution_lock_permitted is False
        assert blocked.reason_codes == ("PREDECESSOR_REACTIVATION_ATTEMPT",)

    allowed = authorize_launch_after_retirement(
        tombstone,
        launch_binding_sha256="f" * 64,
        successor_transition_sha256="4" * 64,
        supervision_launch=True,
    )
    assert allowed.status == "PASS"
    assert allowed.execution_lock_permitted is True
    assert allowed.broker_connection_permitted is True
