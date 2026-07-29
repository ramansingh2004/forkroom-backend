from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import (
    ActionAccessDeniedError,
    ActionAssigneeInvalidError,
    ActionInvalidTransitionError,
    ActionNotFoundError,
    DecisionImmutableError,
    DecisionNotFoundError,
    DecisionRevisionNotFoundError,
    ReviewAccessDeniedError,
    ReviewInvalidScheduleError,
    ReviewNotDueError,
    ReviewNotFoundError,
    ReviewOutcomeInvalidError,
    WorkspaceNotFoundError,
)
from app.models.action_review import (
    ActionStatus,
    DecisionReview,
    DecisionRevision,
    ImplementationAction,
    ReviewOutcome,
    ReviewStatus,
)
from app.models.decision import Decision, DecisionStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole
from app.permissions.action_review import (
    can_manage_actions,
    can_manage_reviews,
    can_transition_action,
)
from app.repositories.action_review import ActionReviewRepository
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.action_review import (
    ActionCreateRequest,
    ActionTransitionRequest,
    ActionUpdateRequest,
    ReviewCreateRequest,
    ReviewOutcomeRequest,
    ReviewUpdateRequest,
)

ACTION_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.TODO: {
        ActionStatus.IN_PROGRESS,
        ActionStatus.BLOCKED,
        ActionStatus.COMPLETED,
        ActionStatus.CANCELLED,
    },
    ActionStatus.IN_PROGRESS: {
        ActionStatus.TODO,
        ActionStatus.BLOCKED,
        ActionStatus.COMPLETED,
        ActionStatus.CANCELLED,
    },
    ActionStatus.BLOCKED: {
        ActionStatus.TODO,
        ActionStatus.IN_PROGRESS,
        ActionStatus.COMPLETED,
        ActionStatus.CANCELLED,
    },
    ActionStatus.COMPLETED: set(),
    ActionStatus.CANCELLED: set(),
}


@dataclass(frozen=True, slots=True)
class ReviewOutcomeResult:
    review: DecisionReview
    revision: DecisionRevision | None
    successor_decision: Decision | None


