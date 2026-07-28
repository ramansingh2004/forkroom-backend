from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import (
    CriterionAccessDeniedError,
    CriterionConflictError,
    CriterionNotFoundError,
    DecisionImmutableError,
    DecisionNotFoundError,
    ProposalAccessDeniedError,
    ProposalImmutableError,
    ProposalInvalidTransitionError,
    ProposalNotFoundError,
    WorkspaceNotFoundError,
)
from app.models.decision import Decision, DecisionStatus
from app.models.proposal import (
    DecisionCriterion,
    Proposal,
    ProposalScore,
    ProposalStatus,
)
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.permissions.proposal import (
    can_create_proposals,
    can_manage_criteria,
    can_manage_proposal,
    can_score_proposals,
)
from app.repositories.decision import DecisionRepository
from app.repositories.proposal import ProposalRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.proposal import (
    CriterionCreateRequest,
    CriterionReorderRequest,
    CriterionUpdateRequest,
    ProposalComparisonResponse,
    ProposalCreateRequest,
    ProposalResponse,
    ProposalScoreResponse,
    ProposalScoreUpsertRequest,
    ProposalTransitionRequest,
    ProposalUpdateRequest,
)

MUTABLE_DECISION_STATUSES = {
    DecisionStatus.DRAFT,
    DecisionStatus.ACTIVE,
}

PROPOSAL_TRANSITIONS: dict[ProposalStatus, set[ProposalStatus]] = {
    ProposalStatus.DRAFT: {
        ProposalStatus.SUBMITTED,
        ProposalStatus.WITHDRAWN,
    },
    ProposalStatus.SUBMITTED: {
        ProposalStatus.DRAFT,
        ProposalStatus.WITHDRAWN,
    },
    ProposalStatus.WITHDRAWN: set(),
}


