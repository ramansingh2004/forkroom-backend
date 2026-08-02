from app.integrations.pdf_export import DecisionPdfRenderer


def test_pdf_renderer_creates_a_pdf_from_locked_snapshot() -> None:
    snapshot: dict[str, object] = {
        "decision": {
            "title": "Choose the API framework",
            "summary": "Select a maintainable backend framework.",
            "category": "architecture",
            "review_at": "2026-11-01T00:00:00+00:00",
        },
        "approved_proposal": {
            "title": "Use FastAPI",
            "summary": "Typed async APIs and automatic OpenAPI.",
            "content": "Adopt FastAPI with SQLAlchemy and PostgreSQL.",
        },
        "voting_result": {
            "tallies": [
                {"proposal_id": "fastapi", "votes": 7, "percentage": 70.0},
                {"proposal_id": "django", "votes": 3, "percentage": 30.0},
            ]
        },
        "dissent": {
            "objections_to_approved_proposal": [
                {
                    "severity": "major",
                    "title": "Team familiarity",
                    "description": "Two engineers need onboarding.",
                    "resolution_note": "Schedule a workshop.",
                }
            ],
            "alternative_proposals": [],
        },
    }
    result = DecisionPdfRenderer().render(
        snapshot,
        document_hash="a" * 64,
        snapshot_version=1,
        locked_at="2026-08-01T12:00:00+00:00",
    )
    assert result.startswith(b"%PDF-")
    assert len(result) > 10_000
