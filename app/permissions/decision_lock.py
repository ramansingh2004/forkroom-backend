from app.models.workspace import WorkspaceRole


def can_lock_decisions(role: WorkspaceRole) -> bool:
    return role in {
        WorkspaceRole.OWNER,
        WorkspaceRole.ADMIN,
    }
