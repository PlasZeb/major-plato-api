"""Private, atomic GitHub decision archive. No browser-facing read endpoint."""
import base64
import copy
import csv
import hashlib
import html
import io
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests

AXES = ("ethical", "military", "command")


class ArchiveError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def public(value):
    """Remove instructor-only fields recursively before map persistence or responses."""
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items()
                if k not in {"assessment", "score_delta", "scores", "scoring", "rubric", "instructor_notes"}}
    if isinstance(value, list):
        return [public(v) for v in value]
    return value


def rubric():
    raw = os.environ.get("SCORING_RUBRIC_JSON")
    if not raw:
        return None
    try:
        result = json.loads(raw)
        assert isinstance(result["version"], str) and result["version"]
        assert isinstance(result["instructions"], str) and result["instructions"]
        for axis in AXES:
            rule = result["axes"][axis]
            assert all(type(rule[k]) is int for k in ("initial", "min", "max", "max_delta"))
            assert rule["min"] <= rule["initial"] <= rule["max"] and rule["max_delta"] >= 0
        return result
    except (ValueError, KeyError, TypeError, AssertionError):
        raise ArchiveError("invalid_scoring_rubric") from None


def score_record(doc, delta, rules):
    previous = doc.get("decisions", [])
    if not rules:
        return {"status": "not_configured", "rubric_version": None,
                "before": None, "delta": None, "after": None}
    # Never silently bridge a missing evaluation or change the rubric mid-session.
    if previous:
        last = previous[-1].get("scoring", {})
        if last.get("rubric_version") != rules["version"] or last.get("after") is None:
            return {"status": "baseline_required", "rubric_version": rules["version"],
                    "before": None, "delta": None, "after": None}
        before = last["after"]
    else:
        before = {a: rules["axes"][a]["initial"] for a in AXES}
    if not isinstance(delta, dict) or any(type(delta.get(a)) is not int or
            abs(delta[a]) > rules["axes"][a]["max_delta"] for a in AXES):
        return {"status": "not_evaluated", "rubric_version": rules["version"],
                "before": before, "delta": None, "after": None}
    after = {a: max(rules["axes"][a]["min"], min(rules["axes"][a]["max"], before[a] + delta[a])) for a in AXES}
    return {"status": "evaluated", "rubric_version": rules["version"], "before": before,
            "proposed_delta": delta, "delta": {a: after[a] - before[a] for a in AXES}, "after": after}


def csv_cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def exports(doc):
    stream = io.StringIO(newline="")
    fields = ["session_id", "scenario_id", "player", "unit", "turn_id", "occurred_at", "status", "player_action", "rubric_version", "scoring_status"]
    fields += [f"{a}_{k}" for a in AXES for k in ("before", "delta", "after", "reason")]
    fields += [f"{a}_reported" for a in AXES]
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
    writer.writeheader()
    lines = ["# Oktatói játékmenetnapló", "", f"Játékmenet: {html.escape(doc['session_id'])}",
             "", "A hiányzó pontszám nem nulla: nincs értékelve vagy nincs hiteles kezdőérték.", ""]
    for record in doc["decisions"]:
        scoring = record.get("scoring", {})
        row = {k: record.get(k, "") for k in fields}
        row.update(session_id=doc["session_id"], scenario_id=doc.get("scenario_id", ""),
                   player=doc.get("player", ""), unit=doc.get("unit", ""),
                   rubric_version=scoring.get("rubric_version"), scoring_status=scoring.get("status"))
        for a in AXES:
            for k in ("before", "delta", "after"):
                row[f"{a}_{k}"] = (scoring.get(k) or {}).get(a)
            row[f"{a}_reason"] = record.get("assessment", {}).get(a, "")
            row[f"{a}_reported"] = record.get("reported_scores", {}).get(a)
        writer.writerow({k: csv_cell(v) for k, v in row.items()})
        lines += [f"## {html.escape(str(record['turn_id']))}", "",
                  html.escape(str(record.get("occurred_at", ""))), "",
                  "Állapot: " + html.escape(record.get("status", "")), "",
                  "<pre>" + html.escape(json.dumps(record.get("player_action"), ensure_ascii=False, indent=2)) + "</pre>", ""]
        for a in AXES:
            values = [row[f"{a}_{k}"] for k in ("before", "delta", "after")]
            lines += [f"**{a}**: " + " → ".join("nincs értékelve" if x is None else str(x) for x in values),
                      "", "<pre>" + html.escape(str(row[f"{a}_reason"])) + "</pre>", ""]
            if row[f"{a}_reported"] is not None:
                lines += [f"Korábban közölt {a} érték: {row[f'{a}_reported']} (nem jelölt, hogy változás vagy összpont).", ""]
    return {"session.json": json.dumps(doc, ensure_ascii=False, indent=2),
            "decisions.csv": "\ufeff" + stream.getvalue(), "README.md": "\n".join(lines)}


