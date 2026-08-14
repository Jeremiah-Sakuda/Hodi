import unittest
from datetime import datetime, timezone, timedelta
from src.schema.scope import Scope
from src.schema.grant_event import GrantEvent
from src.resolve.evaluator import permits

class TestScopeContainmentTruthTable(unittest.TestCase):
    """
    Scope Containment Truth Table Test Suite (HOD-104, HOD-106).
    Evaluates >=40 cases across all 5 dimensions simultaneously + union semantics.
    """

    def setUp(self):
        self.now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        self.past = self.now - timedelta(days=30)
        self.future = self.now + timedelta(days=30)
        self.expired = self.now - timedelta(days=1)

    def _make_grant(self, grant_id, use_type, commercial=False, territory=None, model_class="all_models", attribution_required=False, valid_from=None, valid_until=None):
        return GrantEvent(
            event_id=f"evt-{grant_id}",
            grant_id=grant_id,
            work_id="work-01",
            counterparty_id="buyer-01",
            scope=Scope(
                use_type=use_type,
                model_class=model_class,
                commercial=commercial,
                attribution_required=attribution_required,
                territory=territory or ["WW"],
                valid_from=valid_from or self.past,
                valid_until=valid_until
            ),
            kind="granted",
            issued_at=valid_from or self.past,
            signature="sig"
        )

    def _make_request(self, use_type, commercial=False, territory=None, model_class="all_models",
                      attribution_required=False, valid_from=None, valid_until=None):
        # Default request window: from now, open-ended. Under HOD-702 an
        # open-ended request is contained only by an UNBOUNDED grant — cases
        # pairing a bounded grant with an expected permit must request a
        # window inside the grant's.
        return Scope(
            use_type=use_type,
            model_class=model_class,
            commercial=commercial,
            attribution_required=attribution_required,
            territory=territory or ["WW"],
            valid_from=valid_from or self.now,
            valid_until=valid_until
        )

    # --- CORRECTION 1: UNION SEMANTICS & NO PER-DIMENSION MERGING (Cases 1-3) ---
    def test_case_01_naive_merge_prevention_returns_false(self):
        """Correction 1: Grant A (fine_tuning, non-commercial, US) + Grant B (human_reference, commercial, EU) -> commercial fine_tuning in EU MUST return False."""
        grant_a = self._make_grant("g-a", "fine_tuning", commercial=False, territory=["US"])
        grant_b = self._make_grant("g-b", "human_reference", commercial=True, territory=["EU"])
        req = self._make_request("fine_tuning", commercial=True, territory=["EU"])
        
        res = permits([grant_a, grant_b], req, at=self.now)
        self.assertFalse(res.permitted, "Must NOT permit per-dimension merging across grants!")

    def test_case_02_single_grant_covering_all_dimensions_returns_true(self):
        """Correction 1: Single Grant C genuinely covering commercial fine_tuning in EU returns True."""
        grant_c = self._make_grant("g-c", "fine_tuning", commercial=True, territory=["EU"])
        req = self._make_request("fine_tuning", commercial=True, territory=["EU"])
        
        res = permits([grant_c], req, at=self.now)
        self.assertTrue(res.permitted)
        self.assertEqual(res.matching_grant_id, "g-c")

    def test_case_03_neither_grant_alone_covers_request_returns_false(self):
        """Correction 1 Regression Test: Request covered by neither grant alone returns False."""
        grant_a = self._make_grant("g-a", "fine_tuning", commercial=True, territory=["US"])
        grant_b = self._make_grant("g-b", "fine_tuning", commercial=False, territory=["EU"])
        req = self._make_request("fine_tuning", commercial=True, territory=["EU"])
        
        res = permits([grant_a, grant_b], req, at=self.now)
        self.assertFalse(res.permitted)

    # --- CORRECTION 2: ATTRIBUTION IS A CONDITION, NOT A GATE (Case 4) ---
    def test_case_04_attribution_condition_does_not_block_permission(self):
        """Correction 2: attribution_required=True on grant permits request without asking, returning obligation condition."""
        grant = self._make_grant("g-attr", "training", commercial=True, attribution_required=True)
        req = self._make_request("training", commercial=True, attribution_required=False)
        
        res = permits([grant], req, at=self.now)
        self.assertTrue(res.permitted, "Attribution is a condition, not a permission gate!")
        self.assertTrue(res.attribution_required, "Obligation condition must ride along on evaluation result!")

    # --- CORRECTION 3: HIERARCHY & CONTAINMENT (Cases 5-10) ---
    def test_case_05_training_grant_permits_fine_tuning(self):
        g = self._make_grant("g1", "training")
        r = self._make_request("fine_tuning")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_06_training_grant_permits_rag_retrieval(self):
        g = self._make_grant("g1", "training")
        r = self._make_request("rag_retrieval")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_07_training_grant_permits_human_reference(self):
        """Correction 3 Mirror Case: training grant answers 'may I use as human reference' -> True."""
        g = self._make_grant("g1", "training")
        r = self._make_request("human_reference")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_08_fine_tuning_grant_permits_human_reference(self):
        g = self._make_grant("g1", "fine_tuning")
        r = self._make_request("human_reference")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_09_rag_retrieval_grant_permits_human_reference(self):
        g = self._make_grant("g1", "rag_retrieval")
        r = self._make_request("human_reference")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_10_human_reference_grant_denies_training(self):
        """PRD Case: human_reference grant answers 'may I train' -> False."""
        g = self._make_grant("g1", "human_reference")
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_11_fine_tuning_grant_denies_training(self):
        g = self._make_grant("g1", "fine_tuning")
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_12_synthesis_incomparable_to_training(self):
        g = self._make_grant("g1", "synthesis")
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_13_training_denies_synthesis(self):
        g = self._make_grant("g1", "training")
        r = self._make_request("synthesis")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_14_synthesis_permits_synthesis(self):
        g = self._make_grant("g1", "synthesis")
        r = self._make_request("synthesis")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    # --- COMMERCIAL STATUS DIMENSION (Cases 15-18) ---
    def test_case_15_commercial_grant_permits_non_commercial_request(self):
        """PRD Case: Commercial-permitted grant answers non-commercial request -> True (one-way)."""
        g = self._make_grant("g1", "training", commercial=True)
        r = self._make_request("training", commercial=False)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_16_non_commercial_grant_denies_commercial_request(self):
        g = self._make_grant("g1", "training", commercial=False)
        r = self._make_request("training", commercial=True)
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_17_commercial_grant_permits_commercial_request(self):
        g = self._make_grant("g1", "training", commercial=True)
        r = self._make_request("training", commercial=True)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_18_non_commercial_grant_permits_non_commercial_request(self):
        g = self._make_grant("g1", "training", commercial=False)
        r = self._make_request("training", commercial=False)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    # --- TERRITORY DIMENSION (Cases 19-24) ---
    def test_case_19_ww_grant_permits_us_request(self):
        g = self._make_grant("g1", "training", territory=["WW"])
        r = self._make_request("training", territory=["US"])
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_20_ww_grant_permits_eu_request(self):
        g = self._make_grant("g1", "training", territory=["WW"])
        r = self._make_request("training", territory=["EU"])
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_21_us_grant_denies_eu_request(self):
        """PRD Case: territory-limited grant answers out-of-territory request -> False."""
        g = self._make_grant("g1", "training", territory=["US"])
        r = self._make_request("training", territory=["EU"])
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_22_us_eu_grant_permits_us_request(self):
        g = self._make_grant("g1", "training", territory=["US", "EU"])
        r = self._make_request("training", territory=["US"])
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_23_us_grant_denies_us_jp_request(self):
        g = self._make_grant("g1", "training", territory=["US"])
        r = self._make_request("training", territory=["US", "JP"])
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_24_us_jp_grant_permits_us_jp_request(self):
        g = self._make_grant("g1", "training", territory=["US", "JP"])
        r = self._make_request("training", territory=["US", "JP"])
        self.assertTrue(permits([g], r, at=self.now).permitted)

    # --- MODEL CLASS DIMENSION (Cases 25-29) ---
    def test_case_25_all_models_grant_permits_open_weights(self):
        g = self._make_grant("g1", "training", model_class="all_models")
        r = self._make_request("training", model_class="open_weights")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_26_all_models_grant_permits_proprietary(self):
        g = self._make_grant("g1", "training", model_class="all_models")
        r = self._make_request("training", model_class="proprietary_frontier")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_27_open_weights_grant_denies_proprietary(self):
        g = self._make_grant("g1", "training", model_class="open_weights")
        r = self._make_request("training", model_class="proprietary_frontier")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_28_proprietary_grant_denies_open_weights(self):
        g = self._make_grant("g1", "training", model_class="proprietary_frontier")
        r = self._make_request("training", model_class="open_weights")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_29_open_weights_grant_permits_open_weights(self):
        g = self._make_grant("g1", "training", model_class="open_weights")
        r = self._make_request("training", model_class="open_weights")
        self.assertTrue(permits([g], r, at=self.now).permitted)

    # --- TEMPORAL VALIDITY DIMENSION (Cases 30-34) ---
    def test_case_30_active_grant_permits_valid_time(self):
        # The request's own window sits inside the grant's (HOD-702) — an
        # open-ended request against this bounded grant is case 50's DENY.
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training", valid_until=self.future)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_31_expired_grant_denies_request(self):
        """PRD Case: expired grant answers everything -> False."""
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.expired)
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_32_future_grant_denies_present_request(self):
        g = self._make_grant("g1", "training", valid_from=self.future)
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_33_open_ended_grant_permits_future_request(self):
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=None)
        r = self._make_request("training")
        self.assertTrue(permits([g], r, at=self.future).permitted)

    def test_case_34_expired_open_ended_grant_before_valid_from(self):
        g = self._make_grant("g1", "training", valid_from=self.now)
        r = self._make_request("training")
        self.assertFalse(permits([g], r, at=self.past).permitted)

    # --- MULTI-DIMENSIONAL COMBINATIONS & EDGE CASES (Cases 35-42) ---
    def test_case_35_all_5_dimensions_matching_returns_true(self):
        g = self._make_grant("g1", "training", commercial=True, territory=["US", "EU"], model_class="all_models", valid_from=self.past, valid_until=self.future)
        r = self._make_request("fine_tuning", commercial=False, territory=["US"], model_class="open_weights",
                               valid_until=self.future)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_36_failure_on_single_dimension_use_type(self):
        g = self._make_grant("g1", "human_reference", commercial=True, territory=["WW"], model_class="all_models")
        r = self._make_request("training", commercial=True, territory=["WW"], model_class="all_models")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_37_failure_on_single_dimension_commercial(self):
        g = self._make_grant("g1", "training", commercial=False, territory=["WW"], model_class="all_models")
        r = self._make_request("training", commercial=True, territory=["WW"], model_class="all_models")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_38_failure_on_single_dimension_territory(self):
        g = self._make_grant("g1", "training", commercial=True, territory=["US"], model_class="all_models")
        r = self._make_request("training", commercial=True, territory=["JP"], model_class="all_models")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_39_failure_on_single_dimension_model_class(self):
        g = self._make_grant("g1", "training", commercial=True, territory=["WW"], model_class="open_weights")
        r = self._make_request("training", commercial=True, territory=["WW"], model_class="proprietary_frontier")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_40_failure_on_single_dimension_temporal(self):
        g = self._make_grant("g1", "training", commercial=True, territory=["WW"], model_class="all_models", valid_until=self.expired)
        r = self._make_request("training", commercial=True, territory=["WW"], model_class="all_models")
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_41_empty_active_grants_list_returns_false(self):
        r = self._make_request("human_reference")
        self.assertFalse(permits([], r, at=self.now).permitted)

    def test_case_42_second_active_grant_matches_returns_true(self):
        g1 = self._make_grant("g1", "human_reference")
        g2 = self._make_grant("g2", "training")
        r = self._make_request("fine_tuning")
        res = permits([g1, g2], r, at=self.now)
        self.assertTrue(res.permitted)
        self.assertEqual(res.matching_grant_id, "g2")

    # --- EMPTY-TERRITORY SEMANTICS (Cases 43-45) ---
    # NOTE: these cases construct the grant Scope directly because _make_grant's
    # `territory or ["WW"]` coerces an explicit [] into ["WW"], which is exactly
    # the blind spot that let the empty-territory defect ship.
    def _make_grant_with_explicit_territory(self, grant_id, use_type, territory):
        return GrantEvent(
            event_id=f"evt-{grant_id}",
            grant_id=grant_id,
            work_id="work-01",
            counterparty_id="buyer-01",
            scope=Scope(
                use_type=use_type,
                territory=territory,
                valid_from=self.past
            ),
            kind="granted",
            issued_at=self.past,
            signature="sig"
        )

    def test_case_43_empty_granted_territory_means_worldwide_permits_us_request(self):
        """An empty territory list on a grant means UNRESTRICTED (worldwide), never 'no territories permitted'."""
        g = self._make_grant_with_explicit_territory("g1", "training", territory=[])
        r = self._make_request("training", territory=["US"])
        res = permits([g], r, at=self.now)
        self.assertTrue(res.permitted, "Empty granted territory must resolve as worldwide, not as zero territories!")
        self.assertEqual(res.matching_grant_id, "g1")

    def test_case_44_empty_granted_territory_permits_containment_across_use_type(self):
        """Empty granted territory + use-type containment: a training grant with territory=[] permits fine_tuning in US."""
        g = self._make_grant_with_explicit_territory("g1", "training", territory=[])
        r = self._make_request("fine_tuning", territory=["US"])
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_45_empty_requested_territory_denied_by_territory_limited_grant(self):
        """An empty REQUESTED territory asks for worldwide use; a US-only grant cannot contain it (set().issubset() must not slip through)."""
        g = self._make_grant("g1", "training", territory=["US"])
        r = Scope(use_type="training", territory=[], valid_from=self.now)
        self.assertFalse(permits([g], r, at=self.now).permitted)

    # --- FOLD BEFORE CONTAINMENT (Cases 46-47) ---
    # permits() takes ACTIVE grants. In the append-only log a revoked grant's
    # original `granted` event is still present; every log reader must fold
    # through active_grant_events() first, or a revoked grant keeps permitting.
    def _revoked_then_narrower_log(self):
        from src.schema.grant_event import GrantEvent
        broad = self._make_grant("g1", "training", commercial=True, territory=["WW"])
        revoke = GrantEvent(
            event_id="evt-g1-revoke", grant_id="g1", work_id="work-01", counterparty_id="buyer-01",
            scope=broad.scope, kind="revoked", supersedes="evt-g1",
            issued_at=self.past + timedelta(days=1), signature="sig"
        )
        narrower = GrantEvent(
            event_id="evt-g1-regrant", grant_id="g1", work_id="work-01", counterparty_id="buyer-01",
            scope=Scope(use_type="fine_tuning", model_class="open_weights", commercial=False,
                        territory=["US"], valid_from=self.past + timedelta(days=2)),
            kind="granted", issued_at=self.past + timedelta(days=2), signature="sig"
        )
        return [broad, revoke, narrower]

    def test_case_46_revoked_grants_original_event_cannot_permit_after_fold(self):
        """Raw append-only events must be REFUSED by permits(), and the folded
        active set must deny the broad request the revoked grant once allowed.

        The door is closed rather than filtered: permits() used to skip
        non-granted events silently, so a caller passing raw events got an
        answer computed partly from revoked history. It now raises."""
        from src.resolve.resolver import active_grant_events
        events = self._revoked_then_narrower_log()
        r = self._make_request("training", commercial=True, territory=["WW"])

        with self.assertRaises(ValueError, msg="permits() must refuse raw append-only events"):
            permits(events, r, at=self.now)

        active = active_grant_events(events, at=self.now)
        self.assertFalse(permits(active, r, at=self.now).permitted)

    def test_case_47_fold_resolves_to_narrower_regrant(self):
        """After revoke-then-regrant-narrower, the folded active set permits
        exactly the narrower scope and nothing broader (HOD-107 on the read path)."""
        from src.resolve.resolver import active_grant_events
        active = active_grant_events(self._revoked_then_narrower_log(), at=self.now)
        self.assertEqual(len(active), 1)
        narrower_req = self._make_request("fine_tuning", commercial=False, territory=["US"], model_class="open_weights")
        self.assertTrue(permits(active, narrower_req, at=self.now).permitted)
        broader_req = self._make_request("fine_tuning", commercial=False, territory=["US", "EU"], model_class="open_weights")
        self.assertFalse(permits(active, broader_req, at=self.now).permitted)

    # --- REQUEST-WINDOW CONTAINMENT (Cases 48-56, HOD-702) ---
    # Currency is not containment. A grant alive at the evaluation instant has
    # answered "am I alive", not "do I cover the window being asked for". These
    # cases pin requested ⊆ granted on the temporal dimension itself.

    def test_case_48_request_extending_past_bounded_grant_denied_even_while_grant_current(self):
        """The September/December case: grant through +30d, asked NOW for
        rights through +120d. The evaluation instant is inside the grant, and
        the answer must still be no — checking currency alone was the defect."""
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training", valid_until=self.now + timedelta(days=120))
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_49_request_window_inside_bounded_grant_permitted(self):
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training", valid_until=self.now + timedelta(days=10))
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_50_open_ended_request_denied_by_bounded_grant(self):
        """valid_until=None on a request asks for rights forever; a bounded
        grant cannot contain forever, and the evaluator refuses rather than
        quietly truncating what was asked."""
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training")  # open-ended
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_51_open_ended_request_permitted_by_unbounded_grant(self):
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=None)
        r = self._make_request("training")  # open-ended
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_52_request_beginning_before_grant_denied(self):
        """A request whose window opens before the grant existed asks for
        rights the grant never covered."""
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=None)
        r = self._make_request("training", valid_from=self.past - timedelta(days=1))
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_53_request_window_exactly_equal_to_grant_window_permitted(self):
        """Boundary inclusivity: requested == granted is containment."""
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training", valid_from=self.past, valid_until=self.future)
        self.assertTrue(permits([g], r, at=self.now).permitted)

    def test_case_54_malformed_interval_rejected_at_the_schema(self):
        """valid_until before valid_from is not a narrow scope, it is a
        malformed one, and it never reaches the evaluator."""
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            Scope(use_type="training", valid_from=self.now, valid_until=self.now - timedelta(seconds=1))

    def test_case_55_request_one_second_past_grant_end_denied(self):
        g = self._make_grant("g1", "training", valid_from=self.past, valid_until=self.future)
        r = self._make_request("training", valid_until=self.future + timedelta(seconds=1))
        self.assertFalse(permits([g], r, at=self.now).permitted)

    def test_case_56_union_on_temporal_dimension_via_single_unbounded_grant(self):
        """Two grants: one bounded short, one unbounded. An open-ended request
        is permitted by the unbounded grant ALONE — union semantics hold on
        the temporal dimension exactly as on every other."""
        short = self._make_grant("g-short", "training", valid_from=self.past, valid_until=self.future)
        forever = self._make_grant("g-forever", "training", valid_from=self.past, valid_until=None)
        r = self._make_request("training")  # open-ended
        res = permits([short, forever], r, at=self.now)
        self.assertTrue(res.permitted)
        self.assertEqual(res.matching_grant_id, "g-forever")

if __name__ == "__main__":
    unittest.main()
