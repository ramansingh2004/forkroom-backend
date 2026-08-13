from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import (
    DecisionAccessDeniedError,
    DecisionImmutableError,
    DecisionInvalidTransitionError,
    DecisionNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionCategory, DecisionStatus
from app.models.integration import IntegrationEventType, IntegrationOutboxEvent
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.permissions.decision import can_delete_decisions, can_write_decisions
from app.repositories.decision import DecisionRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.decision import (
    DecisionCreateRequest,
    DecisionTransitionRequest,
    DecisionUpdateRequest,
)
from app.services.integration_delivery import IntegrationEventEmitter

ALLOWED_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.DRAFT: {
        DecisionStatus.ACTIVE,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.ACTIVE: {
        DecisionStatus.CLOSED,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.CLOSED: {
        DecisionStatus.ACTIVE,
        DecisionStatus.ARCHIVED,
    },
    DecisionStatus.LOCKED: set(),
    DecisionStatus.ARCHIVED: set(),
}

EDITABLE_STATUSES = {
    DecisionStatus.DRAFT,
    DecisionStatus.ACTIVE,
}


class DecisionService:
    def __init__(
        self,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
        integration_events: IntegrationEventEmitter | None = None,
    ) -> None:
        self._decisions = decision_repository
        self._workspaces = workspace_repository
        self._integration_events = integration_events

    async def create(
        self,
        current_user: User,
        workspace_id: UUID,
        payload: DecisionCreateRequest,
    ) -> Decision:
        membership = await self._require_membership(current_user.id, workspace_id)
        if not can_write_decisions(membership.role):
            raise DecisionAccessDeniedError
        return await self._decisions.create(
            Decision(
                workspace_id=workspace_id,
                created_by_id=current_user.id,
                title=payload.title,
                summary=payload.summary,
                category=payload.category,
                status=DecisionStatus.DRAFT,
                due_at=payload.due_at,
                review_at=payload.review_at,
            )
        )

    async def list_decisions(
        self,
        current_user: User,
        workspace_id: UUID,
        *,
        status: DecisionStatus | None,
        category: DecisionCategory | None,
        limit: int,
        offset: int,
    ) -> list[Decision]:
        await self._require_membership(current_user.id, workspace_id)
        return await self._decisions.list_for_workspace(
            workspace_id,
            status=status,
            category=category,
            limit=limit,
            offset=offset,
        )

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> Decision:
        await self._require_membership(current_user.id, workspace_id)
        return await self._require_decision(workspace_id, decision_id)

    async def update(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: DecisionUpdateRequest,
    ) -> Decision:
        membership = await self._require_membership(current_user.id, workspace_id)
        if not can_write_decisions(membership.role):
            raise DecisionAccessDeniedError
        decision = await self._require_decision(workspace_id, decision_id)
        if decision.status not in EDITABLE_STATUSES:
            raise DecisionImmutableError

        provided_fields = payload.model_fields_set
        values: dict[str, object] = {}
        if "title" in provided_fields and payload.title is not None:
            values["title"] = payload.title
        if "summary" in provided_fields:
            values["summary"] = payload.summary
        if "category" in provided_fields and payload.category is not None:
            values["category"] = payload.category
        if "due_at" in provided_fields:
            values["due_at"] = payload.due_at
        if "review_at" in provided_fields:
            values["review_at"] = payload.review_at

        due_at = payload.due_at if "due_at" in provided_fields else decision.due_at
        review_at = payload.review_at if "review_at" in provided_fields else decision.review_at
        if due_at is not None and review_at is not None and review_at <= due_at:
            raise DecisionInvalidTransitionError
        return await self._decisions.update(decision, values=values)

    async def transition(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: DecisionTransitionRequest,
    ) -> Decision:
        membership = await self._require_membership(current_user.id, workspace_id)
        if not can_write_decisions(membership.role):
            raise DecisionAccessDeniedError
        decision = await self._require_decision(workspace_id, decision_id)
        if decision.status is DecisionStatus.LOCKED:
            raise DecisionImmutableError
        if payload.status not in ALLOWED_TRANSITIONS[decision.status]:
            raise DecisionInvalidTransitionError

        now = datetime.now(UTC)
        closed_at = now if payload.status is DecisionStatus.CLOSED else None
        archived_at = now if payload.status is DecisionStatus.ARCHIVED else None
        outbox_event: IntegrationOutboxEvent | None = None
        if (
            self._integration_events is not None
            and decision.status is DecisionStatus.DRAFT
            and payload.status is DecisionStatus.ACTIVE
        ):
            outbox_event = self._integration_events.stage(
                workspace_id=workspace_id,
                event_type=IntegrationEventType.DECISION_ACTIVATED,
                event_id=decision.id,
                payload={
                    "workspace_id": str(workspace_id),
                    "decision_id": str(decision.id),
                    "decision_title": decision.title,
                    "actor_id": str(current_user.id),
                    "actor_name": current_user.display_name,
                    "activated_at": now.isoformat(),
                },
            )
        updated = await self._decisions.transition(
            decision,
            status=payload.status,
            closed_at=closed_at,
            archived_at=archived_at,
        )
        if outbox_event is not None and self._integration_events is not None:
            self._integration_events.publish(outbox_event)
        return updated

    async def delete(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> None:
        membership = await self._require_membership(current_user.id, workspace_id)
        if not can_delete_decisions(membership.role):
            raise DecisionAccessDeniedError
        decision = await self._require_decision(workspace_id, decision_id)
        if decision.status is not DecisionStatus.DRAFT:
            raise DecisionImmutableError
        await self._decisions.delete(decision)

    async def _require_membership(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceMember:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        return membership

    async def _require_decision(
        self,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> Decision:
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        return decision
