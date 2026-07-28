from uuid import UUID

from app.models.objection import ObjectionStatus
from app.models.workspace import WorkspaceRole


def can_create_objections(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    }


def can_edit_objection(
    role: WorkspaceRole,
    *,
    objection_author_id: UUID,
    user_id: UUID,
) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    } or (role is WorkspaceRole.MEMBER and objection_author_id == user_id)


def can_transition_objection(
    role: WorkspaceRole,
    *,
    objection_author_id: UUID,
    user_id: UUID,
    target_status: ObjectionStatus,
) -> bool:
    if role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
        return True
    if role is not WorkspaceRole.MEMBER or objection_author_id != user_id:
        return False
    return target_status in {
        ObjectionStatus.OPEN,
        ObjectionStatus.RESOLVED,
    }
