from __future__ import annotations

from app.mission_contract import (
    Mission,
    MissionCreate,
    MissionRepository,
    MissionState,
    MissionUserProjection,
)


class InMemoryMissionRepository:
    def __init__(self) -> None:
        self.items: dict[str, Mission] = {}

    def create(self, owner_id: int, request: MissionCreate) -> Mission:
        mission = Mission(owner_id=owner_id, **request.model_dump())
        self.items[mission.id] = mission
        return mission

    def get_for_owner(self, owner_id: int, mission_id: str) -> Mission | None:
        mission = self.items.get(mission_id)
        return mission if mission and mission.owner_id == owner_id else None

    def list_for_owner(self, owner_id: int, limit: int = 100) -> list[Mission]:
        return [item for item in self.items.values() if item.owner_id == owner_id][:limit]

    def update_state_for_owner(
        self,
        owner_id: int,
        mission_id: str,
        state: MissionState,
    ) -> Mission | None:
        mission = self.get_for_owner(owner_id, mission_id)
        if mission is None:
            return None
        mission.state = state
        return mission

    def get_for_admin(self, mission_id: str) -> Mission | None:
        return self.items.get(mission_id)

    def list_for_admin(self, limit: int = 100) -> list[Mission]:
        return list(self.items.values())[:limit]


def request(title: str = "Audit") -> MissionCreate:
    return MissionCreate(
        title=title,
        target_ref="https://example.com",
        input_snapshot={"requested_mode": "company-audit"},
        correlation_id="corr-1",
    )


def test_repository_contract_is_replaceable() -> None:
    repository = InMemoryMissionRepository()

    assert isinstance(repository, MissionRepository)


def test_owner_is_supplied_by_repository_boundary() -> None:
    repository = InMemoryMissionRepository()

    mission = repository.create(42, request())

    assert mission.owner_id == 42
    assert "owner_id" not in request().model_dump()


def test_cross_user_reads_and_writes_are_hidden() -> None:
    repository = InMemoryMissionRepository()
    mission = repository.create(1, request())

    assert repository.get_for_owner(2, mission.id) is None
    assert repository.update_state_for_owner(2, mission.id, MissionState.COMPLETED) is None
    assert repository.get_for_owner(1, mission.id).state == MissionState.RUNNING


def test_user_projection_excludes_owner_and_technical_snapshot() -> None:
    mission = Mission(
        owner_id=7,
        title="Audit",
        target_ref="https://example.com",
        input_snapshot={"public": True},
        technical_snapshot={"provider_secret": "must-not-leak", "trace": ["internal"]},
        correlation_id="corr-1",
    )

    payload = MissionUserProjection.from_mission(mission).model_dump()

    assert "owner_id" not in payload
    assert "input_snapshot" not in payload
    assert "technical_snapshot" not in payload
    assert "provider_secret" not in str(payload)


def test_typed_states_cover_product_contract() -> None:
    assert {state.value for state in MissionState} == {
        "running",
        "degraded",
        "blocked",
        "completed",
    }
