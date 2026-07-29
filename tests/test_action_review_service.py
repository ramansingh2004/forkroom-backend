from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    ActionAccessDeniedError,
    ActionAssigneeInvalidError,
    ActionInvalidTransitionError,
    DecisionImmutableError,
    ReviewAccessDeniedError,
    ReviewInvalidScheduleError,
)
from app.models.action_review import (
    ActionStatus,
    DecisionReview,
    ImplementationAction,
    ReviewStatus,
)
from app.models.decision import Decision, DecisionStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.repositories.action_review import ActionReviewRepository
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.action_review import (
    ActionCreateRequest,
    ActionTransitionRequest,
    ReviewCreateRequest,
)
from app.services.action_review import ActionReviewService


@pytest.fixture
def record_repository() -> AsyncMock:
    return AsyncMock(spec=ActionReviewRepository)


@pytest.fixture
def decision_repository() -> AsyncMock:
    return AsyncMock(spec=DecisionRepository)


@pytest.fixture
def workspace_repository() -> AsyncMock:
    return AsyncMock(spec=WorkspaceRepository)


@pytest.fixture
def service(
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> ActionReviewService:
    return ActionReviewService(
        record_repository,
        decision_repository,
        workspace_repository,
    )


def make_context(
    *,
    role: WorkspaceRole = WorkspaceRole.ADMIN,
    decision_status: DecisionStatus = DecisionStatus.LOCKED,
) -> tuple[User, Workspace, WorkspaceMember, Decision]:
    user = User(
        id=uuid4(),
        email="raman@example.com",
        password_hash="hash",
        display_name="Raman Singh",
    )
    workspace = Workspace(id=uuid4(), name="Backend Guild", owner_id=uuid4())
    membership = WorkspaceMember(
        id=uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    decision = Decision(
        id=uuid4(),
        workspace_id=workspace.id,
        created_by_id=user.id,
        title="Choose the backend framework",
        status=decision_status,
        locked_at=datetime.now(UTC) if decision_status is DecisionStatus.LOCKED else None,
    )
    return user, workspace, membership, decision


def grant_context(
    workspace_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace: Workspace,
    membership: WorkspaceMember,
    decision: Decision,
) -> None:
    workspace_repository.get_by_id.return_value = workspace
    workspace_repository.get_membership.return_value = membership
    decision_repository.get_for_workspace.return_value = decision


async def test_admin_creates_action_for_eligible_member(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    assignee_id = uuid4()
    assignee = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=assignee_id,
        role=WorkspaceRole.MEMBER,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    workspace_repository.get_membership.side_effect = [membership, assignee]
    record_repository.create_action.side_effect = lambda action: action

    action = await service.create_action(
        user,
        workspace.id,
        decision.id,
        ActionCreateRequest(
            title="Ship authentication migration",
            assignee_id=assignee_id,
            due_at=datetime.now(UTC) + timedelta(days=7),
        ),
    )

    assert action.status is ActionStatus.TODO
    assert action.assignee_id == assignee_id
    record_repository.create_action.assert_awaited_once()


async def test_member_cannot_create_action(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(role=WorkspaceRole.MEMBER)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )

    with pytest.raises(ActionAccessDeniedError):
        await service.create_action(
            user,
            workspace.id,
            decision.id,
            ActionCreateRequest(title="Deploy the service", assignee_id=user.id),
        )

    record_repository.create_action.assert_not_awaited()


async def test_action_requires_locked_decision(
    service: ActionReviewService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(decision_status=DecisionStatus.ACTIVE)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )

    with pytest.raises(DecisionImmutableError):
        await service.create_action(
            user,
            workspace.id,
            decision.id,
            ActionCreateRequest(title="Deploy the service", assignee_id=user.id),
        )


async def test_viewer_cannot_be_assigned_action(
    service: ActionReviewService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    viewer = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=uuid4(),
        role=WorkspaceRole.VIEWER,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    workspace_repository.get_membership.side_effect = [membership, viewer]

    with pytest.raises(ActionAssigneeInvalidError):
        await service.create_action(
            user,
            workspace.id,
            decision.id,
            ActionCreateRequest(
                title="Deploy the service",
                assignee_id=viewer.user_id,
            ),
        )


async def test_assignee_can_complete_action(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(role=WorkspaceRole.MEMBER)
    action = ImplementationAction(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        assignee_id=user.id,
        title="Deploy the service",
        status=ActionStatus.IN_PROGRESS,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    record_repository.get_action.return_value = action
    record_repository.transition_action.side_effect = lambda action, **values: action

    await service.transition_action(
        user,
        workspace.id,
        decision.id,
        action.id,
        ActionTransitionRequest(status=ActionStatus.COMPLETED),
    )

    kwargs = record_repository.transition_action.await_args.kwargs
    assert kwargs["status"] is ActionStatus.COMPLETED
    assert kwargs["completed_at"] is not None


async def test_unassigned_member_cannot_transition_action(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(role=WorkspaceRole.MEMBER)
    action = ImplementationAction(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=uuid4(),
        assignee_id=uuid4(),
        title="Deploy the service",
        status=ActionStatus.TODO,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    record_repository.get_action.return_value = action

    with pytest.raises(ActionAccessDeniedError):
        await service.transition_action(
            user,
            workspace.id,
            decision.id,
            action.id,
            ActionTransitionRequest(status=ActionStatus.IN_PROGRESS),
        )


async def test_terminal_action_cannot_transition(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    action = ImplementationAction(
        id=uuid4(),
        decision_id=decision.id,
        created_by_id=user.id,
        assignee_id=user.id,
        title="Deploy the service",
        status=ActionStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    record_repository.get_action.return_value = action

    with pytest.raises(ActionInvalidTransitionError):
        await service.transition_action(
            user,
            workspace.id,
            decision.id,
            action.id,
            ActionTransitionRequest(status=ActionStatus.TODO),
        )


async def test_admin_schedules_future_review(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    record_repository.create_review.side_effect = lambda review: review
    scheduled_for = datetime.now(UTC) + timedelta(days=90)

    review = await service.create_review(
        user,
        workspace.id,
        decision.id,
        ReviewCreateRequest(
            scheduled_for=scheduled_for,
            notes="Recheck traffic and operational cost assumptions.",
        ),
    )

    assert review.scheduled_for == scheduled_for
    assert review.scheduled_by_id == user.id


async def test_member_cannot_schedule_review(
    service: ActionReviewService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context(role=WorkspaceRole.MEMBER)
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )

    with pytest.raises(ReviewAccessDeniedError):
        await service.create_review(
            user,
            workspace.id,
            decision.id,
            ReviewCreateRequest(scheduled_for=datetime.now(UTC) + timedelta(days=30)),
        )


async def test_past_review_date_is_rejected(
    service: ActionReviewService,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )

    with pytest.raises(ReviewInvalidScheduleError):
        await service.create_review(
            user,
            workspace.id,
            decision.id,
            ReviewCreateRequest(scheduled_for=datetime.now(UTC) - timedelta(days=1)),
        )


async def test_cancel_review_preserves_record(
    service: ActionReviewService,
    record_repository: AsyncMock,
    decision_repository: AsyncMock,
    workspace_repository: AsyncMock,
) -> None:
    user, workspace, membership, decision = make_context()
    review = DecisionReview(
        id=uuid4(),
        decision_id=decision.id,
        scheduled_by_id=user.id,
        scheduled_for=datetime.now(UTC) + timedelta(days=30),
        status=ReviewStatus.SCHEDULED,
    )
    grant_context(
        workspace_repository,
        decision_repository,
        workspace,
        membership,
        decision,
    )
    record_repository.get_review.return_value = review
    record_repository.cancel_review.side_effect = lambda review, **_: review

    await service.cancel_review(
        user,
        workspace.id,
        decision.id,
        review.id,
    )

    record_repository.cancel_review.assert_awaited_once()
