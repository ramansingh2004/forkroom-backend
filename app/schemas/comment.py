from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CommentTextNode(BaseModel):
    type: Literal["text"]
    text: str = Field(max_length=50_000)


class CommentMentionNode(BaseModel):
    type: Literal["mention"]
    user_id: UUID
    label: str = Field(min_length=1, max_length=100)


CommentNode = Annotated[
    CommentTextNode | CommentMentionNode,
    Field(discriminator="type"),
]


class StructuredCommentBody(BaseModel):
    content: list[CommentNode] = Field(min_length=1, max_length=500)


class CommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=50_000)
    structured_body: StructuredCommentBody
    proposal_id: UUID | None = None
    objection_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Comment body cannot be empty")
        return normalized

    @model_validator(mode="after")
    def require_one_optional_context(self) -> "CommentCreateRequest":
        if self.proposal_id is not None and self.objection_id is not None:
            raise ValueError("A comment may reference a proposal or an objection, not both")
        return self


class CommentUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=50_000)
    structured_body: StructuredCommentBody

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Comment body cannot be empty")
        return normalized


class CommentAuthorResponse(BaseModel):
    id: UUID
    display_name: str
    avatar_url: str | None


class CommentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    decision_id: UUID
    proposal_id: UUID | None
    objection_id: UUID | None
    author: CommentAuthorResponse
    body: str
    structured_body: StructuredCommentBody
    created_at: datetime
    updated_at: datetime
