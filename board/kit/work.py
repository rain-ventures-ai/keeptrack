"""Durable task ownership. Metadata never grants approval or external-effect rights."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import urllib.parse

SCHEMA = 1
MAX_INPUT = 16384
MAX_RUNS = 16
MAX_EVENTS = 8
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
RUN = re.compile(r"wr_[a-f0-9]{24}\Z")
PR_LINK = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+(?:[?#].*)?\Z")
PROGRESS = {"progress", "waiting", "result_ready", "failed"}
PRIVATE = re.compile(r"(?:gh[pousr]_|github_pat_|sk-ant-|sk-proj-|xox[baprs]-)[A-Za-z0-9_.-]{10,}"
                     r"|sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY"
                     r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
                     r"|(?<!\w)(?:\+\d{1,3}[ -]?)?\(?0\d{2,4}\)?[ -]\d{3,4}[ -]\d{3,4}(?!\w)"
                     r"|[$£€]\s*\d|\b\d+(?:\.\d+)?\s*(?:USD|GBP|EUR)\b")
PRIVATE = re.compile(PRIVATE.pattern +
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\b(?:sk_live_|rk_live_|glpat-)[A-Za-z0-9_-]{10,}"
    r"|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|\(\d{3}\)\s*\d{3}[- ]\d{4}|\b(?:USD|GBP|EUR)\s+\d"
    r"|\b\d[\d,]*(?:\.\d+)?\s+(?:dollars|pounds|euros)\b"
    r"|[?&](?:token|access_token|api_key|apikey|secret|password|auth|authorization)=[^\s\"&]+", re.I)


class Refused(SystemExit):
    """A validation refusal, distinct from an uncertain transport/save failure."""


def fail(message):
    raise Refused("work: " + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def text(value, name, cap, *, required=False):
    if not isinstance(value, str) or len(value) > cap or (required and not value.strip()) or "\x00" in value:
        fail(f"{name} must be {'non-empty ' if required else ''}text of at most {cap} characters")
    return value.strip()


def payload(value):
    if not isinstance(value, dict) or set(value) - {"request_id", "title", "project", "details", "todos"}:
        fail("request needs only request_id, title, project, details and todos")
    result = {"request_id": text(value.get("request_id"), "request_id", 128, required=True),
              "title": text(value.get("title"), "title", 160, required=True),
              "project": text(value.get("project"), "project", 80, required=True),
              "details": text(value.get("details", ""), "details", 2000)}
    if not KEY.fullmatch(result["request_id"]) or any(c in result["title"] for c in "\r\n"):
        fail("request_id has invalid characters or title is not one line")
    todos = value.get("todos", [])
    if not isinstance(todos, list) or len(todos) > 20:
        fail("todos must be a list of at most 20 items")
    result["todos"] = [text(t, "todo", 300, required=True) for t in todos]
    return result


def safe_content(kt, value):
    # Same board boundary as other CLI writes; never echo the rejected content.
    raw = json.dumps(value, ensure_ascii=False)
    if PRIVATE.search(raw):
        fail("content contains secret-shaped or contact information; link to an authorised document instead")


def public(value):
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if not k.startswith("_")}
    return [public(v) for v in value] if isinstance(value, list) else value


def coordinate(task):
    current = task.get("coordination")
    if current is None:
        current = {"v": SCHEMA, "owner": "rook:" + str(task.get("project") or "unscoped"),
                   "executor": "relay-local", "runs": []}
        task["coordination"] = current
    if not isinstance(current, dict) or current.get("v") != SCHEMA or not isinstance(current.get("runs"), list):
        fail("coordination metadata needs a supported kit; nothing changed")
    return current


def require_current_kit(data):
    settings = data.setdefault("settings", {})
    minimum = settings.get("min_kit")
    settings["min_kit"] = max(123, minimum) if type(minimum) is int else 123


def strict_archives(kt, data, base):
    found = {}
    for key in kt.archive_years(data):
        archive, _ = kt.read_archive(key, base)
        if not isinstance(archive, dict) or not isinstance(archive.get("tasks"), list):
            fail("cannot establish request identity: an archive is missing or unreadable")
        for task in archive["tasks"]:
            if isinstance(task, dict) and task.get("id"):
                found[task["id"]] = task
    return found


def view(kt, task, *, data=None, archived=False):
    co = public(task.get("coordination") or {})
    claim = task.get("claim") or {}
    wait = kt.open_waiting(task)
    if archived:
        state, next_step = "archived", "inspect archived outcome; no new task was created"
    elif any(r.get("needs_reconciliation") and not r.get("resolution") for r in co.get("runs", [])):
        state, next_step = "reconciliation_required", "inspect this run's effects; an old card outcome or link does not resolve them"
    elif any(unresolved(r) for r in co.get("runs", [])):
        active = kt.claim_state(data or {}, claim) == "running" and any(
            not r.get("terminal") and r.get("_claim") == claim_hash(kt, claim)
            for r in (task.get("coordination") or {}).get("runs", []))
        state = "running" if active else "reconciliation_required"
        next_step = "follow the current claim; a recorded claim is not proof of process liveness" if active else \
            "the runner must reconcile its unresolved attempt before another launch"
    elif task.get("column") == "done":
        state, next_step = ("cancelled" if task.get("outcome") == "cancelled" else "complete"), "no execution is requested"
    elif wait:
        state, next_step = "waiting", "resolve the existing wait through its normal authorised path"
    elif task.get("column") == "pending-review":
        state, next_step = "pending_review", "the owner decides on the recorded result"
    elif claim and claim.get("status") != "done":
        state = "running" if kt.claim_state(data or {}, claim) == "running" else "reconciliation_required"
        next_step = "follow the current claim; a recorded claim is not proof of process liveness"
    elif co.get("runs") and co["runs"][-1].get("result"):
        state, next_step = "result_ready", "reconcile this run's host-attested evidence through the existing result/review path"
    elif task.get("column") == "todo":
        state, next_step = "awaiting_runner", "subject to can-start, opt-in and limits; runner availability has not been observed"
    else:
        state, next_step = "awaiting_approval", "saved only; explicit named-card approval is required before unattended work"
    return {"schema": "keeptrack.work/1", "id": task["id"], "num": task.get("num"), "title": task.get("title"),
            "url": kt.card_url(task.get("num"), task["id"]), "column": task.get("column"), "state": state,
            "next": next_step, "coordination": co, "runner_liveness": "unknown", "authority_granted": False}


def request(kt, value):
    value = payload(value)
    safe_content(kt, value)
    tid = "t_" + digest(["rook-work", value["request_id"]])[:20]
    answer = {}

    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True
        answer.clear()
        existing = next((t for t in data.get("tasks", []) if t.get("id") == tid), None)
        archived = False
        if existing is None:
            existing = strict_archives(kt, data, kt._MUT["base"]).get(tid)
            archived = existing is not None
        if existing is not None:
            receipt = (existing.get("coordination") or {}).get("request") or {}
            original = receipt.get("digest")
            legacy_exact = not receipt.get("source_project") and original == digest(value)
            candidates = {receipt["project_id"]} if receipt.get("project_id") else {
                p.get("id") for p in data.get("projects", []) if isinstance(p, dict)} | {
                existing.get("project"), str((existing.get("coordination") or {}).get("owner", "")).removeprefix("rook:")}
            matches = [p for p in candidates if p and digest({**value, "project": p}) == original]
            project = matches[0] if len(matches) == 1 else None
            alias = value["project"] in {receipt.get("source_project"), project}
            if project and not alias:
                try:
                    alias = kt.find_project(data, value["project"])["id"] == project
                except SystemExit:
                    alias = False
            if not legacy_exact and not (project and alias):
                fail("request_id already exists with a different original payload; show it instead of adding another card")
            answer.update(view(kt, existing, data=data, archived=archived), created=False)
            return
        pr = kt.find_project(data, value["project"])
        original = digest({**value, "project": pr["id"]})
        if not any(c.get("id") == "backlog" for c in data.get("columns", [])):
            fail("this board has no Backlog column")
        ts = kt.now()
        task = {"id": tid, "title": value["title"], "project": pr["id"], "client": pr.get("client", ""),
                "column": "backlog", "priority": "medium", "due": "", "labels": [],
                "assignees": [os.environ.get("BOARD_USER", "")], "details": value["details"], "links": [], "contacts": [],
                "todos": [{"id": "d_" + secrets.token_hex(3), "text": t, "done": False} for t in value["todos"]],
                "history": [], "comments": [], "claim": None, "created": ts, "updated": ts,
                "createdBy": kt.who_am_i()}
        co = coordinate(task)
        require_current_kit(data)
        co["request"] = {"key": value["request_id"], "digest": original, "project_id": pr["id"],
                         "source_project": value["project"], "submitted_by": kt.who_am_i(), "received_at": ts}
        task["rank"] = kt.append_rank([t.get("rank") for t in data.get("tasks", [])
                                       if t.get("column") == "backlog" and kt.valid_rank(t.get("rank"))])
        kt.append_priority_rank(data, task)
        kt.hist(task, "Rook request saved; awaiting explicit approval")
        data.setdefault("tasks", []).append(task)
        kt.assign_nums(data)
        marks = kt.mark_similar(data, task)
        answer.update(view(kt, task, data=data), created=True, possible_related=marks)
    # Only a JSON result is printed; normal mutation's own buffered output stays empty.
    kt.mutate(change, "Rook: save request")
    print(json.dumps(answer, ensure_ascii=False))


def status(kt, ref):
    data, base = kt.load()
    task = next((t for t in data.get("tasks", []) if t.get("id") == ref or str(t.get("num")) == ref.lstrip("#")), None)
    archived = False
    if task is None:
        archived = True
        task = next((t for t in strict_archives(kt, data, base).values()
                     if t.get("id") == ref or str(t.get("num")) == ref.lstrip("#")), None)
    if task is None:
        fail("task not found")
    print(json.dumps(view(kt, task, data=data, archived=archived), ensure_ascii=False))


def session(kt):
    value = kt.explicit_session()
    if not value or not kt.usable_session(value):
        fail("an explicit BOARD_SESSION is required")
    return value


def claim_hash(kt, claim):
    return digest([claim.get("agent"), claim.get("session_id"), claim.get("generation") or claim.get("claimed_at")])


def unresolved(run):
    return not run.get("terminal") or (run.get("needs_reconciliation") and not run.get("resolution"))


def run_projects(task, run):
    """Retargeting a card cannot move an already running attempt's hold."""
    projects = {task.get("project"), run.get("project_id")}
    if not run.get("project_id"):
        owner = str((task.get("coordination") or {}).get("owner") or "")
        if owner.startswith("rook:"):
            projects.add(owner[5:])  # conservative scope for historical receipts
    return projects - {None, ""}


