from app.models.workspace import WorkspaceRole


def can_write_decisions(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.MEMBER,
    }


def can_delete_decisions(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    }
