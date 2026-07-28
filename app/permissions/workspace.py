from app.models.workspace import WorkspaceRole


def can_manage_workspace(role: WorkspaceRole) -> bool:
    return role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


def can_delete_workspace(role: WorkspaceRole) -> bool:
    return role is WorkspaceRole.OWNER


def can_change_member_role(
    actor_role: WorkspaceRole,
    target_role: WorkspaceRole,
) -> bool:
    return actor_role is WorkspaceRole.OWNER and target_role is not WorkspaceRole.OWNER


def can_remove_member(
    actor_role: WorkspaceRole,
    target_role: WorkspaceRole,
) -> bool:
    if target_role is WorkspaceRole.OWNER:
        return False
    if actor_role is WorkspaceRole.OWNER:
        return True
    return actor_role is WorkspaceRole.ADMIN and target_role in {
        WorkspaceRole.MEMBER,
        WorkspaceRole.VIEWER,
    }
