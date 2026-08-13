from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.integration import IntegrationEventType, IntegrationOutboxEvent
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.voting import VotingSession, VotingSessionStatus
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.voting import VotingRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.decision import DecisionTransitionRequest
from app.services.decision import DecisionService
from app.services.integration_delivery import IntegrationEventEmitter
from app.services.voting import VotingService


def user_and_context() -> tuple[User, Workspace, Decision, WorkspaceMember]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
        is_active=True,
    )
    workspace = Workspace(id=uuid4(), name="ForkRoom", owner_id=user.id)
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose an API framework",
        category=DecisionCategory.TECHNOLOGY,
        status=DecisionStatus.DRAFT,
    )
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.OWNER,
    )
    return user, workspace, decision, membership


def outbox_event(
    workspace_id: object,
    event_type: IntegrationEventType,
    event_id: object,
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        id=uuid4(),
        workspace_id=workspace_id,
        event_type=event_type,
        event_id=event_id,
        payload={},
        available_at=datetime.now(UTC),
    )


async def test_decision_activation_stages_and_publishes_outbox_event() -> None:
    user, workspace, decision, membership = user_and_context()
    decisions = AsyncMock(spec=DecisionRepository)
    workspaces = AsyncMock(spec=WorkspaceRepository)
    emitter = Mock(spec=IntegrationEventEmitter)
    event = outbox_event(
        workspace.id,
        IntegrationEventType.DECISION_ACTIVATED,
        decision.id,
    )
    emitter.stage.return_value = event
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = membership
    decisions.get_for_workspace.return_value = decision
    decisions.transition.side_effect = lambda item, **_: item
    service = DecisionService(decisions, workspaces, emitter)

    await service.transition(
        user,
        workspace.id,
        decision.id,
        DecisionTransitionRequest(status=DecisionStatus.ACTIVE),
    )

    assert emitter.stage.call_args.kwargs["event_type"] is IntegrationEventType.DECISION_ACTIVATED
    assert emitter.stage.call_args.kwargs["payload"]["decision_title"] == decision.title
    emitter.publish.assert_called_once_with(event)


async def test_voting_open_and_close_publish_distinct_events() -> None:
    user, workspace, decision, membership = user_and_context()
    decision.status = DecisionStatus.ACTIVE
    voting = AsyncMock(spec=VotingRepository)
    objections = AsyncMock(spec=ObjectionRepository)
    proposals = AsyncMock(spec=ProposalRepository)
    decisions = AsyncMock(spec=DecisionRepository)
    workspaces = AsyncMock(spec=WorkspaceRepository)
    emitter = Mock(spec=IntegrationEventEmitter)
    session = VotingSession(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        status=VotingSessionStatus.DRAFT,
        quorum_percentage=60,
    )
    candidates = [
        Proposal(
            id=uuid4(),
            decision_id=decision.id,
            created_by_id=user.id,
            title=title,
            status=ProposalStatus.SUBMITTED,
        )
        for title in ("FastAPI", "Django")
    ]
    opened_event = outbox_event(
        workspace.id,
        IntegrationEventType.VOTING_OPENED,
        session.id,
    )
    closed_event = outbox_event(
        workspace.id,
        IntegrationEventType.VOTING_CLOSED,
        session.id,
    )
    emitter.stage.side_effect = [opened_event, closed_event]
    workspaces.get_by_id.return_value = workspace
    workspaces.get_membership.return_value = membership
    workspaces.list_voting_eligible_user_ids.return_value = [user.id]
    decisions.get_for_workspace.return_value = decision
    voting.get_for_decision.return_value = session
    objections.has_open_blocking_for_decision.return_value = False
    proposals.list_for_decision.return_value = candidates

    async def open_session(item: VotingSession, **_: object) -> VotingSession:
        item.status = VotingSessionStatus.OPEN
        return item

    async def close_session(item: VotingSession, **_: object) -> VotingSession:
        item.status = VotingSessionStatus.CLOSED
        return item

    voting.open.side_effect = open_session
    voting.close.side_effect = close_session
    service = VotingService(voting, objections, proposals, decisions, workspaces, emitter)

    await service.open_session(user, workspace.id, decision.id, session.id)
    await service.close_session(user, workspace.id, decision.id, session.id)

    event_types = [call.kwargs["event_type"] for call in emitter.stage.call_args_list]
    assert event_types == [
        IntegrationEventType.VOTING_OPENED,
        IntegrationEventType.VOTING_CLOSED,
    ]
    assert emitter.publish.call_args_list[0].args == (opened_event,)
    assert emitter.publish.call_args_list[1].args == (closed_event,)
