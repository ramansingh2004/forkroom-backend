from uuid import UUID

from app.models.workspace import WorkspaceRole


def can_manage_actions(role: WorkspaceRole) -> bool:
    return role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


def can_transition_action(
    role: WorkspaceRole,
    *,
    actor_id: UUID,
    assignee_id: UUID,
) -> bool:
    return can_manage_actions(role) or actor_id == assignee_id


def can_manage_reviews(role: WorkspaceRole) -> bool:
    return role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