class ActionReviewService:
    def __init__(
        self,
        repository: ActionReviewRepository,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._records = repository
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def create_action(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: ActionCreateRequest,
    ) -> ImplementationAction:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_actions(membership.role):
            raise ActionAccessDeniedError
        self._require_locked(decision)
        await self._require_eligible_assignee(workspace_id, payload.assignee_id)
        return await self._records.create_action(
            ImplementationAction(
                decision_id=decision.id,
                created_by_id=current_user.id,
                assignee_id=payload.assignee_id,
                title=payload.title,
                description=payload.description,
                status=ActionStatus.TODO,
                due_at=payload.due_at,
            )
        )

    async def list_actions(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        *,
        status: ActionStatus | None,
        assignee_id: UUID | None,
    ) -> list[ImplementationAction]:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._records.list_actions(
            decision_id,
            status=status,
            assignee_id=assignee_id,
        )

    async def get_action(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        action_id: UUID,
    ) -> ImplementationAction:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._require_action(decision_id, action_id)

    async def update_action(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        action_id: UUID,
        payload: ActionUpdateRequest,
    ) -> ImplementationAction:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_actions(membership.role):
            raise ActionAccessDeniedError
        self._require_locked(decision)
        action = await self._require_action(decision_id, action_id)
        if action.status in {ActionStatus.COMPLETED, ActionStatus.CANCELLED}:
            raise ActionInvalidTransitionError

        values: dict[str, object] = {}
        for field in payload.model_fields_set:
            value = getattr(payload, field)
            if field == "assignee_id" and value is not None:
                await self._require_eligible_assignee(workspace_id, value)
            values[field] = value
        return await self._records.update_action(action, values=values)

    async def transition_action(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        action_id: UUID,
        payload: ActionTransitionRequest,
    ) -> ImplementationAction:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_locked(decision)
        action = await self._require_action(decision_id, action_id)
        if not can_transition_action(
            membership.role,
            actor_id=current_user.id,
            assignee_id=action.assignee_id,
        ):
            raise ActionAccessDeniedError
        if payload.status not in ACTION_TRANSITIONS[action.status]:
            raise ActionInvalidTransitionError

        now = datetime.now(UTC)
        return await self._records.transition_action(
            action,
            status=payload.status,
            completed_at=now if payload.status is ActionStatus.COMPLETED else None,
            cancelled_at=now if payload.status is ActionStatus.CANCELLED else None,
        )

    async def create_review(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: ReviewCreateRequest,
    ) -> DecisionReview:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_reviews(membership.role):
            raise ReviewAccessDeniedError
        self._require_locked(decision)
        self._require_future_review(payload.scheduled_for)
        return await self._records.create_review(
            DecisionReview(
                decision_id=decision.id,
                scheduled_by_id=current_user.id,
                scheduled_for=payload.scheduled_for,
                status=ReviewStatus.SCHEDULED,
                notes=payload.notes,
            )
        )

    async def list_reviews(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> list[DecisionReview]:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._records.list_reviews(decision_id)

    async def get_review(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        review_id: UUID,
    ) -> DecisionReview:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._require_review(decision_id, review_id)

    async def update_review(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        review_id: UUID,
        payload: ReviewUpdateRequest,
    ) -> DecisionReview:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_reviews(membership.role):
            raise ReviewAccessDeniedError
        self._require_locked(decision)
        review = await self._require_review(decision_id, review_id)
        if review.status is not ReviewStatus.SCHEDULED:
            raise ReviewInvalidScheduleError

        values: dict[str, object] = {}
        for field in payload.model_fields_set:
            value = getattr(payload, field)
            if field == "scheduled_for":
                if value is None:
                    raise ReviewInvalidScheduleError
                self._require_future_review(value)
            values[field] = value
        return await self._records.update_review(review, values=values)

    async def cancel_review(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        review_id: UUID,
    ) -> DecisionReview:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_reviews(membership.role):
            raise ReviewAccessDeniedError
        self._require_locked(decision)
        review = await self._require_review(decision_id, review_id)
        if review.status is not ReviewStatus.SCHEDULED:
            raise ReviewInvalidScheduleError
        return await self._records.cancel_review(
            review,
            cancelled_by_id=current_user.id,
            cancelled_at=datetime.now(UTC),
        )

    async def complete_review(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        review_id: UUID,
        payload: ReviewOutcomeRequest,
    ) -> ReviewOutcomeResult:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_manage_reviews(membership.role):
            raise ReviewAccessDeniedError
        self._require_locked(decision)
        review = await self._require_review(decision_id, review_id)
        if review.status is not ReviewStatus.SCHEDULED:
            raise ReviewOutcomeInvalidError

        now = datetime.now(UTC)
        if review.scheduled_for > now:
            raise ReviewNotDueError

        if payload.outcome is ReviewOutcome.CONFIRMED:
            completed = await self._records.complete_review(
                review,
                outcome=payload.outcome,
                rationale=payload.rationale,
                completed_by_id=current_user.id,
                completed_at=now,
            )
            return ReviewOutcomeResult(completed, None, None)

        decision_lock = await self._records.get_decision_lock(decision.id)
        if decision_lock is None:
            raise ReviewOutcomeInvalidError
        root_decision_id = await self._records.get_revision_root(decision.id)
        revision_number = await self._records.next_revision_number(root_decision_id)
        successor = Decision(
            id=uuid4(),
            workspace_id=decision.workspace_id,
            created_by_id=current_user.id,
            title=payload.successor_title or decision.title,
            summary=(
                payload.successor_summary
                if payload.successor_summary is not None
                else decision.summary
            ),
            category=payload.successor_category or decision.category,
            status=DecisionStatus.DRAFT,
            due_at=None,
            review_at=None,
        )
        revision = DecisionRevision(
            id=uuid4(),
            root_decision_id=root_decision_id,
            predecessor_decision_id=decision.id,
            successor_decision_id=successor.id,
            source_lock_id=decision_lock.id,
            review_id=review.id,
            created_by_id=current_user.id,
            revision_number=revision_number,
            outcome=payload.outcome,
            rationale=payload.rationale,
        )
        (
            completed,
            created_revision,
            created_successor,
        ) = await self._records.complete_review_with_revision(
            review,
            successor,
            revision,
            completed_by_id=current_user.id,
            completed_at=now,
        )
        return ReviewOutcomeResult(
            completed,
            created_revision,
            created_successor,
        )

    async def list_revisions(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> list[DecisionRevision]:
        await self._context(current_user.id, workspace_id, decision_id)
        root_decision_id = await self._records.get_revision_root(decision_id)
        return await self._records.list_revisions(root_decision_id)

    async def get_revision(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        revision_id: UUID,
    ) -> DecisionRevision:
        await self._context(current_user.id, workspace_id, decision_id)
        root_decision_id = await self._records.get_revision_root(decision_id)
        revision = await self._records.get_revision(root_decision_id, revision_id)
        if revision is None:
            raise DecisionRevisionNotFoundError
        return revision

    async def _context(
        self,
        user_id: UUID,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> tuple[WorkspaceMember, Decision]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if workspace is None or membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        return membership, decision

    async def _require_eligible_assignee(
        self,
        workspace_id: UUID,
        assignee_id: UUID,
    ) -> None:
        membership = await self._workspaces.get_membership(workspace_id, assignee_id)
        if membership is None or membership.role is WorkspaceRole.VIEWER:
            raise ActionAssigneeInvalidError

    async def _require_action(
        self,
        decision_id: UUID,
        action_id: UUID,
    ) -> ImplementationAction:
        action = await self._records.get_action(decision_id, action_id)
        if action is None:
            raise ActionNotFoundError
        return action

    async def _require_review(
        self,
        decision_id: UUID,
        review_id: UUID,
    ) -> DecisionReview:
        review = await self._records.get_review(decision_id, review_id)
        if review is None:
            raise ReviewNotFoundError
        return review

    @staticmethod
    def _require_locked(decision: Decision) -> None:
        if decision.status is not DecisionStatus.LOCKED:
            raise DecisionImmutableError

    @staticmethod
    def _require_future_review(scheduled_for: datetime) -> None:
        if scheduled_for <= datetime.now(UTC):
            raise ReviewInvalidScheduleError
