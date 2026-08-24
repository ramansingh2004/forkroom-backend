"""SQLAlchemy models.

Import every model in ``import_all_models`` so Alembic can discover it.
"""


def import_all_models() -> None:
    """Import model modules before Alembic reads Base.metadata."""
    from app.models.action_review import (  # noqa: F401
        DecisionReview,
        DecisionRevision,
        ImplementationAction,
    )
    from app.models.attachment import Attachment  # noqa: F401
    from app.models.collaboration import CollaborationDocument  # noqa: F401
    from app.models.comment import Comment  # noqa: F401
    from app.models.decision import Decision, DecisionLock  # noqa: F401
    from app.models.export_search import (  # noqa: F401
        DecisionExport,
        DecisionSearchDocument,
    )
    from app.models.integration import (  # noqa: F401
        IntegrationConnection,
        IntegrationDelivery,
        IntegrationOutboxEvent,
        IntegrationSubscription,
        IntegrationWebhookEvent,
    )
    from app.models.mention import Mention  # noqa: F401
    from app.models.notification import Notification  # noqa: F401
    from app.models.objection import Objection, ObjectionStatusEvent  # noqa: F401
    from app.models.proposal import (  # noqa: F401
        DecisionCriterion,
        Proposal,
        ProposalScore,
    )
    from app.models.user import User  # noqa: F401
    from app.models.voting import (  # noqa: F401
        Vote,
        VotingEligibleVoter,
        VotingSession,
        VotingSessionProposal,
    )
    from app.models.workspace import Workspace, WorkspaceMember  # noqa: F401
