import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import (
    DecisionImmutableError,
    DecisionLockAccessDeniedError,
    DecisionLockConflictError,
    DecisionLockInvalidResultError,
    DecisionLockNotFoundError,
    DecisionNotFoundError,
    ProposalNotFoundError,
    VotingBlockedByObjectionsError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionLock, DecisionStatus
from app.models.integration import IntegrationEventType, IntegrationOutboxEvent
from app.models.objection import Objection
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.permissions.decision_lock import can_lock_decisions
from app.repositories.decision import DecisionRepository
from app.repositories.decision_lock import DecisionLockRepository
from app.repositories.objection import ObjectionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.decision_lock import (
    DecisionLockCreateRequest,
    DecisionLockVerificationResponse,
)
from app.schemas.voting import VotingResultResponse
from app.services.integration_delivery import IntegrationEventEmitter
from app.services.voting import VotingService


class DecisionLockService:
    def __init__(
        self,
        lock_repository: DecisionLockRepository,
        decision_repository: DecisionRepository,
        proposal_repository: ProposalRepository,
        objection_repository: ObjectionRepository,
        workspace_repository: WorkspaceRepository,
        voting_service: VotingService,
        integration_events: IntegrationEventEmitter | None = None,
    ) -> None:
        self._locks = lock_repository
        self._decisions = decision_repository
        self._proposals = proposal_repository
        self._objections = objection_repository
        self._workspaces = workspace_repository
        self._voting = voting_service
        self._integration_events = integration_events

    async def create(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: DecisionLockCreateRequest,
    ) -> DecisionLock:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        if not can_lock_decisions(membership.role):
            raise DecisionLockAccessDeniedError
        if decision.status is not DecisionStatus.ACTIVE:
            raise DecisionImmutableError
        if await self._locks.get_for_decision(decision_id) is not None:
            raise DecisionLockConflictError
        if await self._objections.has_open_blocking_for_decision(decision_id):
            raise VotingBlockedByObjectionsError

        result = await self._voting.get_result(
            current_user,
            workspace_id,
            decision_id,
            payload.voting_session_id,
        )
        if not result.result_valid or result.is_tie or result.winner_proposal_id is None:
            raise DecisionLockInvalidResultError

        winning_proposal = await self._proposals.get_for_decision(
            decision_id,
            result.winner_proposal_id,
        )
        if winning_proposal is None:
            raise ProposalNotFoundError
        if winning_proposal.status is not ProposalStatus.SUBMITTED:
            raise DecisionLockInvalidResultError

        snapshot = await self._build_snapshot(
            decision,
            winning_proposal,
            result,
        )
        locked_at = datetime.now(UTC)
        decision_lock = DecisionLock(
            id=uuid4(),
            decision_id=decision.id,
            voting_session_id=payload.voting_session_id,
            winning_proposal_id=winning_proposal.id,
            locked_by_id=current_user.id,
            snapshot_version=1,
            snapshot=snapshot,
            document_hash=self.hash_snapshot(snapshot),
            locked_at=locked_at,
        )
        outbox_event: IntegrationOutboxEvent | None = None
        if self._integration_events is not None:
            outbox_event = self._integration_events.stage(
                workspace_id=workspace_id,
                event_type=IntegrationEventType.DECISION_LOCKED,
                event_id=decision_lock.id,
                payload={
                    "workspace_id": str(workspace_id),
                    "decision_id": str(decision.id),
                    "decision_title": decision.title,
                    "decision_lock_id": str(decision_lock.id),
                    "winning_proposal_id": str(winning_proposal.id),
                    "winning_proposal_title": winning_proposal.title,
                    "actor_id": str(current_user.id),
                    "actor_name": current_user.display_name,
                    "locked_at": locked_at.isoformat(),
                },
            )
        created = await self._locks.create(
            decision_lock,
            decision,
            locked_at=locked_at,
        )
        if outbox_event is not None and self._integration_events is not None:
            self._integration_events.publish(outbox_event)
        return created

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> DecisionLock:
        await self._context(current_user.id, workspace_id, decision_id)
        decision_lock = await self._locks.get_for_decision(decision_id)
        if decision_lock is None:
            raise DecisionLockNotFoundError
        return decision_lock

    async def verify(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> DecisionLockVerificationResponse:
        decision_lock = await self.get(current_user, workspace_id, decision_id)
        computed_hash = self.hash_snapshot(decision_lock.snapshot)
        return DecisionLockVerificationResponse(
            decision_id=decision_id,
            document_hash=decision_lock.document_hash,
            computed_hash=computed_hash,
            valid=computed_hash == decision_lock.document_hash,
        )

    async def _build_snapshot(
        self,
        decision: Decision,
        winning_proposal: Proposal,
        result: VotingResultResponse,
    ) -> dict[str, object]:
        approved_objections = await self._objections.list_for_proposal(
            winning_proposal.id,
            severity=None,
            status=None,
        )
        alternatives: list[dict[str, object]] = []
        for tally in result.tallies:
            if tally.proposal_id == winning_proposal.id:
                continue
            proposal = await self._proposals.get_for_decision(
                decision.id,
                tally.proposal_id,
            )
            if proposal is None:
                raise ProposalNotFoundError
            objections = await self._objections.list_for_proposal(
                proposal.id,
                severity=None,
                status=None,
            )
            alternatives.append(
                {
                    "proposal": self._proposal_snapshot(proposal),
                    "votes": tally.votes,
                    "percentage": tally.percentage,
                    "objections": [self._objection_snapshot(objection) for objection in objections],
                }
            )

        return {
            "decision": {
                "id": str(decision.id),
                "workspace_id": str(decision.workspace_id),
                "created_by_id": str(decision.created_by_id),
                "title": decision.title,
                "summary": decision.summary,
                "category": decision.category.value,
                "due_at": self._datetime_value(decision.due_at),
                "review_at": self._datetime_value(decision.review_at),
            },
            "approved_proposal": self._proposal_snapshot(winning_proposal),
            "voting_result": result.model_dump(mode="json"),
            "dissent": {
                "objections_to_approved_proposal": [
                    self._objection_snapshot(objection) for objection in approved_objections
                ],
                "alternative_proposals": alternatives,
            },
        }

    async def _context(
        self,
        user_id: UUID,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> tuple[WorkspaceMember, Decision]:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError
        membership = await self._workspaces.get_membership(workspace_id, user_id)
        if membership is None:
            raise WorkspaceNotFoundError
        decision = await self._decisions.get_for_workspace(workspace_id, decision_id)
        if decision is None:
            raise DecisionNotFoundError
        return membership, decision

    @staticmethod
    def hash_snapshot(snapshot: dict[str, object]) -> str:
        canonical = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _proposal_snapshot(proposal: Proposal) -> dict[str, object]:
        return {
            "id": str(proposal.id),
            "decision_id": str(proposal.decision_id),
            "created_by_id": str(proposal.created_by_id),
            "title": proposal.title,
            "summary": proposal.summary,
            "content": proposal.content,
            "status": proposal.status.value,
            "submitted_at": DecisionLockService._datetime_value(proposal.submitted_at),
        }

    @staticmethod
    def _objection_snapshot(objection: Objection) -> dict[str, object]:
        return {
            "id": str(objection.id),
            "proposal_id": str(objection.proposal_id),
            "created_by_id": str(objection.created_by_id),
            "severity": objection.severity.value,
            "status": objection.status.value,
            "title": objection.title,
            "description": objection.description,
            "resolution_note": objection.resolution_note,
            "resolved_by_id": (
                str(objection.resolved_by_id) if objection.resolved_by_id is not None else None
            ),
            "resolved_at": DecisionLockService._datetime_value(objection.resolved_at),
        }

    @staticmethod
    def _datetime_value(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
