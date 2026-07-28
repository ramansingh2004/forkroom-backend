from app.models.workspace import WorkspaceRole


def can_manage_voting(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    }


def is_voting_role(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    }
