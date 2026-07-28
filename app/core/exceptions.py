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
