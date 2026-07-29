class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an email owned by another account."""


class InvalidCredentialsError(Exception):
    """Raised when an email and password combination is invalid."""


class InactiveAccountError(Exception):
    """Raised when an inactive account attempts to authenticate."""


class InvalidTokenError(Exception):
    """Raised when an authentication token is invalid, expired, or reused."""


class EmailNotVerifiedError(Exception):
    """Raised when an account must verify its email before authentication."""


class InvalidActionTokenError(Exception):
    """Raised when an email verification or password reset token is invalid."""


class WorkspaceNotFoundError(Exception):
    """Raised when a workspace does not exist or is not visible to the user."""


class WorkspaceAccessDeniedError(Exception):
    """Raised when a workspace role cannot perform an operation."""


class WorkspaceMemberNotFoundError(Exception):
    """Raised when a requested workspace member or user does not exist."""


class WorkspaceMemberAlreadyExistsError(Exception):
    """Raised when a user already belongs to a workspace."""


class WorkspaceOwnerImmutableError(Exception):
    """Raised when an operation would remove or demote the workspace owner."""


class DecisionNotFoundError(Exception):
    """Raised when a decision does not exist in a visible workspace."""


class DecisionAccessDeniedError(Exception):
    """Raised when a workspace role cannot perform a decision operation."""


class DecisionInvalidTransitionError(Exception):
    """Raised when a decision status transition is not allowed."""


class DecisionImmutableError(Exception):
    """Raised when a closed or archived decision cannot be changed."""


class ProposalNotFoundError(Exception):
    """Raised when a proposal does not exist inside a visible decision."""


class ProposalAccessDeniedError(Exception):
    """Raised when a workspace role or proposal ownership forbids an operation."""


class ProposalImmutableError(Exception):
    """Raised when a proposal or its parent decision cannot be changed."""


class ProposalInvalidTransitionError(Exception):
    """Raised when a proposal status transition is not allowed."""


class CriterionNotFoundError(Exception):
    """Raised when a comparison criterion does not exist."""


class CriterionAccessDeniedError(Exception):
    """Raised when a role cannot manage comparison criteria."""


class CriterionConflictError(Exception):
    """Raised when criterion or proposal-score data is inconsistent."""


class ObjectionNotFoundError(Exception):
    """Raised when an objection does not exist inside a visible proposal."""


class ObjectionAccessDeniedError(Exception):
    """Raised when a role or objection ownership forbids an operation."""


class ObjectionImmutableError(Exception):
    """Raised when a resolved or dismissed objection cannot be edited."""


class ObjectionInvalidTransitionError(Exception):
    """Raised when an objection status transition is not allowed."""


class VotingSessionNotFoundError(Exception):
    """Raised when a voting session does not exist inside a visible decision."""


class VotingAccessDeniedError(Exception):
    """Raised when a role or eligibility snapshot forbids a voting action."""


class VotingConflictError(Exception):
    """Raised when another unfinished voting session already exists."""


class VotingBlockedByObjectionsError(Exception):
    """Raised when unresolved blocking objections prevent voting from opening."""


class VotingInvalidTransitionError(Exception):
    """Raised when a voting session status transition is not allowed."""


class VotingClosedError(Exception):
    """Raised when a ballot is submitted outside an open voting window."""


class VoteAlreadyCastError(Exception):
    """Raised when an eligible participant attempts to vote more than once."""


class VotingResultUnavailableError(Exception):
    """Raised when results are requested before a voting session is closed."""


class DecisionLockNotFoundError(Exception):
    """Raised when a decision has no immutable lock record."""


class DecisionLockAccessDeniedError(Exception):
    """Raised when a workspace role cannot lock a decision."""


class DecisionLockConflictError(Exception):
    """Raised when a decision or voting session has already been locked."""


class DecisionLockInvalidResultError(Exception):
    """Raised when a voting result is not eligible to lock a decision."""


class ActionNotFoundError(Exception):
    """Raised when an implementation action does not exist for a decision."""


class ActionAccessDeniedError(Exception):
    """Raised when a role or assignment forbids an action operation."""


class ActionInvalidTransitionError(Exception):
    """Raised when an implementation action status transition is invalid."""


class ActionAssigneeInvalidError(Exception):
    """Raised when an action assignee is not an eligible workspace member."""


class ReviewNotFoundError(Exception):
    """Raised when a scheduled decision review does not exist."""


class ReviewAccessDeniedError(Exception):
    """Raised when a workspace role cannot manage decision reviews."""


class ReviewConflictError(Exception):
    """Raised when a decision already has a scheduled review."""


class ReviewInvalidScheduleError(Exception):
    """Raised when a review date or review state is invalid."""
