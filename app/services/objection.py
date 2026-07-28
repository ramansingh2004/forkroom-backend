from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionNotFoundError,
    ObjectionAccessDeniedError,
    ObjectionImmutableError,
    ObjectionInvalidTransitionError,
    ObjectionNotFoundError,
    ProposalImmutableError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionStatus
from app.models.objection import (
    Objection,
    ObjectionSeverity,
    ObjectionStatus,
    ObjectionStatusEvent,
)
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.permissions.objection import (
    can_create_objections,
    can_edit_objection,
    can_transition_objection,
)
from app.repositories.decision import DecisionRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.objection import (
    ObjectionCreateRequest,
    ObjectionTransitionRequest,
    ObjectionUpdateRequest,
)

MUTABLE_DECISION_STATUSES = {
    DecisionStatus.DRAFT,
    DecisionStatus.ACTIVE,
}

OBJECTION_TRANSITIONS: dict[ObjectionStatus, set[ObjectionStatus]] = {
    ObjectionStatus.OPEN: {
        ObjectionStatus.RESOLVED,
        ObjectionStatus.DISMISSED,
    },
    ObjectionStatus.RESOLVED: {ObjectionStatus.OPEN},
    ObjectionStatus.DISMISSED: {ObjectionStatus.OPEN},
}


class ObjectionService:
    def __init__(
        self,
        objection_repository: ObjectionRepository,
        proposal_repository: ProposalRepository,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._objections = objection_repository
        self._proposals = proposal_repository
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def create(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        payload: ObjectionCreateRequest,
    ) -> Objection:
        membership, decision, proposal = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
            proposal_id,
        )
        self._require_mutable_decision(decision)
        if not can_create_objections(membership.role):
            raise ObjectionAccessDeniedError
        if proposal.status is not ProposalStatus.SUBMITTED:
            raise ProposalImmutableError
        return await self._objections.create(
            Objection(
                proposal_id=proposal_id,
                created_by_id=current_user.id,
                severity=payload.severity,
                status=ObjectionStatus.OPEN,
                title=payload.title,
                description=payload.description,
            )
        )

    async def list_objections(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        *,
        severity: ObjectionSeverity | None,
        status: ObjectionStatus | None,
    ) -> list[Objection]:
        await self._context(current_user.id, workspace_id, decision_id, proposal_id)
        return await self._objections.list_for_proposal(
            proposal_id,
            severity=severity,
            status=status,
        )

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        objection_id: UUID,
    ) -> Objection:
        await self._context(current_user.id, workspace_id, decision_id, proposal_id)
        return await self._require_objection(proposal_id, objection_id)

    async def update(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        objection_id: UUID,
        payload: ObjectionUpdateRequest,
    ) -> Objection:
        membership, decision, _ = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
            proposal_id,
        )
        self._require_mutable_decision(decision)
        objection = await self._require_objection(proposal_id, objection_id)
        if not can_edit_objection(
            membership.role,
            objection_author_id=objection.created_by_id,
            user_id=current_user.id,
        ):
            raise ObjectionAccessDeniedError
        if objection.status is not ObjectionStatus.OPEN:
            raise ObjectionImmutableError

        fields = payload.model_fields_set
        values: dict[str, object] = {}
        if "severity" in fields and payload.severity is not None:
            values["severity"] = payload.severity
        if "title" in fields and payload.title is not None:
            values["title"] = payload.title
        if "description" in fields and payload.description is not None:
            values["description"] = payload.description
        return await self._objections.update(objection, values=values)

    async def transition(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        objection_id: UUID,
        payload: ObjectionTransitionRequest,
    ) -> Objection:
        membership, decision, _ = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
            proposal_id,
        )
        self._require_mutable_decision(decision)
        objection = await self._require_objection(proposal_id, objection_id)
        if payload.status not in OBJECTION_TRANSITIONS[objection.status]:
            raise ObjectionInvalidTransitionError
        if not can_transition_objection(
            membership.role,
            objection_author_id=objection.created_by_id,
            user_id=current_user.id,
            target_status=payload.status,
        ):
            raise ObjectionAccessDeniedError

        resolved_at = None
        if payload.status is not ObjectionStatus.OPEN:
            resolved_at = datetime.now(UTC)
        return await self._objections.transition(
            objection,
            actor_id=current_user.id,
            status=payload.status,
            note=payload.note,
            resolved_at=resolved_at,
        )

    async def list_history(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        objection_id: UUID,
    ) -> list[ObjectionStatusEvent]:
        await self._context(current_user.id, workspace_id, decision_id, proposal_id)
        objection = await self._require_objection(proposal_id, objection_id)
        return await self._objections.list_status_events(objection.id)

    async def _context(
        self,
        user_id: UUID,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> tuple[WorkspaceMember, Decision, Proposal]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        proposal = await self._proposals.get_for_decision(decision_id, proposal_id)
        if proposal is None:
            raise ProposalNotFoundError
        return membership, decision, proposal

    @staticmethod
    def _require_mutable_decision(decision: Decision) -> None:
        if decision.status not in MUTABLE_DECISION_STATUSES:
            raise DecisionImmutableError

    async def _require_objection(
        self,
        proposal_id: UUID,
        objection_id: UUID,
    ) -> Objection:
        objection = await self._objections.get_for_proposal(proposal_id, objection_id)
        if objection is None:
            raise ObjectionNotFoundError
        return objection
