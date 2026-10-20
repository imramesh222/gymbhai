"""What's new drafts (scripts/changelog_drafts.py): added unpublished, once."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform import ChangelogEntry
from scripts import changelog_drafts


def test_drafts_are_added_once_and_never_published(db: Session) -> None:
    db.add(ChangelogEntry(title="Classes, booked from the app", body="Mine"))
    db.flush()
    added = changelog_drafts.add_drafts(db)
    assert "Classes, booked from the app" not in added
    assert len(added) == len(changelog_drafts.DRAFTS) - 1
    assert changelog_drafts.add_drafts(db) == []
    rows = db.scalars(select(ChangelogEntry)).all()
    assert all(row.published_at is None for row in rows)
    assert {row.body for row in rows if row.title.startswith("Classes")} == {"Mine"}
    for title, body in changelog_drafts.DRAFTS:
        assert len(title) <= 120 and body
