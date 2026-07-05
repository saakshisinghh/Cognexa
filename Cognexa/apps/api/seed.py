"""
apps/api/seed.py

Startup data seeding.

Fixes the following reported issues:
  1. "Admin Login" — the frontend demo box advertises admin@indusmind.io /
     admin1234, but nothing ever created that user in the database. This
     module creates it automatically on API startup (idempotent — safe to
     run on every boot) instead of requiring a manual `docker exec` step.
  5. "Default Seed Data" — also seeds a couple of extra demo users (one per
     role, so RBAC is actually testable), a couple of sample assets, one
     sample document, and one demo conversation so the product doesn't look
     empty on first login.

Controlled by settings so it can be disabled in real production deployments:
  - SEED_DEFAULT_ADMIN   (default True)
  - SEED_DEMO_DATA       (default True)
  - DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD / DEFAULT_ADMIN_NAME
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.models import (
    User,
    UserRole,
    Asset,
    Document,
    DocumentStatus,
    Conversation,
    Message,
)

logger = logging.getLogger("indusmind.seed")


def _hash_password(password: str) -> str:
    # Local import to avoid a circular import with routers.auth at module
    # load time (routers.auth imports models, main imports both).
    from apps.api.routers.auth import hash_password
    return hash_password(password)


def seed_default_admin(db: Session) -> User:
    """
    Idempotently ensure the default admin account exists.

    Safe to call on every startup: if a user with DEFAULT_ADMIN_EMAIL
    already exists, nothing is changed (existing password is preserved so
    an operator who has since changed it doesn't get reset on redeploy).
    """
    email = settings.DEFAULT_ADMIN_EMAIL
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        # Make sure it's still an active admin even if it was edited.
        changed = False
        if existing.role != UserRole.admin:
            existing.role = UserRole.admin
            changed = True
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            db.commit()
            logger.info(f"Default admin '{email}' repaired (role/active flag).")
        return existing

    admin = User(
        email=email,
        full_name=settings.DEFAULT_ADMIN_NAME,
        hashed_password=_hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info(f"Seeded default admin user: {email}")
    return admin


def seed_demo_data(db: Session, admin: User) -> None:
    """
    Seed a small amount of representative data so a fresh environment isn't
    empty on first login. Every step is idempotent (checked by a stable
    lookup key) so this is safe to call on every startup.
    """
    # ── Extra role accounts (Engineer / Viewer) so RBAC can actually be
    #    tested — the checklist notes "Only Engineer tested" for roles. ──
    demo_users = [
        ("engineer@indusmind.io", "Demo Engineer", UserRole.engineer),
        ("viewer@indusmind.io", "Demo Viewer", UserRole.viewer),
    ]
    users_by_email = {admin.email: admin}
    for email, name, role in demo_users:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                full_name=name,
                hashed_password=_hash_password(settings.DEFAULT_DEMO_PASSWORD),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Seeded demo {role.value} user: {email}")
        users_by_email[email] = user

    # ── Sample assets ──
    sample_assets = [
        {
            "name": "Compressor Unit CMP-101",
            "description": "Primary air compressor, Plant Floor A.",
            "location": "Plant A / Bay 3",
            "asset_type": "Compressor",
            "health_status": "healthy",
            "tags": ["compressor", "plant-a"],
        },
        {
            "name": "Conveyor Line CV-07",
            "description": "Main packaging line conveyor.",
            "location": "Plant A / Packaging",
            "asset_type": "Conveyor",
            "health_status": "warning",
            "tags": ["conveyor", "packaging"],
        },
    ]
    created_assets = []
    for a in sample_assets:
        asset = db.query(Asset).filter(Asset.name == a["name"]).first()
        if not asset:
            asset = Asset(owner_id=admin.id, **a)
            db.add(asset)
            db.commit()
            db.refresh(asset)
            logger.info(f"Seeded sample asset: {asset.name}")
        created_assets.append(asset)

    # ── Sample document (metadata only — no real file upload / OCR run,
    #    just enough for the UI list & Asset 360 views to render). ──
    doc = db.query(Document).filter(Document.filename == "sample-maintenance-manual.pdf").first()
    if not doc:
        doc = Document(
            filename="sample-maintenance-manual.pdf",
            original_filename="Compressor Maintenance Manual.pdf",
            file_path="seed/sample-maintenance-manual.pdf",
            file_size=245_760,
            mime_type="application/pdf",
            status=DocumentStatus.completed,
            ocr_status="completed",
            embedding_status="completed",
            chunk_count=0,
            page_count=12,
            language="en",
            category="manual",
            tags=["seed", "manual"],
            extracted_text="This is placeholder seed content; upload a real document to replace it.",
            owner_id=admin.id,
            asset_id=created_assets[0].id if created_assets else None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        logger.info("Seeded sample document metadata row.")

    # ── Demo conversation so the Copilot sidebar isn't empty ──
    convo = db.query(Conversation).filter(
        Conversation.user_id == admin.id, Conversation.title == "Welcome to INDUS MIND"
    ).first()
    if not convo:
        convo = Conversation(title="Welcome to INDUS MIND", user_id=admin.id, document_id=doc.id)
        db.add(convo)
        db.commit()
        db.refresh(convo)
        db.add_all([
            Message(conversation_id=convo.id, role="user", content="What can INDUS MIND do?"),
            Message(
                conversation_id=convo.id,
                role="assistant",
                content=(
                    "I can answer questions about your uploaded documents with cited sources, "
                    "track your industrial assets, and help you investigate incidents. "
                    "Upload a document or ask me about the sample maintenance manual to get started."
                ),
                sources=[{"document_id": doc.id, "filename": doc.original_filename}],
                confidence=0.9,
                tokens_used=42,
            ),
        ])
        db.commit()
        logger.info("Seeded demo conversation.")


def run_startup_seed(db: Session) -> None:
    """Entry point called from main.py's lifespan handler."""
    if not settings.SEED_DEFAULT_ADMIN:
        logger.info("SEED_DEFAULT_ADMIN=false — skipping admin seed.")
        return
    admin = seed_default_admin(db)

    if settings.SEED_DEMO_DATA:
        seed_demo_data(db, admin)
    else:
        logger.info("SEED_DEMO_DATA=false — skipping demo data seed.")
