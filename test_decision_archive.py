import copy
import csv
import io
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request
import app
from decision_archive import Archive, ArchiveError, AXES, exports, public, score_record


RULES = {"version": "test-only", "instructions": "Test fixture only",
         "axes": {a: {"initial": 10, "min": 0, "max": 20, "max_delta": 15} for a in AXES}}


class MemoryArchive(Archive):
    def __init__(self):
        self.docs = {}
        self.fail_completion = False

    def read(self, session_id):
        return "head", copy.deepcopy(self.docs.get(session_id, {"session_id": session_id, "decisions": []}))

    def update(self, session_id, mutate):
        doc = copy.deepcopy(self.docs.get(session_id, {"session_id": session_id, "decisions": []}))
        result, changed = mutate(doc)
        if changed:
            if self.fail_completion and doc["decisions"][-1]["status"] == "completed":
                raise ArchiveError("github_unreachable")
            self.docs[session_id] = doc
        return result


class ArchiveTests(unittest.TestCase):
    def test_scores_arithmetic_clamping_and_missing(self):
        score = score_record({}, {a: 15 for a in AXES}, RULES)
        self.assertEqual(score["after"]["ethical"], 20)
        self.assertEqual(score["delta"]["ethical"], 10)
        self.assertIsNone(score_record({}, {}, None)["after"])
        self.assertEqual(score_record({}, {a: True for a in AXES}, RULES)["status"], "not_evaluated")
        history = {"decisions": [{"scoring": {"after": None}}]}
        self.assertEqual(score_record(history, {a: 1 for a in AXES}, RULES)["status"], "baseline_required")

    def test_no_private_fields_in_nested_public_response(self):
        result = public({"state": {"engine": {"last_response": {"turn": {
            "assessment": {"ethical": "private"}, "score_delta": {"ethical": -1}, "narrative": "moved"}}}}})
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("score_delta", json.dumps(result))

    def test_csv_unicode_injection_and_legacy_values(self):
        doc = {"session_id": "=HYPERLINK(1)", "decisions": [{"turn_id": "t", "status": "completed",
               "assessment": {"ethical": "=DANGEROUS()"}, "player_action": {"text": "Árvíztűrő"},
               "reported_scores": {"ethical": -25}}]}
        files = exports(doc)
        row = next(csv.DictReader(io.StringIO(files["decisions.csv"].lstrip("\ufeff")), delimiter=";"))
        self.assertTrue(row["session_id"].startswith("'="))
        self.assertTrue(row["ethical_reason"].startswith("'="))
        self.assertEqual(row["ethical_reported"], "-25")
        self.assertIn("Árvíztűrő", row["player_action"])

    def test_reservation_duplicate_conflict_and_pending(self):
        archive = MemoryArchive()
        record, created = archive.reserve("s", "v", "t", {"a": 1}, RULES, 1)
        self.assertTrue(created)
        self.assertFalse(archive.reserve("s", "v", "t", {"a": 1}, RULES, 1)[1])
        with self.assertRaisesRegex(ArchiveError, "different_action"):
            archive.reserve("s", "v", "t", {"a": 2}, RULES, 1)
        with self.assertRaisesRegex(ArchiveError, "pending"):
            archive.reserve("s", "v", "u", {}, RULES, 1)
        archive.amend("s", "t", {"status": "completed"})
        with self.assertRaisesRegex(ArchiveError, "stale"):
            archive.reserve("s", "v", "u", {}, RULES, 1)

    def test_atomic_export_conflict_reloads_instead_of_overwrite(self):
        archive = object.__new__(Archive)
        archive.branch = "main"
        reads = [("head1", {"session_id": "s", "decisions": []}),
                 ("head2", {"session_id": "s", "decisions": []})]
        tree_calls = []
        def call(method, path, body=None, **kwargs):
            if path.startswith("/git/commits/"):
                return {"tree": {"sha": "base"}}
            if path == "/git/trees":
                tree_calls.append(body)
                return {"sha": "tree"}
            if path == "/git/commits":
                return {"sha": "commit"}
            if method == "PATCH":
                self.assertFalse(body["force"])
                return None if len(tree_calls) == 1 else {"ok": True}
        with patch.object(archive, "read", side_effect=reads), patch.object(archive, "call", side_effect=call):
            archive.update("s", lambda doc: ("ok", True))
        self.assertEqual(len(tree_calls), 2)
        self.assertEqual({r["path"].rsplit("/", 1)[1] for r in tree_calls[-1]["tree"]},
                         {"session.json", "decisions.csv", "README.md"})

    def test_public_repository_rejected(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test"}), patch.object(Archive, "call", return_value={"private": False}):
            with self.assertRaisesRegex(ArchiveError, "private"):
                Archive()

    def test_map_history_reads_beyond_first_fifty_events(self):
        from unittest.mock import Mock
        pages = [[{"id": i} for i in range(1, 51)], [{"id": 51}]]
        responses = []
        for page in pages:
            response = Mock(status_code=200)
            response.json.return_value = {"events": page}
            responses.append(response)
        with patch.object(app, "_map_request", side_effect=responses) as request:
            self.assertEqual(len(app._map_session_events("s")), 51)
            self.assertIn("after=50", request.call_args_list[1].args[1])


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.archive = MemoryArchive()
        self.state = app._default_game_state("village_shield")
        self.request = Request({"type": "http", "headers": []})
        self.turn = app.TurnRequest(session_id="s", map_session_id="s", map_session_token="test",
                                   scenario_id="village_shield", turn_id="t", expected_turn=1,
                                   player_action={"type": "move_unit", "unit_id": "alpha", "target_location_id": "bridge"})
        self.model = {"narrative": "Az egység elindul.", "assessment": {a: "INSTRUCTOR_ONLY" for a in AXES},
                      "score_delta": {a: 1 for a in AXES}, "map_actions": [], "state_delta": {},
                      "events": [], "next_state_summary": "Elindult."}

    def run_turn(self, completion_failure=False, model_error=None):
        self.archive.fail_completion = completion_failure
        def persist(**kwargs):
            self.assertNotIn("assessment", kwargs["model_turn"])
            self.assertNotIn("score_delta", kwargs["model_turn"])
            return self.state, {}
        with patch.object(app, "Archive", return_value=self.archive), \
             patch.object(app, "rubric", return_value=RULES), \
             patch.object(app, "_map_session_state", return_value={"scenario_id": "village_shield", "state": self.state}), \
             patch.object(app, "_map_session_events", return_value=[]), \
             patch.object(app, "_openai_response", return_value=({"id": "r"}, copy.deepcopy(self.model)), side_effect=model_error) as model, \
             patch.object(app, "_dispatch_map_actions", return_value={"status": "not_requested", "results": []}) as dispatch, \
             patch.object(app, "_persist_turn_to_map", side_effect=persist):
            try:
                result = app.resolve_turn(self.turn, self.request)
            except HTTPException as exc:
                result = exc
            return result, model.call_count, dispatch.call_count

    def test_automatic_archive_replay_and_privacy(self):
        result, _, count = self.run_turn()
        self.assertEqual(count, 1)
        record = self.archive.docs["s"]["decisions"][0]
        self.assertEqual(record["scoring"]["after"]["ethical"], 11)
        self.assertEqual(record["player_action"], self.turn.player_action)
        self.assertNotIn("INSTRUCTOR_ONLY", json.dumps(result))
        result, model_count, dispatch_count = self.run_turn()
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual((model_count, dispatch_count), (0, 0))
        self.assertEqual(len(self.archive.docs["s"]["decisions"]), 1)

    def test_failed_completion_keeps_archive_and_does_not_repeat_move(self):
        result, _, count = self.run_turn(completion_failure=True)
        self.assertIsInstance(result, HTTPException)
        self.assertEqual(count, 1)
        self.assertEqual(self.archive.docs["s"]["decisions"][0]["status"], "needs_review")
        result, model_count, dispatch_count = self.run_turn()
        self.assertEqual(result.status_code, 409)
        self.assertEqual((model_count, dispatch_count), (0, 0))

    def test_model_failure_logged_before_any_dispatch(self):
        result, _, count = self.run_turn(model_error=HTTPException(502, "test failure"))
        self.assertEqual(count, 0)
        self.assertEqual(self.archive.docs["s"]["decisions"][0]["status"], "failed_before_dispatch")

    def test_legacy_isolation_deduplication_and_score_preservation(self):
        log = app.DecisionLog(player="teszt", unit="alpha", decisions=[["2026-09-09", "Döntés", -25, -15, -20]])
        with patch.object(app, "Archive", return_value=self.archive):
            first = app.append_log(log)
            second = app.append_log(log)
        self.assertEqual(first["path"], second["path"])
        doc = next(iter(self.archive.docs.values()))
        self.assertEqual(len(doc["decisions"]), 1)
        self.assertEqual(doc["decisions"][0]["reported_scores"]["ethical"], -25)
        self.assertIsNone(doc["decisions"][0]["scoring"]["after"])


if __name__ == "__main__":
    unittest.main()
