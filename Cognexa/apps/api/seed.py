"""
apps/api/seed.py

Startup data seeding.

Fixes the following reported issues:
  1. "Admin Login" — the frontend demo box advertises admin@indusmind.io /
     admin1234, but nothing ever created that user in the database. This
     module creates it automatically on API startup (idempotent — safe to
     run on every boot) instead of requiring a manual `docker exec` step.
  5. "Default Seed Data" — seeds a connected, realistic demo dataset (not
     just one lonely document) so every page in the product — Assets,
     Documents, Time Machine, Knowledge Dashboard (gaps / loss risk /
     disagreements / stale documents) — has something real to show on a
     fresh install, instead of looking broken-empty.

Controlled by settings so it can be disabled in real production deployments:
  - SEED_DEFAULT_ADMIN   (default True)
  - SEED_DEMO_DATA       (default True)
  - DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD / DEFAULT_ADMIN_NAME

Everything below is idempotent — every insert is guarded by a "does this
already exist" lookup — so this is safe to run on every container boot,
including against a database that already has this seed data from a
previous run.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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
from apps.api.models.incident import Incident, IncidentSeverity, IncidentStatus
from apps.api.models.knowledge_gap import AssetKnowledgeGap
from apps.api.models.knowledge_loss import AssetExpertiseOwnership, AssetKnowledgeLossRisk
from apps.api.models.expert_disagreement import AssetExpertDisagreement

logger = logging.getLogger("indusmind.seed")


def _now():
    return datetime.now(timezone.utc)


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


def _get_or_create_user(db: Session, email: str, name: str, role: UserRole,
                         is_retirement_risk: bool = False,
                         retirement_risk_notes: str | None = None) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            full_name=name,
            hashed_password=_hash_password(settings.DEFAULT_DEMO_PASSWORD),
            role=role,
            is_active=True,
            is_retirement_risk=is_retirement_risk,
            retirement_risk_notes=retirement_risk_notes,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Seeded demo {role.value} user: {email}")
    return user


def _get_or_create_asset(db: Session, admin: User, **fields) -> Asset:
    asset = db.query(Asset).filter(Asset.name == fields["name"]).first()
    if not asset:
        asset = Asset(owner_id=admin.id, **fields)
        db.add(asset)
        db.commit()
        db.refresh(asset)
        logger.info(f"Seeded sample asset: {asset.name}")
    return asset


def _get_or_create_document(db: Session, filename: str, **fields) -> Document:
    doc = db.query(Document).filter(Document.filename == filename).first()
    if not doc:
        doc = Document(filename=filename, **fields)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        logger.info(f"Seeded sample document: {doc.original_filename}")
    return doc


def seed_demo_data(db: Session, admin: User) -> None:
    """
    Seed a connected, realistic demo dataset so a fresh environment
    demonstrates every feature immediately instead of looking empty.
    """
    now = _now()

    # ────────────────────────────────────────────────────────────────────
    # Users (Engineer / Viewer, so RBAC is testable) — one of them is
    # flagged retirement-risk so the Knowledge Loss dashboard has a real
    # "high risk" row instead of an empty tab.
    # ────────────────────────────────────────────────────────────────────
    engineer = _get_or_create_user(
        db, "engineer@indusmind.io", "Demo Engineer", UserRole.engineer,
        is_retirement_risk=True,
        retirement_risk_notes="Planning to retire within 12 months — primary owner of Unit 3 rotating equipment history.",
    )
    _get_or_create_user(db, "viewer@indusmind.io", "Demo Viewer", UserRole.viewer)

    # ────────────────────────────────────────────────────────────────────
    # Assets — five, spanning two plant areas, so search/filter has
    # something to actually filter.
    # ────────────────────────────────────────────────────────────────────
    pump_1045 = _get_or_create_asset(
        db, admin,
        name="Pump P-1045",
        description="Centrifugal transfer pump, reactor feed service, Unit 3.",
        location="Riverside Plant / Unit 3",
        asset_type="Pump",
        health_status="warning",
        tags=["pump", "unit-3", "reactor-feed"],
    )
    pump_1046 = _get_or_create_asset(
        db, admin,
        name="Pump P-1046 (Standby)",
        description="Standby centrifugal transfer pump, reactor feed service, Unit 3.",
        location="Riverside Plant / Unit 3",
        asset_type="Pump",
        health_status="healthy",
        tags=["pump", "unit-3", "reactor-feed", "standby"],
    )
    reactor = _get_or_create_asset(
        db, admin,
        name="Reactor R-220",
        description="Primary reactor vessel, Unit 3.",
        location="Riverside Plant / Unit 3",
        asset_type="Reactor",
        health_status="healthy",
        tags=["reactor", "unit-3"],
    )
    compressor = _get_or_create_asset(
        db, admin,
        name="Compressor Unit CMP-101",
        description="Primary air compressor, Plant Floor A.",
        location="Plant A / Bay 3",
        asset_type="Compressor",
        health_status="healthy",
        tags=["compressor", "plant-a"],
    )
    conveyor = _get_or_create_asset(
        db, admin,
        name="Conveyor Line CV-07",
        description="Main packaging line conveyor.",
        location="Plant A / Packaging",
        asset_type="Conveyor",
        health_status="warning",
        tags=["conveyor", "packaging"],
    )
    created_assets = [pump_1045, pump_1046, reactor, compressor, conveyor]

    # ────────────────────────────────────────────────────────────────────
    # Documents — five, with real body text (so Search/Copilot have
    # something to actually retrieve), spread across owners, and one
    # explicitly flagged stale so the "Stale Documents" tab isn't empty.
    # NOTE: chunk_count is left at 0 here — these rows only carry
    # extracted_text as placeholder metadata, they were never actually run
    # through the OCR->chunk->embed pipeline, so they will NOT be
    # retrievable by Copilot/Search. Use "Reprocess" from the Documents
    # page (now that the metadata/extra_metadata bug is fixed) if you want
    # these specific rows to become real, searchable chunks — or just
    # upload your own documents, which is the more realistic demo path.
    # ────────────────────────────────────────────────────────────────────
    incident_report_doc = _get_or_create_document(
        db, "seed-incident-report-p1045.txt",
        original_filename="Incident Report - Pump P-1045.txt",
        file_path="seed/incident-report-p1045.txt",
        file_size=3200, mime_type="text/plain",
        status=DocumentStatus.completed, ocr_status="completed", embedding_status="completed",
        chunk_count=0, page_count=1, language="en", category="incident_report",
        tags=["seed", "incident", "pump"],
        extracted_text=(
            "Pump P-1045 tripped on high vibration at 02:14. Root cause investigation found "
            "the coupling guard had two of four bolts missing and the last laser alignment "
            "check was 11 months overdue against the 6-month PM interval."
        ),
        owner_id=admin.id, asset_id=pump_1045.id,
    )
    maintenance_manual_doc = _get_or_create_document(
        db, "seed-maintenance-manual-cp1000.txt",
        original_filename="Maintenance Manual - CP-1000 Pump Series.txt",
        file_path="seed/maintenance-manual-cp1000.txt",
        file_size=3300, mime_type="text/plain",
        status=DocumentStatus.completed, ocr_status="completed", embedding_status="completed",
        chunk_count=0, page_count=1, language="en", category="manual",
        tags=["seed", "manual", "pump"],
        extracted_text=(
            "Perform a laser shaft alignment check every 6 months on all CP-1000 series pumps. "
            "Torque-check coupling guard fasteners to 18 N·m at the same interval."
        ),
        owner_id=engineer.id, asset_id=pump_1045.id,
    )
    compliance_doc = _get_or_create_document(
        db, "seed-compliance-standard-saf014.txt",
        original_filename="Safety Compliance Standard RPS-SAF-014.txt",
        file_path="seed/compliance-standard-saf014.txt",
        file_size=3500, mime_type="text/plain",
        status=DocumentStatus.completed, ocr_status="completed", embedding_status="completed",
        chunk_count=0, page_count=1, language="en", category="compliance",
        tags=["seed", "compliance", "safety"],
        extracted_text=(
            "Any coupling guard work order that goes more than 30 days without a documented "
            "alignment verification is a Category B compliance violation requiring engineering sign-off."
        ),
        owner_id=admin.id, asset_id=pump_1045.id,
    )
    lessons_doc = _get_or_create_document(
        db, "seed-lessons-learned-coupling.txt",
        original_filename="Lessons Learned - Coupling Failures.txt",
        file_path="seed/lessons-learned-coupling.txt",
        file_size=3800, mime_type="text/plain",
        status=DocumentStatus.completed, ocr_status="completed", embedding_status="completed",
        chunk_count=0, page_count=1, language="en", category="lessons_learned",
        tags=["seed", "lessons-learned"],
        extracted_text=(
            "Three prior coupling failures across the CP-1000 fleet all trace back to the same "
            "systemic gap: alignment verification after guard removal is not system-enforced."
        ),
        owner_id=engineer.id, asset_id=pump_1045.id,
    )
    # Deliberately stale: an old conveyor manual nobody has touched in a
    # long time — the Stale Documents tab needs at least one real row.
    stale_manual_doc = _get_or_create_document(
        db, "seed-conveyor-manual-cv07.txt",
        original_filename="Conveyor CV-07 Operating Manual (2023 edition).txt",
        file_path="seed/conveyor-manual-cv07.txt",
        file_size=2100, mime_type="text/plain",
        status=DocumentStatus.completed, ocr_status="completed", embedding_status="completed",
        chunk_count=0, page_count=1, language="en", category="manual",
        tags=["seed", "manual", "conveyor"],
        extracted_text="Legacy operating manual for the CV-07 packaging conveyor, 2023 edition.",
        owner_id=admin.id, asset_id=conveyor.id,
        is_stale=True,
        stale_flagged_at=now - timedelta(days=14),
        stale_reason="No revision or re-verification recorded in over 18 months; average chunk trust score has decayed below threshold.",
    )
    all_docs = [incident_report_doc, maintenance_manual_doc, compliance_doc, lessons_doc, stale_manual_doc]

    # ────────────────────────────────────────────────────────────────────
    # Incidents — drives the Time Machine timeline for Pump P-1045.
    # ────────────────────────────────────────────────────────────────────
    if not db.query(Incident).filter(Incident.title.like("%P-1045%unplanned shutdown%")).first():
        db.add(Incident(
            title="Pump P-1045 unplanned shutdown — high vibration trip",
            description=(
                "Pump tripped on high-vibration interlock at 02:14. Coupling guard found with "
                "2 of 4 bolts missing; last laser alignment check was 11 months overdue. "
                "Coupling replaced and guard re-torqued to spec; alignment re-verified within tolerance."
            ),
            asset_id=pump_1045.id,
            document_id=incident_report_doc.id,
            reported_by=admin.id,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.RESOLVED,
            failure_mode_code="MISALIGN-01",
            occurred_at=now - timedelta(days=63),
        ))
        logger.info("Seeded sample incident: Pump P-1045 unplanned shutdown")

    if not db.query(Incident).filter(Incident.title.like("%CV-07%jam%")).first():
        db.add(Incident(
            title="Conveyor CV-07 belt jam",
            description="Packaging line conveyor jammed on a foreign object; cleared within 20 minutes, no injuries.",
            asset_id=conveyor.id,
            reported_by=engineer.id,
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.CLOSED,
            occurred_at=now - timedelta(days=200),
        ))
        logger.info("Seeded sample incident: Conveyor CV-07 belt jam")
    db.commit()

    # ────────────────────────────────────────────────────────────────────
    # Knowledge Gaps (Knowledge Dashboard → "Documentation Gaps" tab)
    # ────────────────────────────────────────────────────────────────────
    gap_rows = [
        (reactor, 0.72, ["safety_procedure", "commissioning_record"], ["manual"], 0),
        (pump_1046, 0.55, ["maintenance_schedule"], ["manual"], 0),
        (compressor, 0.35, [], ["manual"], 0),
    ]
    for asset, score, missing, present, incident_count in gap_rows:
        if not db.query(AssetKnowledgeGap).filter(AssetKnowledgeGap.asset_id == asset.id).first():
            db.add(AssetKnowledgeGap(
                asset_id=asset.id,
                gap_score=score,
                missing_categories=missing,
                present_categories=present,
                expected_categories=list(set(missing + present)),
                incident_count=incident_count,
                incident_penalty_applied=0,
                computed_at=now,
            ))
            logger.info(f"Seeded knowledge gap row for {asset.name} (score={score})")
    db.commit()

    # ────────────────────────────────────────────────────────────────────
    # Knowledge Loss Risk (Knowledge Dashboard → "Knowledge Loss Risk" tab)
    # Story: the demo Engineer (flagged retirement-risk above) is the sole
    # real contributor of Pump P-1045's documentation — a textbook
    # "bus factor of 1" high-risk row.
    # ────────────────────────────────────────────────────────────────────
    if not db.query(AssetExpertiseOwnership).filter(
        AssetExpertiseOwnership.asset_id == pump_1045.id, AssetExpertiseOwnership.user_id == engineer.id
    ).first():
        db.add(AssetExpertiseOwnership(
            asset_id=pump_1045.id, user_id=engineer.id,
            document_count=2, incident_count=0, ownership_score=0.85,
            is_primary_owner=True, last_activity_at=now - timedelta(days=5),
            computed_at=now,
        ))
    if not db.query(AssetExpertiseOwnership).filter(
        AssetExpertiseOwnership.asset_id == pump_1045.id, AssetExpertiseOwnership.user_id == admin.id
    ).first():
        db.add(AssetExpertiseOwnership(
            asset_id=pump_1045.id, user_id=admin.id,
            document_count=2, incident_count=1, ownership_score=0.15,
            is_primary_owner=False, last_activity_at=now - timedelta(days=63),
            computed_at=now,
        ))
    db.commit()

    if not db.query(AssetKnowledgeLossRisk).filter(AssetKnowledgeLossRisk.asset_id == pump_1045.id).first():
        db.add(AssetKnowledgeLossRisk(
            asset_id=pump_1045.id,
            primary_owner_user_id=engineer.id,
            concentration_score=0.85,
            contributor_count=2,
            retirement_boost_applied=True,
            risk_score=0.81,
            risk_level="high",
            mitigation_recommendation=(
                "Primary owner is flagged as a retirement risk within 12 months and holds 85% of "
                "this asset's documented knowledge. Recommend cross-training a second engineer and "
                "running a Shadow Engineer capture session before transition."
            ),
            computed_at=now,
        ))
        logger.info("Seeded knowledge loss risk row for Pump P-1045 (high risk)")

    if not db.query(AssetKnowledgeLossRisk).filter(AssetKnowledgeLossRisk.asset_id == conveyor.id).first():
        db.add(AssetKnowledgeLossRisk(
            asset_id=conveyor.id,
            primary_owner_user_id=admin.id,
            concentration_score=0.4,
            contributor_count=3,
            retirement_boost_applied=False,
            risk_score=0.22,
            risk_level="low",
            mitigation_recommendation=None,
            computed_at=now,
        ))
        logger.info("Seeded knowledge loss risk row for Conveyor CV-07 (low risk)")
    db.commit()

    # ────────────────────────────────────────────────────────────────────
    # Expert Disagreement (Knowledge Dashboard → "Expert Disagreements")
    # Story: the maintenance manual's 6-month alignment interval vs the
    # compliance standard's 30-day escalation trigger reads as
    # contradictory guidance if you don't have both documents open at
    # once — exactly the kind of thing this feature exists to surface.
    # ────────────────────────────────────────────────────────────────────
    doc_a_id, doc_b_id = sorted([maintenance_manual_doc.id, compliance_doc.id])
    doc_a_title = maintenance_manual_doc.original_filename if doc_a_id == maintenance_manual_doc.id else compliance_doc.original_filename
    doc_b_title = compliance_doc.original_filename if doc_b_id == compliance_doc.id else maintenance_manual_doc.original_filename

    if not db.query(AssetExpertDisagreement).filter(
        AssetExpertDisagreement.asset_id == pump_1045.id,
        AssetExpertDisagreement.document_a_id == doc_a_id,
        AssetExpertDisagreement.document_b_id == doc_b_id,
        AssetExpertDisagreement.topic == "alignment_check_interval",
    ).first():
        db.add(AssetExpertDisagreement(
            asset_id=pump_1045.id,
            topic="alignment_check_interval",
            document_a_id=doc_a_id, document_a_title=doc_a_title,
            document_b_id=doc_b_id, document_b_title=doc_b_title,
            occurrence_count=4,
            max_severity="moderate",
            sample_excerpt_a="Perform a laser shaft alignment check every 6 months on all CP-1000 series pumps.",
            sample_excerpt_b="Any coupling guard work order that goes more than 30 days without a documented alignment verification is a compliance violation.",
            last_seen_at=now - timedelta(days=2),
            is_resolved=False,
            computed_at=now,
        ))
        logger.info("Seeded expert disagreement: alignment_check_interval on Pump P-1045")
    db.commit()

    # ────────────────────────────────────────────────────────────────────
    # Demo conversation so the Copilot sidebar isn't empty
    # ────────────────────────────────────────────────────────────────────
    convo = db.query(Conversation).filter(
        Conversation.user_id == admin.id, Conversation.title == "Welcome to INDUS MIND"
    ).first()
    if not convo:
        convo = Conversation(title="Welcome to INDUS MIND", user_id=admin.id, document_id=incident_report_doc.id)
        db.add(convo)
        db.commit()
        db.refresh(convo)
        db.add_all([
            Message(conversation_id=convo.id, role="user", content="What caused the Pump P-1045 failure?"),
            Message(
                conversation_id=convo.id,
                role="assistant",
                content=(
                    "Pump P-1045 tripped on high vibration after a shaft misalignment that developed "
                    "when the required 6-month laser alignment check ran nearly a year overdue. "
                    "Ask me follow-up questions, or upload your own documents to replace this seed data."
                ),
                sources=[{"document_id": incident_report_doc.id, "filename": incident_report_doc.original_filename}],
                confidence=0.9,
                tokens_used=42,
            ),
        ])
        db.commit()
        logger.info("Seeded demo conversation.")

    logger.info(
        f"Demo data seed complete: {len(created_assets)} assets, {len(all_docs)} documents, "
        f"2 incidents, {len(gap_rows)} knowledge-gap rows, 2 loss-risk rows, 1 disagreement."
    )


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