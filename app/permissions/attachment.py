from uuid import UUID

from app.models.workspace import WorkspaceRole


def can_upload_attachment(role: WorkspaceRole) -> bool:
    return role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER}


def can_delete_attachment(
    role: WorkspaceRole,
    *,
    uploaded_by_id: UUID,
    user_id: UUID,
) -> bool:
    return role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN} or uploaded_by_id == user_id
