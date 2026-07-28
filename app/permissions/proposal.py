from uuid import UUID

from app.models.workspace import WorkspaceRole


def can_create_proposals(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    }


def can_manage_proposal(
    role: WorkspaceRole,
    *,
    proposal_author_id: UUID,
    user_id: UUID,
) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    } or (role is WorkspaceRole.MEMBER and proposal_author_id == user_id)


def can_manage_criteria(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    }


def can_score_proposals(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    }
