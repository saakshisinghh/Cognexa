"""
apps/api/tests/test_phase6_knowledge.py

Phase 6 unit tests — Temporal Knowledge Intelligence, Knowledge Gap
Detection, Knowledge Loss Prediction, Expert Disagreement Detection.

Follows the exact convention of tests/test_services.py and
tests/test_phase2_workers.py: pure-function unit tests requiring no
database, no Weaviate, no Celery worker — this repo has no conftest.py /
DB fixtures set up yet, so these test the pure scoring/clustering logic
directly (decay.py, gap.py, loss.py, disagreement.py are all designed as
DB-independent pure functions specifically so they're unit-testable this
way — see each module's docstring).

Router/Celery-task-level integration tests (actually hitting a test
database) would need a conftest.py with async DB fixtures added first —
that's a separate, larger addition this repo doesn't have for ANY
existing feature yet, so it's out of scope here rather than silently
assumed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.services import decay
from apps.api.services import gap
from apps.api.services import loss
from apps.api.services import disagreement


# ─── Temporal Knowledge Intelligence (services/decay.py) ──────────────────

class TestTrustDecay:
    def test_fresh_chunk_has_near_full_trust(self):
        now = datetime.now(timezone.utc)
        score = decay.compute_trust_score(valid_from=now, valid_to=None, category="procedure", now=now)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_none_valid_from_treated_as_fresh(self):
        # Pre-Phase-6 rows without a backfilled valid_from should not crash.
        score = decay.compute_trust_score(valid_from=None, valid_to=None, category="procedure")
        assert score == 1.0

    def test_score_decays_to_half_at_half_life(self):
        half_life = decay.HALF_LIFE_DAYS_BY_CATEGORY["incident"]
        now = datetime.now(timezone.utc)
        valid_from = now - timedelta(days=half_life)
        score = decay.compute_trust_score(valid_from=valid_from, valid_to=None, category="incident", now=now)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_score_never_drops_below_floor(self):
        now = datetime.now(timezone.utc)
        very_old = now - timedelta(days=100_000)
        score = decay.compute_trust_score(valid_from=very_old, valid_to=None, category="incident", now=now)
        assert score >= decay.MIN_TRUST_SCORE

    def test_superseded_chunk_capped_regardless_of_age(self):
        now = datetime.now(timezone.utc)
        # Freshly superseded (valid_to = now) should still be capped low —
        # age alone would otherwise give it a near-1.0 score.
        score = decay.compute_trust_score(valid_from=now, valid_to=now, category="procedure", now=now)
        assert score <= decay.SUPERSEDED_TRUST_CEILING

    def test_unknown_category_falls_back_to_default_half_life(self):
        now = datetime.now(timezone.utc)
        valid_from = now - timedelta(days=decay.DEFAULT_HALF_LIFE_DAYS)
        score = decay.compute_trust_score(valid_from=valid_from, valid_to=None, category="some_unmapped_category", now=now)
        assert score == pytest.approx(0.5, abs=0.01)


class TestStaleDocumentDetection:
    def test_no_chunks_never_stale(self):
        assert decay.is_document_stale([], threshold=0.4) is False

    def test_low_average_trust_is_stale(self):
        assert decay.is_document_stale([0.1, 0.2, 0.15], threshold=0.4) is True

    def test_high_average_trust_is_not_stale(self):
        assert decay.is_document_stale([0.9, 0.8, 0.95], threshold=0.4) is False


# ─── Knowledge Gap Detection (services/gap.py) ─────────────────────────────

class TestGapScoring:
    def test_all_categories_present_zero_gap(self):
        present = set(gap.EXPECTED_CATEGORY_WEIGHTS.keys())
        score, missing, expected, penalty = gap.compute_gap_score(present, incident_count=0)
        assert score == 0.0
        assert missing == []
        assert penalty is False

    def test_nothing_present_full_gap(self):
        score, missing, expected, penalty = gap.compute_gap_score(set(), incident_count=0)
        assert score == 1.0
        assert set(missing) == set(gap.EXPECTED_CATEGORY_WEIGHTS.keys())

    def test_incident_without_procedure_applies_penalty(self):
        present = {"compliance", "inspection", "specification"}  # no procedure/manual
        score_with_incidents, _, _, penalty = gap.compute_gap_score(present, incident_count=3)
        score_without_incidents, _, _, penalty_none = gap.compute_gap_score(present, incident_count=0)
        assert penalty is True
        assert penalty_none is False
        assert score_with_incidents > score_without_incidents

    def test_no_penalty_when_procedure_present_despite_incidents(self):
        present = set(gap.EXPECTED_CATEGORY_WEIGHTS.keys())  # includes procedure & manual
        score, missing, expected, penalty = gap.compute_gap_score(present, incident_count=5)
        assert penalty is False

    def test_gap_score_never_exceeds_one(self):
        score, _, _, _ = gap.compute_gap_score(set(), incident_count=100)
        assert score <= 1.0


# ─── Knowledge Loss Prediction (services/loss.py) ──────────────────────────

class TestOwnershipScoring:
    def test_single_contributor_gets_full_ownership(self):
        scores = loss.compute_ownership_scores({"u1": 5}, {})
        assert scores == {"u1": 1.0}

    def test_equal_contributors_split_evenly(self):
        scores = loss.compute_ownership_scores({"u1": 2, "u2": 2}, {})
        assert scores["u1"] == pytest.approx(0.5)
        assert scores["u2"] == pytest.approx(0.5)

    def test_no_activity_returns_empty(self):
        assert loss.compute_ownership_scores({}, {}) == {}

    def test_incidents_weighted_higher_than_documents(self):
        # u1: 1 incident only. u2: 1 document only. Incident weight > doc weight,
        # so u1's share should be larger despite equal raw counts.
        scores = loss.compute_ownership_scores({"u2": 1}, {"u1": 1})
        assert scores["u1"] > scores["u2"]


class TestRiskScoring:
    def test_single_contributor_adds_bus_factor_penalty(self):
        risk_one, _, _ = loss.compute_risk_score(concentration_score=0.5, contributor_count=1, primary_owner_is_retirement_risk=False)
        risk_two, _, _ = loss.compute_risk_score(concentration_score=0.5, contributor_count=2, primary_owner_is_retirement_risk=False)
        assert risk_one > risk_two

    def test_retirement_flag_boosts_risk(self):
        risk_no_flag, _, boost_no = loss.compute_risk_score(0.4, 3, primary_owner_is_retirement_risk=False)
        risk_flag, _, boost_yes = loss.compute_risk_score(0.4, 3, primary_owner_is_retirement_risk=True)
        assert boost_yes is True
        assert boost_no is False
        assert risk_flag > risk_no_flag
        assert risk_flag == pytest.approx(risk_no_flag + loss.RETIREMENT_FLAG_BOOST, abs=0.001)

    def test_risk_score_capped_at_one(self):
        risk, _, _ = loss.compute_risk_score(concentration_score=1.0, contributor_count=1, primary_owner_is_retirement_risk=True)
        assert risk <= 1.0

    @pytest.mark.parametrize("score,expected_level", [
        (0.9, "critical"),
        (0.6, "high"),
        (0.3, "medium"),
        (0.1, "low"),
    ])
    def test_risk_level_thresholds(self, score, expected_level):
        _, level, _ = loss.compute_risk_score(concentration_score=score, contributor_count=5, primary_owner_is_retirement_risk=False)
        assert level == expected_level


# ─── Expert Disagreement Detection (services/disagreement.py) ─────────────

class TestDisagreementClustering:
    def test_canonical_pair_is_order_independent(self):
        assert disagreement.canonical_document_pair("doc-a", "doc-b") == disagreement.canonical_document_pair("doc-b", "doc-a")

    def test_higher_severity_major_beats_minor(self):
        assert disagreement.higher_severity("major", "minor") == "major"
        assert disagreement.higher_severity("minor", "major") == "major"

    def test_higher_severity_equal_returns_same(self):
        assert disagreement.higher_severity("moderate", "moderate") == "moderate"

    def test_severity_rank_ordering(self):
        assert disagreement.SEVERITY_RANK["minor"] < disagreement.SEVERITY_RANK["moderate"] < disagreement.SEVERITY_RANK["major"]


# ─── Celery config sanity (matches test_phase2_workers.py's style) ────────

class TestPhase6CeleryConfig:
    def test_phase6_task_modules_registered(self):
        from apps.api.workers.celery_app import celery_app
        includes = celery_app.conf.include
        assert "apps.api.workers.temporal_tasks" in includes
        assert "apps.api.workers.gap_tasks" in includes
        assert "apps.api.workers.loss_tasks" in includes
        assert "apps.api.workers.disagreement_tasks" in includes

    def test_phase6_task_routes_configured(self):
        from apps.api.workers.celery_app import celery_app
        routes = celery_app.conf.task_routes
        assert routes["apps.api.workers.temporal_tasks.*"]["queue"] == "temporal"
        assert routes["apps.api.workers.gap_tasks.*"]["queue"] == "gap"
        assert routes["apps.api.workers.loss_tasks.*"]["queue"] == "loss"
        assert routes["apps.api.workers.disagreement_tasks.*"]["queue"] == "disagreement"

    def test_phase6_beat_schedule_entries_present(self):
        from apps.api.workers.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "temporal-recompute-trust-scores-nightly" in schedule
        assert "temporal-flag-stale-documents-nightly" in schedule
        assert "temporal-detect-superseded-chunks-nightly" in schedule
        assert "gap-compute-knowledge-gaps-nightly" in schedule
        assert "loss-compute-knowledge-loss-risk-nightly" in schedule
        assert "disagreement-detect-expert-disagreements-nightly" in schedule

    def test_phase6_schedule_ordering_respects_dependencies(self):
        """
        flag_stale_documents must run at/after recompute_trust_scores,
        and gap detection must run at/after stale-document flagging,
        since each reads the previous step's output.
        """
        from apps.api.workers.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule

        def minutes_since_midnight(entry):
            c = schedule[entry]["schedule"]
            return c.hour.pop() * 60 + c.minute.pop() if hasattr(c, "hour") else None

        trust_time = minutes_since_midnight("temporal-recompute-trust-scores-nightly")
        stale_time = minutes_since_midnight("temporal-flag-stale-documents-nightly")
        gap_time = minutes_since_midnight("gap-compute-knowledge-gaps-nightly")

        assert trust_time <= stale_time
        assert stale_time <= gap_time