class Archive:
    def __init__(self):
        self.repo = os.environ.get("LOG_REPO", "PlasZeb/major-plato-logs")
        token = os.environ.get("GITHUB_TOKEN")
        if not token or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo):
            raise ArchiveError("github_logging_not_configured")
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        meta = self.call("GET", "")
        if meta.get("private") is not True:
            raise ArchiveError("log_repository_must_be_private")
        self.branch = meta["default_branch"]

    def call(self, method, path, body=None, missing=False, conflict=False):
        try:
            response = requests.request(method, f"https://api.github.com/repos/{self.repo}{path}",
                                        headers=self.headers, json=body, timeout=20)
            if missing and response.status_code == 404:
                return None
            if conflict and response.status_code in (409, 422):
                return None
            if response.status_code >= 400:
                raise ArchiveError(f"github_http_{response.status_code}")
            return response.json()
        except (requests.RequestException, ValueError):
            raise ArchiveError("github_unreachable") from None

    def folder(self, session_id):
        # Keep map UUIDs recognizable; hash arbitrary names/paths without collisions.
        safe = session_id if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session_id) else digest(session_id)
        return "sessions/" + safe

    def read(self, session_id):
        head = self.call("GET", "/git/ref/heads/" + quote(self.branch, safe=""))["object"]["sha"]
        file = self.call("GET", "/contents/" + self.folder(session_id) + "/session.json?ref=" + head, missing=True)
        if file:
            doc = json.loads(base64.b64decode(file["content"]).decode())
        else:
            doc = {"schema_version": 1, "session_id": session_id, "created_at": now(), "decisions": []}
        return head, doc

    def update(self, session_id, mutate):
        for _ in range(4):
            head, doc = self.read(session_id)
            result, changed = mutate(doc)
            if not changed:
                return result
            doc["updated_at"] = now()
            base = self.call("GET", "/git/commits/" + head)["tree"]["sha"]
            tree = [{"path": self.folder(session_id) + "/" + path, "mode": "100644", "type": "blob", "content": content}
                    for path, content in exports(doc).items()]
            tree_sha = self.call("POST", "/git/trees", {"base_tree": base, "tree": tree})["sha"]
            commit = self.call("POST", "/git/commits", {"message": "Update instructor session archive",
                                "tree": tree_sha, "parents": [head]})["sha"]
            updated = self.call("PATCH", "/git/refs/heads/" + quote(self.branch, safe=""),
                                {"sha": commit, "force": False}, conflict=True)
            if updated:
                return result
        raise ArchiveError("archive_concurrent_update_retry")

    def reserve(self, session_id, scenario_id, turn_id, action, rules, turn_number=None):
        fingerprint = digest({"scenario_id": scenario_id, "action": action})
        def mutate(doc):
            for record in doc["decisions"]:
                if record["turn_id"] == turn_id:
                    if record["fingerprint"] != fingerprint:
                        raise ArchiveError("turn_id_reused_with_different_action")
                    return (record, False), False
            if doc["decisions"] and doc["decisions"][-1]["status"] not in ("completed", "failed_before_dispatch"):
                raise ArchiveError("session_has_pending_turn")
            if turn_number is not None and any(r.get("turn_number", -1) >= turn_number
                    and r["status"] != "failed_before_dispatch" for r in doc["decisions"]):
                raise ArchiveError("stale_map_turn")
            doc.setdefault("scenario_id", scenario_id)
            if doc["scenario_id"] != scenario_id:
                raise ArchiveError("archive_scenario_mismatch")
            if doc["decisions"]:
                rules_for_session = doc.get("rubric")
            else:
                rules_for_session = rules
                doc["rubric"] = rules
            record = {"turn_id": turn_id, "fingerprint": fingerprint, "occurred_at": now(),
                      "player_action": action, "status": "processing", "rubric": rules_for_session,
                      "turn_number": turn_number if turn_number is not None else -1}
            doc["decisions"].append(record)
            return (record, True), True
        return self.update(session_id, mutate)

    def amend(self, session_id, turn_id, changes, evaluate=False):
        def mutate(doc):
            record = next(r for r in doc["decisions"] if r["turn_id"] == turn_id)
            if evaluate:
                index = doc["decisions"].index(record)
                history = {"decisions": [r for r in doc["decisions"][:index] if r.get("status") != "failed_before_dispatch"]}
                record["scoring"] = score_record(history, changes.get("score_delta"), record.get("rubric"))
            record.update(copy.deepcopy(changes))
            record["updated_at"] = now()
            return record, True
        return self.update(session_id, mutate)
