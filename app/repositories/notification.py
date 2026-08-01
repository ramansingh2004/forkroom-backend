from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_review import (
    ActionStatus,
    DecisionReview,
    ImplementationAction,
    ReviewStatus,
)
from app.models.decision import Decision, DecisionStatus
from app.models.notification import Notification, NotificationKind, NotificationStatus
from app.models.user import User
from app.models.voting import VotingEligibleVoter, VotingSession, VotingSessionStatus
from app.models.workspace import WorkspaceMember, WorkspaceRole


@dataclass(frozen=True, slots=True)
class ReminderCandidate:
    recipient_id: UUID
    workspace_id: UUID
    kind: NotificationKind
    source_id: UUID
    due_at: datetime
    title: str
    body: str

    @property
    def idempotency_key(self) -> str:
        return f"{self.kind.value}:{self.source_id}:{self.recipient_id}:{self.due_at.isoformat()}"


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_candidate(
        self,
        candidate: ReminderCandidate,
        *,
        max_attempts: int,
        available_at: datetime,
    ) -> UUID | None:
        notification_id = uuid4()
        statement = (
            insert(Notification)
            .values(
                id=notification_id,
                recipient_id=candidate.recipient_id,
                workspace_id=candidate.workspace_id,
                kind=candidate.kind,
                source_id=candidate.source_id,
                idempotency_key=candidate.idempotency_key,
                title=candidate.title,
                body=candidate.body,
                status=NotificationStatus.PENDING,
                attempt_count=0,
                max_attempts=max_attempts,
                available_at=available_at,
            )
            .on_conflict_do_nothing(index_elements=[Notification.idempotency_key])
            .returning(Notification.id)
        )
        created_id = await self._session.scalar(statement)
        await self._session.commit()
        return created_id

    async def list_for_recipient(
        self,
        recipient_id: UUID,
        *,
        unread_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int, int]:
        filters = [Notification.recipient_id == recipient_id]
        if unread_only:
            filters.append(Notification.read_at.is_(None))
        statement = (
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list((await self._session.scalars(statement)).all())
        total = int(
            await self._session.scalar(select(func.count(Notification.id)).where(*filters)) or 0
        )
        unread = await self.unread_count(recipient_id)
        return items, total, unread

    async def get_for_recipient(
        self,
        notification_id: UUID,
        recipient_id: UUID,
    ) -> Notification | None:
        statement = select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == recipient_id,
        )
        return cast(Notification | None, await self._session.scalar(statement))

    async def mark_read(self, notification: Notification, at: datetime) -> Notification:
        if notification.read_at is None:
            notification.read_at = at
            await self._session.commit()
            await self._session.refresh(notification)
        return notification

    async def mark_all_read(self, recipient_id: UUID, at: datetime) -> int:
        result = cast(
            object,
            await self._session.execute(
                update(Notification)
                .where(
                    Notification.recipient_id == recipient_id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=at)
            ),
        )
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def unread_count(self, recipient_id: UUID) -> int:
        statement = select(func.count(Notification.id)).where(
            Notification.recipient_id == recipient_id,
            Notification.read_at.is_(None),
        )
        return int(await self._session.scalar(statement) or 0)

    async def claim_for_delivery(
        self,
        notification_id: UUID,
        now: datetime,
    ) -> Notification | None:
        statement = (
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.status.in_(
                    {
                        NotificationStatus.PENDING,
                        NotificationStatus.RETRY_SCHEDULED,
                    }
                ),
                Notification.available_at <= now,
                Notification.attempt_count < Notification.max_attempts,
            )
            .with_for_update(skip_locked=True)
        )
        notification = cast(Notification | None, await self._session.scalar(statement))
        if notification is None:
            return None
        notification.status = NotificationStatus.DELIVERING
        notification.attempt_count += 1
        notification.delivery_started_at = now
        notification.last_error = None
        await self._session.commit()
        await self._session.refresh(notification)
        return notification

    async def mark_delivered(self, notification: Notification, now: datetime) -> None:
        notification.status = NotificationStatus.DELIVERED
        notification.delivered_at = now
        notification.delivery_started_at = None
        notification.last_error = None
        await self._session.commit()

    async def schedule_retry(
        self,
        notification: Notification,
        *,
        available_at: datetime,
        error: str,
    ) -> None:
        notification.status = NotificationStatus.RETRY_SCHEDULED
        notification.available_at = available_at
        notification.delivery_started_at = None
        notification.last_error = error[:5000]
        await self._session.commit()

    async def mark_failed(
        self,
        notification: Notification,
        *,
        now: datetime,
        error: str,
    ) -> None:
        notification.status = NotificationStatus.FAILED
        notification.failed_at = now
        notification.delivery_started_at = None
        notification.last_error = error[:5000]
        await self._session.commit()

    async def recover_stale_deliveries(
        self,
        *,
        stale_before: datetime,
        available_at: datetime,
    ) -> list[UUID]:
        statement = (
            update(Notification)
            .where(
                Notification.status == NotificationStatus.DELIVERING,
                Notification.delivery_started_at < stale_before,
                Notification.attempt_count < Notification.max_attempts,
            )
            .values(
                status=NotificationStatus.RETRY_SCHEDULED,
                available_at=available_at,
                delivery_started_at=None,
                last_error="Delivery lease expired before completion",
            )
            .returning(Notification.id)
        )
        recovered = list((await self._session.scalars(statement)).all())
        await self._session.commit()
        return recovered

    async def get_recipient(self, recipient_id: UUID) -> User | None:
        return cast(User | None, await self._session.get(User, recipient_id))

    async def due_action_candidates(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> list[ReminderCandidate]:
        statement = (
            select(ImplementationAction, Decision.workspace_id)
            .join(Decision, Decision.id == ImplementationAction.decision_id)
            .where(
                ImplementationAction.status.in_(
                    {ActionStatus.TODO, ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED}
                ),
                ImplementationAction.due_at.is_not(None),
                ImplementationAction.due_at > after,
                ImplementationAction.due_at <= before,
            )
        )
        return [
            ReminderCandidate(
                recipient_id=action.assignee_id,
                workspace_id=workspace_id,
                kind=NotificationKind.ACTION_DUE,
                source_id=action.id,
                due_at=cast(datetime, action.due_at),
                title=f"Action due: {action.title}",
                body=f'Your implementation action "{action.title}" is due soon.',
            )
            for action, workspace_id in (await self._session.execute(statement)).all()
        ]

    async def due_review_candidates(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> list[ReminderCandidate]:
        statement = (
            select(DecisionReview, Decision.workspace_id, WorkspaceMember.user_id)
            .join(Decision, Decision.id == DecisionReview.decision_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Decision.workspace_id)
            .where(
                DecisionReview.status == ReviewStatus.SCHEDULED,
                DecisionReview.scheduled_for > after,
                DecisionReview.scheduled_for <= before,
                WorkspaceMember.role.in_({WorkspaceRole.OWNER, WorkspaceRole.ADMIN}),
            )
        )
        return [
            ReminderCandidate(
                recipient_id=user_id,
                workspace_id=workspace_id,
                kind=NotificationKind.DECISION_REVIEW,
                source_id=review.id,
                due_at=review.scheduled_for,
                title="Decision review due",
                body="A scheduled decision review is due soon.",
            )
            for review, workspace_id, user_id in (await self._session.execute(statement)).all()
        ]

    async def due_decision_candidates(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> list[ReminderCandidate]:
        statement = (
            select(Decision, WorkspaceMember.user_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Decision.workspace_id)
            .where(
                Decision.status == DecisionStatus.ACTIVE,
                Decision.due_at.is_not(None),
                Decision.due_at > after,
                Decision.due_at <= before,
                WorkspaceMember.role.in_(
                    {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER}
                ),
            )
        )
        return [
            ReminderCandidate(
                recipient_id=user_id,
                workspace_id=decision.workspace_id,
                kind=NotificationKind.DECISION_DEADLINE,
                source_id=decision.id,
                due_at=cast(datetime, decision.due_at),
                title=f"Decision deadline: {decision.title}",
                body=f'The decision "{decision.title}" is approaching its deadline.',
            )
            for decision, user_id in (await self._session.execute(statement)).all()
        ]

    async def due_voting_candidates(
        self,
        *,
        after: datetime,
        before: datetime,
    ) -> list[ReminderCandidate]:
        statement = (
            select(VotingSession, Decision, VotingEligibleVoter.user_id)
            .join(Decision, Decision.id == VotingSession.decision_id)
            .join(
                VotingEligibleVoter,
                VotingEligibleVoter.voting_session_id == VotingSession.id,
            )
            .where(
                VotingSession.status == VotingSessionStatus.OPEN,
                VotingSession.closes_at.is_not(None),
                VotingSession.closes_at > after,
                VotingSession.closes_at <= before,
            )
        )
        return [
            ReminderCandidate(
                recipient_id=user_id,
                workspace_id=decision.workspace_id,
                kind=NotificationKind.VOTING_CLOSE,
                source_id=session.id,
                due_at=cast(datetime, session.closes_at),
                title=f"Voting closes soon: {decision.title}",
                body=f'Voting for "{decision.title}" closes soon.',
            )
            for session, decision, user_id in (await self._session.execute(statement)).all()
        ]