def claim_gate(kt, data, task, sid, executor, attended):
    if attended:
        return
    co = task.get("coordination")
    mine = None
    claim = task.get("claim") or {}
    renewing = claim.get("session_id") == sid and not claim.get("attended") and kt.claim_state(data, claim) == "running"
    if executor == "relay-local" and task.get("column") != "todo" and not (renewing and claim.get("unattended_approved") is True):
        fail("unattended runner claims require an approved To do card; no claim written")
    if co is not None:
        co = coordinate(task)
        claim = task.get("claim") or {}
        runs = co["runs"]
        renewing = claim.get("session_id") == sid and not claim.get("attended") and kt.claim_state(data, claim) == "running"
        if renewing and runs and runs[-1].get("_claim") == claim_hash(kt, claim) and not runs[-1].get("terminal"):
            mine = runs[-1]
        if co.get("executor") != "relay-local" or (executor != "relay-local" and mine is None):
            fail("this coordinated task requires its selected relay-local host; no claim written")
        if task.get("column") != "todo" and not renewing:
            fail("unattended coordinated claims require an approved To do card; no claim written")
    for other in data.get("tasks", []):
        for run in (other.get("coordination") or {}).get("runs", []):
            if other is not task and (not task.get("project") or task["project"] not in run_projects(other, run)):
                continue
            if run is not mine and unresolved(run):
                fail("this project has an unresolved coordinated attempt; no claim written")


