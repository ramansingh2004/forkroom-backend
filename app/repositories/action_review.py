from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ReviewConflictError
from app.models.action_review import (
    ActionStatus,
    DecisionReview,
    ImplementationAction,
    ReviewStatus,
)


class ActionReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_action(self, action: ImplementationAction) -> ImplementationAction:
        self._session.add(action)
        await self._session.commit()
        await self._session.refresh(action)
        return action

    async def list_actions(
        self,
        decision_id: UUID,
        *,
        status: ActionStatus | None,
        assignee_id: UUID | None,
    ) -> list[ImplementationAction]:
        statement = select(ImplementationAction).where(
            ImplementationAction.decision_id == decision_id
        )
        if status is not None:
            statement = statement.where(ImplementationAction.status == status)
        if assignee_id is not None:
            statement = statement.where(ImplementationAction.assignee_id == assignee_id)
        statement = statement.order_by(
            ImplementationAction.due_at.asc().nulls_last(),
            ImplementationAction.created_at.asc(),
        )
        return list((await self._session.scalars(statement)).all())

    async def get_action(
        self,
        decision_id: UUID,
        action_id: UUID,
    ) -> ImplementationAction | None:
        statement = select(ImplementationAction).where(
            ImplementationAction.id == action_id,
            ImplementationAction.decision_id == decision_id,
        )
        return cast(ImplementationAction | None, await self._session.scalar(statement))

    async def update_action(
        self,
        action: ImplementationAction,
        *,
        values: dict[str, object],
    ) -> ImplementationAction:
        for field, value in values.items():
            setattr(action, field, value)
        await self._session.commit()
        await self._session.refresh(action)
        return action

    async def transition_action(
        self,
        action: ImplementationAction,
        *,
        status: ActionStatus,
        completed_at: datetime | None,
        cancelled_at: datetime | None,
    ) -> ImplementationAction:
        action.status = status
        action.completed_at = completed_at
        action.cancelled_at = cancelled_at
        await self._session.commit()
        await self._session.refresh(action)
        return action

    async def create_review(self, review: DecisionReview) -> DecisionReview:
        self._session.add(review)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise ReviewConflictError from error
        await self._session.refresh(review)
        return review

    async def list_reviews(self, decision_id: UUID) -> list[DecisionReview]:
        statement = (
            select(DecisionReview)
            .where(DecisionReview.decision_id == decision_id)
            .order_by(DecisionReview.scheduled_for.desc())
        )
        return list((await self._session.scalars(statement)).all())

    async def get_review(
        self,
        decision_id: UUID,
        review_id: UUID,
    ) -> DecisionReview | None:
        statement = select(DecisionReview).where(
            DecisionReview.id == review_id,
            DecisionReview.decision_id == decision_id,
        )
        return cast(DecisionReview | None, await self._session.scalar(statement))

    async def update_review(
        self,
        review: DecisionReview,
        *,
        values: dict[str, object],
    ) -> DecisionReview:
        for field, value in values.items():
            setattr(review, field, value)
        await self._session.commit()
        await self._session.refresh(review)
        return review

    async def cancel_review(
        self,
        review: DecisionReview,
        *,
        cancelled_by_id: UUID,
        cancelled_at: datetime,
    ) -> DecisionReview:
        review.status = ReviewStatus.CANCELLED
        review.cancelled_by_id = cancelled_by_id
        review.cancelled_at = cancelled_at
        await self._session.commit()
        await self._session.refresh(review)
        return review
