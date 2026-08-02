import base64
import hashlib
import hmac
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError
from app.core.security import (
    create_collaboration_token,
    create_meeting_token,
    create_turn_credentials,
    decode_meeting_token,
)


def test_meeting_token_round_trip_preserves_room_scope() -> None:
    user_id, workspace_id, decision_id = uuid4(), uuid4(), uuid4()
    signed = create_meeting_token(
        user_id=user_id,
        workspace_id=workspace_id,
        decision_id=decision_id,
        display_name="Raman Singh",
        role="admin",
        can_facilitate=True,
    )
    claims = decode_meeting_token(signed.token)
    assert claims.user_id == user_id
    assert claims.workspace_id == workspace_id
    assert claims.decision_id == decision_id
    assert claims.can_facilitate is True


def test_collaboration_token_is_rejected_by_meeting_decoder() -> None:
    token = create_collaboration_token(
        user_id=uuid4(),
        workspace_id=uuid4(),
        decision_id=uuid4(),
        proposal_id=uuid4(),
        document_name="proposal:test",
        permission="write",
        display_name="Raman Singh",
    )
    with pytest.raises(InvalidTokenError):
        decode_meeting_token(token.token)


def test_turn_credential_matches_coturn_rest_hmac() -> None:
    username, credential, expires_at = create_turn_credentials(uuid4())
    expected = base64.b64encode(
        hmac.new(
            get_settings().turn_shared_secret.encode(),
            username.encode(),
            hashlib.sha1,
        ).digest()
    ).decode()
    assert credential == expected
    assert username.startswith(f"{expires_at}:")