def own_running_claim(kt, data, task):
    claim = task.get("claim") or {}
    if not claim or claim.get("session_id") != session(kt) or kt.is_placeholder_claim(claim):
        fail("a real claim owned by this exact session is required")
    if kt.claim_state(data, claim) != "running" or kt.open_waiting(task):
        fail("the exact claim must be running and the task must not be waiting")
    if claim.get("attended"):
        fail("runner transitions require an unattended claim; attended work grants no unattended approval")
    if claim.get("unattended_approved") is not True:
        fail("runner transitions require a claim from approved To do work; historical or interactive claims grant no unattended approval")
    return claim


def process_identity(pid):
    try:
        with open(f"/proc/{int(pid)}/stat", encoding="ascii") as source:
            raw = source.read(8192)
        return raw.rsplit(")", 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def receipt(path, run_id, *, create=False, host_pid=None, task_id=None):
    """Private host-only proof. Never returned by status, branch names or stdout."""
    path = os.path.abspath(path)
    if create:
        body = {"v": 1, "run_id": run_id, "proof": secrets.token_hex(32), "task_id": task_id,
                "host_pid": host_pid or os.getppid(), "host_start": process_identity(host_pid or os.getppid()), "phase": "prepared",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(body, stream)
                stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # publish complete bytes without replacing any existing proof
            except FileExistsError:
                return receipt(path, run_id)
            return {**body, "_created": True}
        finally:
            os.unlink(temporary)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            st = os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_size > 4096:
                fail("runner receipt must be a private owned regular file")
            body = json.loads(stream.read(4097))
    except (OSError, ValueError):
        fail("runner receipt is missing or invalid")
    if not isinstance(body, dict) or body.get("run_id") != run_id or not re.fullmatch(r"[a-f0-9]{64}", str(body.get("proof", ""))):
        fail("runner receipt does not match the attempt")
    return body


def attempt(kt, data, task, run_id, proof, *, retiring=False):
    co = coordinate(task)
    runs = co["runs"]
    run = next((r for r in runs if r.get("id") == run_id), None)
    if not run or not secrets.compare_digest(str(run.get("_proof", "")), digest(proof["proof"])):
        fail("runner-only proof does not match this attempt")
    if runs[-1] is not run and not retiring:
        fail("a newer attempt supersedes this run")
    claim = task.get("claim") or {}
    if claim and claim_hash(kt, claim) != run.get("_claim") and not retiring:
        fail("another claim supersedes this run")
    return run


def start(kt, ref, run_id, proof_path, host_pid=None):
    if not RUN.fullmatch(run_id):
        fail("run id must be wr_ followed by 24 lowercase hex digits")
    proof = receipt(proof_path, run_id, create=True, host_pid=host_pid, task_id=ref)
    result = {}

    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True
        try:
            task = kt.find(data, ref)
        except SystemExit as exc:
            raise Refused(str(exc)) from None
        co = coordinate(task)
        if co.get("executor") != "relay-local":
            fail("this executor is not supported by the local runner")
        old = next((r for r in co["runs"] if r.get("id") == run_id), None)
        if old:
            attempt(kt, data, task, run_id, proof, retiring=True)
            result.update(created=False, run_id=run_id, state="already_started", launch=False)
            return
        claim = own_running_claim(kt, data, task)
        claim.setdefault("generation", secrets.token_hex(12))
        charged = [r for r in co["runs"] if (r.get("terminal") or {}).get("launch_state") != "not_launched"
                   and (r.get("resolution") or {}).get("disposition") != "retry-safe"]
        if len(charged) >= MAX_RUNS:
            fail("attempt limit reached; retain the receipts and reconcile the task")
        if any(unresolved(r) for r in co["runs"]):
            fail("an unresolved attempt needs reconciliation before another start")
        for other in data.get("tasks", []):
            if other is task or not task.get("project"):
                continue
            other_co = other.get("coordination") or {}
            if other.get("project") == task["project"] and other.get("claim") and kt.claim_state(data, other["claim"]) == "running":
                fail("this project's other implementation is still claimed or unresolved")
            if any(unresolved(r) and task["project"] in run_projects(other, r) for r in other_co.get("runs", [])):
                fail("this project's other coordinated attempt needs completion or reconciliation")
        record = {"id": run_id, "started_at": kt.now(), "agent": claim.get("agent"), "project_id": task.get("project"),
                  "unattended": True, "admission": "approved-todo", "events": [],
                  "_claim": claim_hash(kt, claim), "_proof": digest(proof["proof"])}
        co["runs"].append(record)
        require_current_kit(data)
        kt.hist(task, "Rook attempt started " + run_id)
        result.update(created=True, run_id=run_id, state="recorded", launch=True)
    try:
        kt.mutate(change, "Rook: record attempt")
    except Refused:
        # Only definite validation refusal is cleaned up. A lost response/transport
        # failure retains its proof, since the remote mutation may have succeeded.
        if proof.get("_created"):
            try:
                saved, _ = kt.load()
                recorded = any(r.get("id") == run_id and r.get("_proof") == digest(proof["proof"])
                               for t in saved.get("tasks", []) for r in (t.get("coordination") or {}).get("runs", []))
                if not recorded:
                    os.unlink(proof_path)
            except (Exception, SystemExit):
                pass  # cannot establish absence: retain proof and report the original refusal
        raise
    print(json.dumps(result))


def release_owned(kt, ref, generation=None):
    """Atomic runner cleanup; ordinary release intentionally has broader recovery semantics."""
    sid = session(kt)
    answer = {}
    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True
        task = kt.find(data, ref)
        claim = task.get("claim") or {}
        if not claim or claim.get("session_id") != sid or kt.is_placeholder_claim(claim):
            answer.update(released=False, reason="no matching claim; task unchanged")
            return
        if claim.get("attended"):
            fail("runner release requires an unattended claim; use an explicit attended finish/release path")
        if not isinstance(generation, str) or not re.fullmatch(r"[a-f0-9]{24}", generation):
            fail("runner release requires the expected claim generation captured when claiming")
        if claim.get("generation") != generation:
            answer.update(released=False, reason="claim generation changed; successor unchanged")
            return
        task["claim"] = None
        if task.get("coordination") is not None:
            require_current_kit(data)
        preserve = any(unresolved(r) for r in (task.get("coordination") or {}).get("runs", [])) or \
            task.get("column") in {"done", "pending-review"} or kt.open_waiting(task) or \
            any(PR_LINK.fullmatch(str(x.get("url", ""))) for x in task.get("links", []) if isinstance(x, dict))
        if not preserve and claim.get("unattended_approved") is True:
            kt.move_task_to_column(data, task, "todo")
        kt.hist(task, "runner released its exact claim")
        kt._MUT["after"].append(lambda d: kt.drop_claim_file(task["id"]))
        answer.update(released=True, column=task.get("column"))
    kt.mutate(change, "Runner: release exact claim")
    print(json.dumps(answer))


def event(kt, ref, run_id, proof_path, value, *, final=False):
    if not isinstance(value, dict):
        fail("event must be an object")
    allowed = {"id", "kind", "summary", "links", "coverage", "exit_code", "launch_state"}
    if set(value) - allowed:
        fail("event has unsupported fields")
    clean = {"id": text(value.get("id"), "event id", 128, required=True),
             "kind": text(value.get("kind"), "kind", 30, required=True),
             "summary": text(value.get("summary", ""), "summary", 400)}
    if not KEY.fullmatch(clean["id"]) or clean["kind"] not in ({"finished", "interrupted"} if final else PROGRESS):
        fail("invalid event id or event kind")
    links = value.get("links", [])
    if not isinstance(links, list) or len(links) > 4 or any(not isinstance(x, str) or not x.startswith("https://") or len(x) > 500
            or urllib.parse.urlsplit(x).username or urllib.parse.urlsplit(x).password or any(c in x for c in "\r\n\t") for x in links):
        fail("links must be at most four HTTPS references")
    clean["links"] = links
    coverage = value.get("coverage", "unavailable")
    if coverage not in {"metadata_only", "partial", "unavailable"}:
        fail("unsupported capture coverage")
    clean["coverage"] = coverage
    if final:
        clean["launch_state"] = value.get("launch_state", "may_have_launched")
        if clean["launch_state"] not in {"not_launched", "may_have_launched"}:
            fail("unsupported launch state")
    if "exit_code" in value:
        if type(value["exit_code"]) is not int or not 0 <= value["exit_code"] <= 255:
            fail("exit_code must be an integer from 0 to 255")
        clean["exit_code"] = value["exit_code"]
    safe_content(kt, clean)
    proof = receipt(proof_path, run_id)
    result = {}

    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True
        task = kt.find(data, ref)
        run = attempt(kt, data, task, run_id, proof, retiring=True)
        prior = ([run["terminal"]] if run.get("terminal") else []) + run["events"]
        existing = next((e for e in prior if e["id"] == clean["id"]), None)
        if existing:
            if existing["digest"] != digest(clean):
                fail("event id already has a different payload")
            result.update(created=False, task=view(kt, task, data=data))
            return
        if not final:
            attempt(kt, data, task, run_id, proof)
        if run.get("terminal"):
            fail("this attempt is already sealed")
        if not final:
            claim = own_running_claim(kt, data, task)
            if claim_hash(kt, claim) != run["_claim"]:
                fail("claim no longer belongs to this attempt")
            if len(run["events"]) >= MAX_EVENTS:
                fail("progress limit reached; the terminal receipt remains available")
        entry = {**clean, "digest": digest(clean), "at": kt.now()}
        require_current_kit(data)
        if clean["links"] and (final or clean["kind"] == "result_ready"):
            # Only the host holding this attempt's receipt can attest these links.
            # No inference from task column, old waits or arbitrary task PR links.
            run["result"] = {"links": clean["links"], "at": entry["at"], "event_id": clean["id"]}
        if final:
            run["terminal"] = entry
            claim = task.get("claim") or {}
            pending = task.get("column") in {"done", "pending-review"} or kt.open_waiting(task) or \
                any(PR_LINK.fullmatch(str(x.get("url", ""))) for x in task.get("links", []) if isinstance(x, dict))
            run["needs_reconciliation"] = bool(not run.get("result") and clean["launch_state"] != "not_launched")
            # Only remove this run's exact claim; never invoke ordinary release's stale/no-claim exceptions.
            if claim and claim_hash(kt, claim) == run["_claim"] and coordinate(task)["runs"][-1] is run:
                task["claim"] = None
                if not pending:
                    kt.move_task_to_column(data, task, "in-progress" if run["needs_reconciliation"] or run.get("result")
                                           or not run.get("unattended") or run.get("admission") != "approved-todo"
                                           or claim.get("unattended_approved") is not True or claim.get("attended") else "todo")
                kt._MUT["after"].append(lambda d: kt.drop_claim_file(task["id"]))
        else:
            run["events"].append(entry)
        kt.hist(task, "Rook " + clean["kind"] + ": " + (clean["summary"] or run_id))
        if clean["summary"] and (not final or run.get("needs_reconciliation")):
            kt.append_comment(task, "Rook: " + clean["summary"], kt.who_am_i())
        result.update(created=True, task=view(kt, task, data=data))
    kt.mutate(change, "Rook: " + clean["kind"])
    print(json.dumps(result, ensure_ascii=False))


def resolve(kt, args):
    """Explicit disposition after checking real effects; never called by automatic recovery."""
    if not args.confirmed:
        fail("resolution needs --confirmed after the owner authorises this exact disposition")
    note = text(args.note, "resolution note", 400, required=True)
    safe_content(kt, note)
    proof = receipt(args.receipt, args.run_id)
    result = {}
    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True
        task = kt.find(data, args.id)
        run = attempt(kt, data, task, args.run_id, proof, retiring=True)
        resolution = {"disposition": args.disposition, "note": note}
        if run.get("resolution"):
            if {k: run["resolution"][k] for k in resolution} != resolution:
                fail("attempt already has a different resolution")
            result.update(created=False, task=view(kt, task, data=data)); return
        if not run.get("terminal"):
            fail("seal the historical attempt before resolving its effects")
        if not run.get("needs_reconciliation") and args.disposition != "retry-safe":
            fail("this attempt has no unresolved effects")
        pending = task.get("column") in {"done", "pending-review"} or kt.open_waiting(task) or \
            any(PR_LINK.fullmatch(str(x.get("url", ""))) for x in task.get("links", []) if isinstance(x, dict))
        if args.disposition == "recorded-result":
            link = getattr(args, "result_link", None)
            known = [x.get("url") for x in task.get("links", []) if isinstance(x, dict)]
            attested = (run.get("result") or {}).get("links", [])
            if link:
                safe_content(kt, link)
                if link not in known or not link.startswith("https://") or urllib.parse.urlsplit(link).username or urllib.parse.urlsplit(link).password:
                    fail("record the verified result link on the task first")
                run["result"] = {"links": [link], "at": kt.now(), "attestation": "owner-confirmed resolution"}
            elif not any(url in known for url in attested):
                fail("record the verified run result first; select its task link with --result-link")
        run["resolution"] = {**resolution, "at": kt.now(), "by": kt.who_am_i()}
        require_current_kit(data)
        if args.disposition == "recorded-result" and task.get("column") == "todo" and not task.get("claim"):
            kt.move_task_to_column(data, task, "in-progress")
        if args.disposition == "retry-safe" and not pending and not task.get("claim") and run.get("admission") == "approved-todo":
            kt.move_task_to_column(data, task, "todo")
        kt.hist(task, "Rook attempt resolved: " + note)
        result.update(created=True, task=view(kt, task, data=data))
    kt.mutate(change, "Rook: resolve observed effects")
    print(json.dumps(result, ensure_ascii=False))


def parser(sub, callback):
    req = sub.add_parser("request-work", help="save one idempotent Rook request in Backlog; never approves or starts")
    req.set_defaults(f=callback, work_action="request")
    resolution = sub.add_parser("work-resolve", help="owner-authorised disposition of an uncertain attempt; never automatic")
    resolution.add_argument("id"); resolution.add_argument("--run-id", required=True); resolution.add_argument("--receipt", required=True)
    resolution.add_argument("--disposition", required=True, choices=("retry-safe", "recorded-result"))
    resolution.add_argument("--note", required=True); resolution.add_argument("--confirmed", action="store_true")
    resolution.add_argument("--result-link", help="owner-verified link already on this task, explicitly bound to this run")
    resolution.set_defaults(f=callback, work_action="resolve")
    release = sub.add_parser("work-release-owned", help="atomic runner cleanup: releases only this exact claim and preserves waits/results")
    release.add_argument("id")
    release.add_argument("--claim-generation", required=True, help="expected incarnation captured at claim, never read anew during cleanup")
    release.set_defaults(f=callback, work_action="release")
    for name, action in (("work-status", "status"), ("work-start", "start"), ("work-event", "event"), ("work-finish", "finish")):
        cmd = sub.add_parser(name, help="Rook durable task/run metadata; does not grant execution authority")
        cmd.add_argument("id")
        if action != "status":
            cmd.add_argument("--run-id", required=True)
            cmd.add_argument("--receipt", required=True, help="private host-only receipt; never pass to an agent")
        if action == "start":
            cmd.add_argument("--host-pid", type=int, help="owning runner PID, used only for orphan reconciliation")
        cmd.set_defaults(f=callback, work_action=action)


def command(kt, args):
    if kt.BACKEND != "github" and not kt.FILE:
        fail("this backend does not support the durable work contract")
    action = args.work_action
    if action == "status":
        return status(kt, args.id)
    if action == "release":
        return release_owned(kt, args.id, getattr(args, "claim_generation", None))
    if action == "resolve":
        return resolve(kt, args)
    if action == "start":
        return start(kt, args.id, args.run_id, args.receipt, getattr(args, "host_pid", None))
    raw = kt.sys.stdin.read(MAX_INPUT + 1)
    if len(raw.encode()) > MAX_INPUT:
        fail("input exceeds 16 KiB")
    try:
        value = json.loads(raw)
    except ValueError:
        fail("input must be one JSON object")
    if action == "request":
        return request(kt, value)
    return event(kt, args.id, args.run_id, args.receipt, value, final=action == "finish")