class ProposalService:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        decision_repository: DecisionRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._proposals = proposal_repository
        self._decisions = decision_repository
        self._workspaces = workspace_repository

    async def create(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: ProposalCreateRequest,
    ) -> Proposal:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_create_proposals(membership.role):
            raise ProposalAccessDeniedError
        return await self._proposals.create(
            Proposal(
                decision_id=decision_id,
                created_by_id=current_user.id,
                title=payload.title,
                summary=payload.summary,
                content=payload.content,
                status=ProposalStatus.DRAFT,
            )
        )

    async def list_proposals(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        *,
        status: ProposalStatus | None,
    ) -> list[Proposal]:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._proposals.list_for_decision(decision_id, status=status)

    async def get(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._require_proposal(decision_id, proposal_id)

    async def update(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        payload: ProposalUpdateRequest,
    ) -> Proposal:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        proposal = await self._require_proposal(decision_id, proposal_id)
        if not can_manage_proposal(
            membership.role,
            proposal_author_id=proposal.created_by_id,
            user_id=current_user.id,
        ):
            raise ProposalAccessDeniedError
        if proposal.status is not ProposalStatus.DRAFT:
            raise ProposalImmutableError

        fields = payload.model_fields_set
        values: dict[str, object] = {}
        if "title" in fields and payload.title is not None:
            values["title"] = payload.title
        if "summary" in fields:
            values["summary"] = payload.summary
        if "content" in fields:
            values["content"] = payload.content
        return await self._proposals.update(proposal, values=values)

    async def transition(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        payload: ProposalTransitionRequest,
    ) -> Proposal:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        proposal = await self._require_proposal(decision_id, proposal_id)
        if not can_manage_proposal(
            membership.role,
            proposal_author_id=proposal.created_by_id,
            user_id=current_user.id,
        ):
            raise ProposalAccessDeniedError
        if payload.status not in PROPOSAL_TRANSITIONS[proposal.status]:
            raise ProposalInvalidTransitionError

        now = datetime.now(UTC)
        values: dict[str, object] = {
            "status": payload.status,
            "submitted_at": now if payload.status is ProposalStatus.SUBMITTED else None,
            "withdrawn_at": now if payload.status is ProposalStatus.WITHDRAWN else None,
        }
        return await self._proposals.update(proposal, values=values)

    async def delete(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> None:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        proposal = await self._require_proposal(decision_id, proposal_id)
        if not can_manage_proposal(
            membership.role,
            proposal_author_id=proposal.created_by_id,
            user_id=current_user.id,
        ):
            raise ProposalAccessDeniedError
        if proposal.status is not ProposalStatus.DRAFT:
            raise ProposalImmutableError
        await self._proposals.delete(proposal)

    async def create_criterion(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: CriterionCreateRequest,
    ) -> DecisionCriterion:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_manage_criteria(membership.role):
            raise CriterionAccessDeniedError
        position = await self._proposals.next_criterion_position(decision_id)
        return await self._proposals.create_criterion(
            DecisionCriterion(
                decision_id=decision_id,
                created_by_id=current_user.id,
                name=payload.name,
                description=payload.description,
                weight=payload.weight,
                position=position,
            )
        )

    async def list_criteria(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> list[DecisionCriterion]:
        await self._context(current_user.id, workspace_id, decision_id)
        return await self._proposals.list_criteria(decision_id)

    async def update_criterion(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        criterion_id: UUID,
        payload: CriterionUpdateRequest,
    ) -> DecisionCriterion:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_manage_criteria(membership.role):
            raise CriterionAccessDeniedError
        criterion = await self._require_criterion(decision_id, criterion_id)
        fields = payload.model_fields_set
        values: dict[str, object] = {}
        if "name" in fields and payload.name is not None:
            values["name"] = payload.name
        if "description" in fields:
            values["description"] = payload.description
        if "weight" in fields and payload.weight is not None:
            values["weight"] = payload.weight
        return await self._proposals.update_criterion(criterion, values=values)

    async def reorder_criteria(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        payload: CriterionReorderRequest,
    ) -> list[DecisionCriterion]:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_manage_criteria(membership.role):
            raise CriterionAccessDeniedError
        criteria = await self._proposals.list_criteria(decision_id)
        by_id = {criterion.id: criterion for criterion in criteria}
        if set(payload.criterion_ids) != set(by_id):
            raise CriterionConflictError
        ordered = [by_id[criterion_id] for criterion_id in payload.criterion_ids]
        return await self._proposals.reorder_criteria(ordered)

    async def delete_criterion(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        criterion_id: UUID,
    ) -> None:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_manage_criteria(membership.role):
            raise CriterionAccessDeniedError
        criterion = await self._require_criterion(decision_id, criterion_id)
        await self._proposals.delete_criterion(criterion)

    async def upsert_score(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
        proposal_id: UUID,
        criterion_id: UUID,
        payload: ProposalScoreUpsertRequest,
    ) -> ProposalScore:
        membership, decision = await self._context(
            current_user.id,
            workspace_id,
            decision_id,
        )
        self._require_mutable_decision(decision)
        if not can_score_proposals(membership.role):
            raise ProposalAccessDeniedError
        proposal = await self._require_proposal(decision_id, proposal_id)
        if proposal.status is not ProposalStatus.SUBMITTED:
            raise ProposalImmutableError
        await self._require_criterion(decision_id, criterion_id)
        score = await self._proposals.get_score(proposal_id, criterion_id)
        if score is None:
            score = ProposalScore(
                proposal_id=proposal_id,
                criterion_id=criterion_id,
                scored_by_id=current_user.id,
                score=payload.score,
                rationale=payload.rationale,
            )
        return await self._proposals.upsert_score(
            score,
            score_value=payload.score,
            rationale=payload.rationale,
            scored_by_id=current_user.id,
        )

    async def compare(
        self,
        current_user: User,
        workspace_id: UUID,
        decision_id: UUID,
    ) -> list[ProposalComparisonResponse]:
        await self._context(current_user.id, workspace_id, decision_id)
        proposals = await self._proposals.list_for_decision(
            decision_id,
            status=ProposalStatus.SUBMITTED,
        )
        criteria = await self._proposals.list_criteria(decision_id)
        scores = await self._proposals.list_scores_for_decision(decision_id)
        score_by_pair = {(score.proposal_id, score.criterion_id): score for score in scores}
        total_weight = sum(criterion.weight for criterion in criteria)
        result: list[ProposalComparisonResponse] = []
        for proposal in proposals:
            proposal_scores = [
                score_by_pair[(proposal.id, criterion.id)]
                for criterion in criteria
                if (proposal.id, criterion.id) in score_by_pair
            ]
            complete = bool(criteria) and len(proposal_scores) == len(criteria)
            weighted_score = None
            if complete and total_weight:
                weighted_sum = sum(
                    score_by_pair[(proposal.id, criterion.id)].score * criterion.weight
                    for criterion in criteria
                )
                weighted_score = round(weighted_sum / total_weight, 2)
            result.append(
                ProposalComparisonResponse(
                    proposal=ProposalResponse.model_validate(proposal),
                    scores=[
                        ProposalScoreResponse.model_validate(score) for score in proposal_scores
                    ],
                    weighted_score=weighted_score,
                )
            )
        return result

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
    def _require_mutable_decision(decision: Decision) -> None:
        if decision.status not in MUTABLE_DECISION_STATUSES:
            raise DecisionImmutableError

    async def _require_proposal(
        self,
        decision_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        proposal = await self._proposals.get_for_decision(decision_id, proposal_id)
        if proposal is None:
            raise ProposalNotFoundError
        return proposal

    async def _require_criterion(
        self,
        decision_id: UUID,
        criterion_id: UUID,
    ) -> DecisionCriterion:
        criterion = await self._proposals.get_criterion(decision_id, criterion_id)
        if criterion is None:
            raise CriterionNotFoundError
        return criterion
