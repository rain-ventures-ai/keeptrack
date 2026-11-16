"""Opt-in public research admission and receipt-bound atomic handover.

Uses Keeptrack's existing direct owner ask.approve boundary. It does not turn
generic connector confirmation, card text or a relayed answer into authority.
The research host must additionally retain its private admission proof; the
credential-free worker receives neither that proof nor a board checkout.
"""
import copy
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import urllib.parse

SCHEMA = "keeptrack.research/1"
EXECUTOR = "relay-research"
HASH = re.compile(r"sha256:[a-f0-9]{64}\Z")
PUBLIC_POLICY_FIELDS = {"v", "enabled", "board", "owner", "projects", "profile", "policy_digest", "approval_ttl"}
ACTION_BINDINGS = {"board", "owner", "project", "task_id", "approval_id", "answer_id", "content_hash", "policy_digest"}
ACTION_FIELDS = ACTION_BINDINGS | {"schema", "kind", "id", "proof", "issued_at", "expires_at", "mac"}
Refused = SystemExit  # The work loader supplies its typed validation refusal.


def fail(message):
    raise Refused("research: " + message)


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def policy(data, expected=None):
    value = (data.get("settings") or {}).get("rook_research")
    if not isinstance(value, dict) or set(value) != PUBLIC_POLICY_FIELDS or value.get("v") != 1 or value.get("enabled") is not True:
        fail("pilot is disabled or its public configuration is unsupported")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(value.get("board", ""))) or \
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", str(value.get("owner", ""))):
        fail("invalid board or owner identity")
    owner = (data.get("settings") or {}).get("kit_owner") or next((p.get("github") for p in data.get("people", []) if p.get("github")), None)
    if value["owner"] != owner or value.get("profile") != "public-research" or not HASH.fullmatch(str(value.get("policy_digest", ""))):
        fail("pilot owner/profile/policy is not the configured board owner")
    if not isinstance(value.get("projects"), list) or not 1 <= len(value["projects"]) <= 16 or \
            any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", p) for p in value["projects"]):
        fail("pilot projects must be canonical IDs")
    if type(value.get("approval_ttl")) is not int or not 60 <= value["approval_ttl"] <= 3600:
        fail("approval lifetime must be 60 to 3600 seconds")
    if expected is not None and expected != value["policy_digest"]:
        fail("board policy differs from the host's adopted policy")
    return value


def projection(data, task):
    """Input only: normal heartbeat, column and host progress changes do not change the brief."""
    p = policy(data)
    projects = [x for x in data.get("projects", []) if isinstance(x, dict) and x.get("id") == task.get("project")]
    if len(projects) != 1 or task.get("project") not in p["projects"]:
        fail("task is outside the pilot's canonical project")
    value = {"id": task.get("id"), "project": task.get("project"), "title": task.get("title", ""),
             "details": task.get("details", ""), "todos": copy.deepcopy(task.get("todos") or []),
             "links": copy.deepcopy(task.get("links") or []), "after": copy.deepcopy(task.get("after") or [])}
    if not isinstance(value["id"], str) or not re.fullmatch(r"t_[a-z0-9]{4,20}", value["id"]) or \
            not isinstance(value["title"], str) or not value["title"].strip() or len(value["title"]) > 160 or \
            not isinstance(value["details"], str) or len(value["details"]) > 2000:
        fail("research brief needs a supported task identity and bounded text")
    if not isinstance(value["todos"], list) or len(value["todos"]) > 20 or \
            not isinstance(value["links"], list) or not 1 <= len(value["links"]) <= 8 or \
            not isinstance(value["after"], list) or len(value["after"]) > 32:
        fail("research needs one to eight explicit public source links and a bounded checklist")
    for link in value["links"]:
        if not isinstance(link, dict) or not isinstance(link.get("url"), str) or len(link["url"]) > 2000:
            fail("invalid research source link")
        try:
            u = urllib.parse.urlsplit(link["url"])
            valid = u.scheme == "https" and u.hostname and not u.username and not u.password and u.port in (None, 443)
        except ValueError:
            valid = False
        if not valid or \
                any(c.isspace() or ord(c) < 32 for c in link["url"]):
            fail("sources must be credential-free HTTPS links; the host also checks their resolved addresses")
    if len(json.dumps(value, ensure_ascii=False).encode()) > 16384:
        fail("research brief exceeds 16 KiB")
    for todo in value["todos"]:
        if not isinstance(todo, dict) or not isinstance(todo.get("text"), str) or len(todo["text"]) > 300 or \
                type(todo.get("done")) is not bool:
            fail("checklist entries need bounded text and a boolean done flag")
    if any(not isinstance(i, str) or not re.fullmatch(r"t_[a-z0-9]{4,20}", i) for i in value["after"]):
        fail("dependencies need canonical task IDs")
    brief = value["title"] + ("\n\n" + value["details"] if value["details"] else "")
    if value["todos"]: brief += "\n\nChecklist:\n" + "\n".join(t["text"] for t in value["todos"])
    if len(brief.encode()) > 4000:
        fail("combined research brief and checklist exceed 4000 UTF-8 bytes")
    return value


def scope(data, task):
    p = policy(data)
    return {"schema": SCHEMA, "board": p["board"], "owner": p["owner"], "approval_ttl": p["approval_ttl"], "task": projection(data, task),
            "executor": EXECUTOR, "profile": p["profile"], "policy_digest": p["policy_digest"]}


def revoke_changed_inputs(before, after):
    """Native edits cannot restore a consumed grant by restoring its old input.

    Called on the existing mutation base after conflict rechecks/merge. New
    grants are created only by admission; this retires an existing identity.
    """
    old = {t.get("id"): t for t in before.get("tasks", []) if isinstance(t, dict)}
    for task in after.get("tasks", []):
        grant = ((task.get("coordination") or {}).get("research") or {}).get("admission")
        previous = old.get(task.get("id"))
        was = (((previous or {}).get("coordination") or {}).get("research") or {}).get("admission")
        if not isinstance(grant, dict) or not isinstance(was, dict) or grant.get("id") != was.get("id"):
            continue
        if was.get("active") is not True or task.get("column") not in {"todo", "in-progress"}:
            grant["active"] = False
        elif grant.get("active") is True:
            try:
                if scope(before, previous) != scope(after, task):
                    grant["active"] = False
            except SystemExit:
                grant["active"] = False


def proposal_input(data, task):
    spec = scope(data, task); hashed = digest(spec)
    return {"kind": "ask.approve", "title": "Hand public research to Rook", "decider": policy(data)["owner"],
            "source": {"kind": "other", "id": "rook.research:" + task["id"], "revision": hashed},
            "action_key": "rook.research:" + hashed, "work_key": "rook.research:" + task["id"],
            "reason": "Read public sources and publish one private report under the adopted pilot policy.",
            "change": {"question": "Hand this exact public-source research request to Rook?", "task": task["id"],
                       "subject": {"type": "other", "summary": "Read-only public research; no messages, purchases or repository changes."},
                       "content_hash": hashed}}


def _time(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        fail("approval has no valid timestamp")


def approved(kt, data, task, proposal_id, answer_id, expected_policy, *, allow_consumed=False):
    p = policy(data, expected_policy)
    if not re.fullmatch(r"r_[a-z0-9]{10}", str(proposal_id or "")) or not re.fullmatch(r"a_[a-f0-9]{10}", str(answer_id or "")):
        fail("approval and answer require full canonical identities")
    if not kt.FILE and kt.REPO != p["board"]:
        fail("pilot configuration names another board")
    item = kt.find_proposal(data, proposal_id)
    decision, change = item.get("decision") or {}, item.get("change") or {}
    want = proposal_input(data, task)
    kt.work_module().safe_content(kt, scope(data, task))
    if any(item.get(k) != want[k] for k in ("kind", "title", "decider", "action_key", "work_key", "reason")) or \
            change != want["change"] or (item.get("source") or {}).get("kind") != "other":
        fail("approval does not describe this exact Rook action")
    if item.get("kind") != "ask.approve" or item.get("status") != "answered" or item.get("decider") != p["owner"] or \
            decision.get("action") != "answer" or decision.get("id") != answer_id or \
            decision.get("by") != p["owner"] or decision.get("relayed") or \
            (decision.get("answer") or {}).get("approved") is not True:
        fail("a direct answer by the named owner to this exact approval is required")
    if change.get("task") != task["id"] or change.get("content_hash") != want["change"]["content_hash"] or \
            (item.get("source") or {}).get("id") != want["source"]["id"] or \
            (item.get("source") or {}).get("revision") != want["source"]["revision"]:
        fail("task, source, scope or policy changed after approval")
    consumed = decision.get("done")
    if consumed and not allow_consumed:
        fail("approval answer was already consumed")
    age = (_time(kt.now()) - _time(decision.get("at"))).total_seconds()
    if age < -5 or (not consumed and age > p["approval_ttl"]):
        fail("owner approval expired or has a future timestamp")
    return item, want["change"]["content_hash"]


def _private_receipt(path, create=None):
    path = Path(os.path.abspath(path)); parent = path.parent
    info = parent.lstat()
    if os.path.realpath(parent) != str(parent) or not stat.S_ISDIR(info.st_mode) or \
            info.st_uid != os.getuid() or info.st_mode & 0o077:
        fail("host admission receipt needs a private owned physical directory")
    if create is not None and not path.exists() and not path.is_symlink():
        fd, temporary = tempfile.mkstemp(prefix=".admission-", dir=parent)
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(create, out, allow_nan=False); out.flush(); os.fsync(out.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)  # publish complete bytes without replacing an existing proof
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
        handle = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(handle)
        finally: os.close(handle)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 8192:
            fail("admission receipt must be a private owned regular file")
        raw = source.read(8193)
    if len(raw) > 8192:
        fail("admission receipt is oversized")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("proof", ""))):
        fail("unsupported admission receipt")
    return value


def _approval_identity(item):
    d, c, s = item.get("decision") or {}, item.get("change") or {}, item.get("source") or {}
    return {"id": item.get("id"), "kind": item.get("kind"), "status": item.get("status"), "decider": item.get("decider"),
            "title": item.get("title"), "reason": item.get("reason"), "action_key": item.get("action_key"), "work_key": item.get("work_key"),
            "source": {k: s.get(k, "") for k in ("kind", "id", "revision", "title", "date", "url")},
            "change": c,
            "answer": {k: d.get(k) for k in ("action", "id", "by", "at", "answer", "relayed")}}


def owner_action_key(path):
    key = _private_receipt(path)
    if set(key) != {"schema", "kind", "proof"} or key.get("kind") != "owner-action-key":
        fail("invalid private owner-action key")
    return bytes.fromhex(key["proof"])


def action_mac(value, key):
    body = {k: v for k, v in value.items() if k != "mac"}
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(), hashlib.sha256).hexdigest()


def verify_owner_action(path, key_path, expected, now, ttl, *, allow_expired=False):
    """The trusted host pins this key/path outside all board/worker mounts.

    A Git push or arbitrary owner-labelled board record is never this receipt.
    An agent with the owner's host filesystem/signing key is outside this boundary.
    """
    if set(expected) != ACTION_BINDINGS:
        fail("invalid owner-action binding")
    value = _private_receipt(path)
    if set(value) != ACTION_FIELDS or value.get("kind") != "owner-action" or \
            not re.fullmatch(r"oa_[a-f0-9]{24}", str(value.get("id", ""))) or \
            not hmac.compare_digest(str(value.get("mac", "")), action_mac(value, owner_action_key(key_path))):
        fail("owner-action signature is invalid")
    if any(value.get(k) != v for k, v in expected.items()):
        fail("owner action belongs to another request or adopted configuration")
    issued, expiry, current = _time(value["issued_at"]), _time(value["expires_at"]), _time(now)
    if not 0 < (expiry - issued).total_seconds() <= ttl or (issued - current).total_seconds() > 5 or \
            (not allow_expired and current > expiry):
        fail("owner action is expired or outside its admission window")
    return {"provider": "owner-action", "id": value["id"], "digest": digest(value)}


def issue_owner_action(path, key_path, expected, now, ttl):
    """Called only after the owner endpoint authenticates its separate capability."""
    if set(expected) != ACTION_BINDINGS or type(ttl) is not int or not 60 <= ttl <= 3600:
        fail("invalid owner-action scope or lifetime")
    if not Path(path).exists() and not Path(path).is_symlink():
        value = {"schema": SCHEMA, "kind": "owner-action", "id": "oa_" + secrets.token_hex(12), "proof": secrets.token_hex(32),
                 **expected, "issued_at": now, "expires_at": (_time(now) + dt.timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")}
        value["mac"] = action_mac(value, owner_action_key(key_path))
        _private_receipt(path, value)
    return verify_owner_action(path, key_path, expected, now, ttl)


def owner_push(kt, item, p):
    # Unused legacy diagnostic. Admission never calls it: Git activity is not
    # proof of a particular owner action and grants no research authority.
    """Optional Git audit only: a push is NOT authority for a specific action.

    The button makes one commit. Its exact proposal answer must be new in the
    owner's normal push, not merely present in an unrelated later owner push.
    Missing/lagging activity or more history than the bounded page means wait.
    File mode is an explicitly offline fixture boundary, never a live pilot.
    """
    if kt.FILE:
        return {"provider": "offline-fixture"}
    if kt.github_api_base() != "https://api.github.com":
        fail("owner provenance currently requires github.com")
    if not re.fullmatch(r"r_[a-z0-9]{10}", str(item.get("id", ""))):
        fail("approval requires its full canonical proposal ID")
    def read(path, absent=False):
        rc, out, err = kt.http("GET", path, retries=0)
        if rc:
            # Only a verified 404 JSON response may stand for a previously absent file.
            missing = str(err).startswith("HTTP 404:")
            if absent and missing: return None
            fail("GitHub owner-action provenance is unavailable; nothing admitted")
        if len(out.encode()) > 262144: fail("GitHub provenance response exceeds its bound")
        try: return json.loads(out)
        except ValueError: fail("invalid GitHub owner-action provenance")
    prefix = "repos/" + p["board"]
    directory = kt.PATH.rpartition("/")[0]
    path = (directory + "/" if directory else "") + "proposals/" + item["id"] + ".json"
    q = urllib.parse.urlencode({"path": path, "sha": kt.BRANCH, "per_page": 1})
    commits = read(prefix + "/commits?" + q)
    commit = commits[0].get("sha") if isinstance(commits, list) and len(commits) == 1 else None
    if not re.fullmatch(r"[a-f0-9]{40}", str(commit or "")):
        fail("approval has no single current GitHub commit")
    q = urllib.parse.urlencode({"ref": "refs/heads/" + kt.BRANCH, "actor": p["owner"], "activity_type": "push", "time_period": "day", "per_page": 100})
    rows = read(prefix + "/activity?" + q)
    if not isinstance(rows, list) or len(rows) > 100: fail("invalid GitHub activity response")
    matches = [r for r in rows if isinstance(r, dict) and r.get("after") == commit and r.get("ref") == "refs/heads/" + kt.BRANCH
               and isinstance(r.get("actor"), dict) and r["actor"].get("login") == p["owner"] and r.get("activity_type") == "push"]
    if len(matches) != 1: fail("the exact approval commit has no verified normal owner push; wait for GitHub activity")
    row = matches[0]
    before = row.get("before")
    if not re.fullmatch(r"[a-f0-9]{40}", str(before or "")) or before == "0" * 40:
        fail("owner push has no verifiable preceding board state")
    age = (_time(kt.now()) - _time(row.get("timestamp"))).total_seconds()
    if age < -5 or age > p["approval_ttl"]: fail("owner push is outside the admission window")
    def at(ref, absent=False):
        response = read(prefix + "/contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + ref, absent=absent)
        if response is None: return None
        if not isinstance(response, dict) or response.get("type") != "file" or response.get("encoding") != "base64" or \
                type(response.get("size")) is not int or response["size"] > 32768:
            fail("unsupported proposal provenance object")
        try:
            raw = base64.b64decode(response["content"].encode(), validate=False)
            if len(raw) > 32768: fail("proposal provenance object is oversized")
            value = json.loads(raw)
        except (KeyError, ValueError, UnicodeError): fail("invalid proposal provenance object")
        if not isinstance(value, dict): fail("invalid proposal provenance object")
        return value
    current, previous = at(commit), at(before, absent=True)
    if _approval_identity(current) != _approval_identity(item) or \
            (previous and (previous.get("decision") or {}).get("id") == (item.get("decision") or {}).get("id")):
        fail("owner push did not introduce this exact approval answer")
    return {"provider": "github-activity", "commit": commit, "before": before, "actor": p["owner"], "push_id": row.get("id")}


def admit(kt, work, args):
    data, _ = kt.load(); task = kt.find(data, args.id)
    item, hashed = approved(kt, data, task, args.approval, args.answer, args.policy_digest, allow_consumed=True)
    action_path, key_path = getattr(args, "owner_action_receipt", None), getattr(args, "owner_action_key", None)
    if Path(args.admission_receipt).exists() or Path(args.admission_receipt).is_symlink():
        private = _private_receipt(args.admission_receipt)
    else:
        if not kt.FILE:
            kt.require_review_storage(data)
        if action_path and key_path:
            p = policy(data, args.policy_digest)
            expected = {"board": p["board"], "owner": p["owner"], "project": task["project"], "task_id": task["id"],
                        "approval_id": args.approval, "answer_id": args.answer, "content_hash": hashed, "policy_digest": args.policy_digest}
            provenance = verify_owner_action(action_path, key_path, expected, kt.now(), p["approval_ttl"])
        elif kt.FILE:
            provenance = {"provider": "offline-fixture"}
        else:
            fail("an independently authenticated private owner-action receipt is required; Git pushes are not approval")
        private = _private_receipt(args.admission_receipt, {"schema": SCHEMA, "task_id": task["id"],
            "project_id": task["project"],
            "admitted_at": kt.now(),
            "approval_id": args.approval, "answer_id": args.answer, "content_hash": hashed,
            "policy_digest": args.policy_digest, "proof": secrets.token_hex(32), "provenance": provenance,
            "approval_digest": digest(_approval_identity(item))})
    answer = {}
    def change(current):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True; answer.clear()
        card = kt.find(current, args.id); co = work.coordinate(card)
        existing = (co.get("research") or {}).get("admission") or {}
        if existing.get("answer_id") == args.answer:
            verify(kt, current, card, private, args.policy_digest)
            answer.update(created=False, task=work.view(kt, card, data=current)); return
        if (not kt.FILE or (private.get("provenance") or {}).get("provider") == "owner-action") and (not action_path or not key_path):
            fail("the signed private owner-action receipt and configured key are required for every unconsumed admission")
        prop, content_hash = approved(kt, current, card, args.approval, args.answer, args.policy_digest)
        if action_path and key_path:
            p = policy(current, args.policy_digest)
            expected = {"board": p["board"], "owner": p["owner"], "project": card["project"], "task_id": card["id"],
                        "approval_id": args.approval, "answer_id": args.answer, "content_hash": content_hash, "policy_digest": args.policy_digest}
            if verify_owner_action(action_path, key_path, expected, kt.now(), p["approval_ttl"]) != private.get("provenance"):
                fail("owner action changed during admission")
        request = (co.get("research") or {}).get("request")
        if request and (request.get("approval_id") != args.approval or request.get("answer_id") != args.answer):
            fail("a newer button action supersedes this admission")
        if private.get("approval_digest") != digest(_approval_identity(prop)):
            fail("approval changed after its authenticated owner action")
        if any(private.get(k) != v for k, v in {"task_id": card["id"], "approval_id": args.approval,
                "answer_id": args.answer, "content_hash": content_hash, "policy_digest": args.policy_digest}.items()):
            fail("host admission receipt belongs to another action")
        if card.get("column") != "backlog" or card.get("claim") or kt.open_waiting(card) or any(work.unresolved(r) for r in co["runs"]):
            fail("only an unclaimed, unblocked Backlog task may be admitted")
        after = kt.after_links(current, card, None)
        if any(x.get("state") != "done" for x in after):
            fail("task has unfinished dependencies")
        owner = policy(current, args.policy_digest)["owner"]
        if owner not in card.setdefault("assignees", []):
            card["assignees"].append(owner)
        previous_note = (co.get("research") or {}).get("prelaunch_note") or {}
        if previous_note.get("label_added") and "needs-human" in card.get("labels", []):
            card["labels"].remove("needs-human")
        co["executor"] = EXECUTOR
        co["research"] = {"v": 1, "admission": {"id": "ra_" + secrets.token_hex(12), "active": True,
            "approval_id": args.approval, "answer_id": args.answer, "content_hash": content_hash,
            "policy_digest": args.policy_digest, "at": private["admitted_at"], "_proof": work.digest(private["proof"])},
            "current": {"done": "Owner admitted this public research request.", "remaining": "Host checks and research.", "next_actor": "rook"}}
        prop["decision"]["done"] = {"at": kt.now(), "by": kt.who_am_i(), "acted": True,
                                      "research_admission": co["research"]["admission"]["id"]}
        kt.move_task_to_column(current, card, "todo"); work.require_current_kit(current)
        current.setdefault("settings", {})["min_kit"] = max(126, current["settings"].get("min_kit", 0))
        kt.hist(card, "Rook research admitted from the owner's exact approval")
        answer.update(created=True, task=work.view(kt, card, data=current))
    kt.mutate(change, "Rook: admit public research")
    print(json.dumps(answer, ensure_ascii=False))


def verify(kt, data, task, private, expected_policy):
    record = ((task.get("coordination") or {}).get("research") or {}).get("admission") or {}
    _time(private.get("admitted_at"))
    if record.get("at") != private["admitted_at"]:
        fail("admission clock differs from the private host receipt")
    if not kt.FILE and (private.get("provenance") or {}).get("provider") != "owner-action":
        fail("this host receipt has no authenticated owner-action provenance")
    if task.get("id") != private.get("task_id") or record.get("active") is not True or \
            record.get("answer_id") != private.get("answer_id") or record.get("approval_id") != private.get("approval_id") or \
            record.get("content_hash") != private.get("content_hash") or record.get("policy_digest") != expected_policy or \
            not secrets.compare_digest(str(record.get("_proof", "")),
                                       hashlib.sha256(json.dumps(private["proof"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()):
        fail("research admission is absent, withdrawn or does not match the host receipt")
    check_active(kt, data, task)
    item, _ = approved(kt, data, task, private["approval_id"], private["answer_id"], expected_policy, allow_consumed=True)
    if private.get("approval_digest") != digest(_approval_identity(item)):
        fail("approval changed after its authenticated owner action")
    return record


def check_active(kt, data, task):
    """Recheck the existing consumed owner grant on renewal; does not grant a new claim."""
    record = ((task.get("coordination") or {}).get("research") or {}).get("admission") or {}
    if record.get("active") is not True or task.get("column") not in {"todo", "in-progress"}:
        fail("research approval was withdrawn")
    prop, hashed = approved(kt, data, task, record.get("approval_id"), record.get("answer_id"),
                            record.get("policy_digest"), allow_consumed=True)
    done = (prop.get("decision") or {}).get("done") or {}
    if done.get("research_admission") != record.get("id") or hashed != record.get("content_hash"):
        fail("approval was not consumed by this research admission")
    return record


def handover(kt, work, args, value):
    allowed = {"artifact", "current", "outcome"}
    if not isinstance(value, dict) or set(value) != allowed or value.get("outcome") not in {"pending_review", "complete"}:
        fail("handover requires artifact, current and a supported outcome")
    artifact, current = value["artifact"], value["current"]
    if not isinstance(artifact, dict) or set(artifact) != {"url", "sha256", "key"} or \
            not isinstance(artifact.get("url"), str) or len(artifact["url"]) > 500 or \
            not re.fullmatch(r"[a-f0-9]{64}", str(artifact.get("sha256", ""))) or \
            not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", str(artifact.get("key", ""))):
        fail("artifact requires one bounded version URL, content digest and publication key")
    url = urllib.parse.urlsplit(artifact["url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or any(c.isspace() for c in artifact["url"]):
        fail("artifact requires a credential-free HTTPS version URL")
    if not isinstance(current, dict) or set(current) - {"done", "decisions", "remaining", "next_actor"} or \
            current.get("next_actor") not in {"owner", "rook", "none"} or \
            any(not isinstance(x, str) for x in current.values()) or len(json.dumps(current, ensure_ascii=False).encode()) > 1024:
        fail("Current state must be bounded host-written text of at most 1 KiB")
    work.safe_content(kt, value)
    private = _private_receipt(args.admission_receipt)
    proof = work.receipt(args.receipt, args.run_id)
    payload_hash = digest(value); answer = {}
    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True; answer.clear()
        task = kt.find(data, args.id); co = work.coordinate(task)
        run = work.attempt(kt, data, task, args.run_id, proof)
        prior = run.get("research_handover")
        if prior:
            sealed_handover(task, run, proof)
            if prior.get("digest") != payload_hash:
                fail("this run was handed over with different evidence")
            answer.update(created=False, task=work.view(kt, task, data=data)); return
        verify(kt, data, task, private, args.policy_digest)
        if co.get("executor") != EXECUTOR or run.get("terminal") or run.get("needs_reconciliation"):
            fail("only the active, unheld research run may hand over")
        claim = work.own_running_claim(kt, data, task)
        if work.claim_hash(kt, claim) != run.get("_claim"):
            fail("a newer claim supersedes this report")
        if value["outcome"] == "complete" and (not args.informational or current.get("next_actor") != "none" or
                current.get("remaining", "").strip() or any(not t.get("done") for t in task.get("todos", []))):
            fail("completion requires the host's adopted informational rule and no remaining actor")
        ts = kt.now()
        run["result"] = {"links": [artifact["url"]], "at": ts, "event_id": "research-handover"}
        run["terminal"] = {"id": "research-handover", "kind": "finished", "at": ts, "digest": payload_hash,
                           "launch_state": "may_have_launched", "coverage": "metadata_only", "exit_code": 0}
        run["needs_reconciliation"] = False
        run["research_handover"] = {"digest": payload_hash, "artifact": copy.deepcopy(artifact), "current": copy.deepcopy(current), "outcome": value["outcome"]}
        run["_research_seal"] = handover_seal(task["id"], run["id"], payload_hash, proof)
        co["research"]["current"] = copy.deepcopy(current)
        co["research"]["artifact"] = copy.deepcopy(artifact)
        task["claim"] = None
        kt.move_task_to_column(data, task, "done" if value["outcome"] == "complete" else "pending-review")
        kt._MUT["after"].append(lambda d: kt.drop_claim_file(task["id"]))
        kt.hist(task, "Rook research report ready; details are in the linked versioned artifact")
        answer.update(created=True, task=work.view(kt, task, data=data))
    kt.mutate(change, "Rook: hand over research outcome")
    print(json.dumps(answer, ensure_ascii=False))


def handover_seal(task_id, run_id, payload_hash, proof):
    return hmac.new(bytes.fromhex(proof["proof"]), json.dumps([task_id, run_id, payload_hash], separators=(",", ":")).encode(), hashlib.sha256).hexdigest()


def read_failed(kt, work, args):
    """Idempotent known failure before the model boundary; never resolves unknown effects."""
    private = _private_receipt(args.admission_receipt)
    proof = work.receipt(args.receipt, args.run_id)
    payload_hash = digest({"kind": "research-read-failed", "reason": "source_unavailable"})
    seal = handover_seal(private["task_id"], args.run_id, payload_hash, proof)
    answer = {}
    def change(data):
        kt._MUT["recheck"] = kt._MUT["rerun"] = True; answer.clear()
        task = kt.find(data, args.id); co = work.coordinate(task)
        run = work.attempt(kt, data, task, args.run_id, proof, retiring=True)
        grant = (co.get("research") or {}).get("admission") or {}
        if task["id"] != private.get("task_id") or grant.get("policy_digest") != args.policy_digest or \
                grant.get("answer_id") != private.get("answer_id") or run.get("research_admission") != grant.get("id"):
            fail("read failure belongs to another research admission")
        if run.get("research_read_failure"):
            if not hmac.compare_digest(str(run.get("_research_read_failure_seal", "")), seal) or \
                    (run.get("terminal") or {}).get("id") != "research-read-failed" or run.get("needs_reconciliation"):
                fail("saved read failure has no valid host seal")
            answer.update(created=False, task=work.view(kt, task, data=data)); return
        verify(kt, data, task, private, args.policy_digest)
        if co.get("executor") != EXECUTOR or run.get("terminal") or run.get("needs_reconciliation") or run.get("result"):
            fail("read failure requires an active research run with no recorded effect")
        claim = work.own_running_claim(kt, data, task)
        if work.claim_hash(kt, claim) != run.get("_claim"):
            fail("a newer claim supersedes this read failure")
        run["terminal"] = {"id": "research-read-failed", "kind": "interrupted", "at": kt.now(),
                           "launch_state": "not_launched", "coverage": "metadata_only", "exit_code": 1}
        run["needs_reconciliation"] = False
        run["research_read_failure"] = {"reason": "source_unavailable"}
        run["_research_read_failure_seal"] = seal
        task["claim"] = None; grant["active"] = False
        co["research"]["current"] = {"done": "Research stopped before the model worker launched.",
            "remaining": "Check source availability or hand this request to Rook again when ready.", "next_actor": "owner"}
        added = "needs-human" not in task.setdefault("labels", [])
        if added:
            task["labels"].append("needs-human"); kt.hist(task, "labels: needs-human")
        co["research"]["prelaunch_note"] = {"reason": "source_unavailable", "label_added": added}
        kt.move_task_to_column(data, task, "backlog")
        kt._MUT["after"].append(lambda d: kt.drop_claim_file(task["id"]))
        kt.hist(task, "Rook research stopped before model launch; a fresh owner action is needed")
        answer.update(created=True, task=work.view(kt, task, data=data))
    kt.mutate(change, "Rook: record known research read failure")
    print(json.dumps(answer, ensure_ascii=False))


def sealed_handover(task, run, proof):
    saved = run.get("research_handover") or {}
    payload_hash = digest({k: saved.get(k) for k in ("artifact", "current", "outcome")})
    if saved.get("digest") != payload_hash or not hmac.compare_digest(str(run.get("_research_seal", "")),
            handover_seal(task["id"], run["id"], payload_hash, proof)):
        fail("canonical research outcome has no valid host seal; retain the receipt and reconcile")
    return saved


def parser(sub, callback):
    p = sub.add_parser("work-research-read-failed", help="host-only known source read failure before the model call")
    p.add_argument("id"); p.add_argument("--run-id", required=True); p.add_argument("--receipt", required=True)
    p.add_argument("--admission-receipt", required=True); p.add_argument("--policy-digest", required=True)
    p.set_defaults(f=callback, work_action="research-read-failed")
    p = sub.add_parser("work-research-note", help="host-only bounded prelaunch wait or refusal; never worker-supplied prose")
    p.add_argument("id"); p.add_argument("--admission-receipt", required=True); p.add_argument("--policy-digest", required=True)
    p.add_argument("--reason", choices=("source_unavailable", "source_rejected", "admission_expired", "host_unavailable"), required=True)
    p.set_defaults(f=callback, work_action="research-note")
    p = sub.add_parser("work-research-reconcile", help="authenticate a saved research outcome with its private run receipt")
    p.add_argument("id"); p.add_argument("--run-id", required=True); p.add_argument("--receipt", required=True)
    p.set_defaults(f=callback, work_action="research-reconcile")
    p = sub.add_parser("work-research-retire", help="retire a host-attested owner resolution; never infer it from board flags")
    p.add_argument("id"); p.add_argument("--run-id", required=True); p.add_argument("--receipt", required=True)
    p.set_defaults(f=callback, work_action="research-retire")
    p = sub.add_parser("work-research-candidates", help="read the current opted-in project's research requests; no queue or admission")
    p.add_argument("--project", required=True); p.set_defaults(f=callback, work_action="research-candidates")
    p = sub.add_parser("watch-poll", help="one read-only watch snapshot diff; cursor is not authority or an event log")
    p.add_argument("--project", required=True); p.set_defaults(f=callback, work_action="watch-poll")
    for name in ("snapshot", "draft", "admit", "check", "handover"):
        p = sub.add_parser("work-research-" + name, help="disabled-by-default read-only public research pilot")
        p.add_argument("id"); p.set_defaults(f=callback, work_action="research-" + name)
        if name not in {"draft", "snapshot"}:
            p.add_argument("--admission-receipt", required=True)
            p.add_argument("--policy-digest", required=True)
        if name == "admit":
            p.add_argument("--approval", required=True); p.add_argument("--answer", required=True)
            p.add_argument("--owner-action-receipt"); p.add_argument("--owner-action-key")
        if name == "handover":
            p.add_argument("--run-id", required=True); p.add_argument("--receipt", required=True)
            p.add_argument("--informational", action="store_true")


def watch_projection_bound(kt, task):
    """Refuse oversized input before watch hashing/list construction, not afterwards."""
    nodes, chars = 0, 0
    def visit(value, depth=0):
        nonlocal nodes, chars
        nodes += 1
        if depth > 12 or nodes > 16384:
            fail("watch card exceeds the pilot projection bound; move detailed activity to linked run logs")
        if isinstance(value, str):
            chars += len(value)
            if chars > 131072:
                fail("watch card exceeds the pilot projection text bound")
        elif isinstance(value, (list, dict)):
            if len(value) > 4096:
                fail("watch card exceeds the pilot activity bound; archive detailed activity first")
            if isinstance(value, dict):
                for key, item in value.items():
                    visit(key, depth + 1); visit(item, depth + 1)
            else:
                for item in value:
                    visit(item, depth + 1)
    keys = set(kt.WATCH_FIELDS) | {"claim", "waiting", "todos", "comments", "history", "coordination"}
    for key in keys:
        visit(task.get(key))


def watch_poll(kt, args):
    """Transport for the existing watch projection, not a second event mechanism.

    The client carries an untrusted bounded snapshot. It can invent its own old
    state, but this read-only call cannot grant admission or execute anything.
    Missed intermediate transitions require reconciliation against work-status.
    """
    raw = kt.sys.stdin.read(196609)
    if len(raw.encode()) > 196608: fail("watch cursor input is oversized")
    try:
        cursor = json.loads(raw) if raw.strip() else None
    except ValueError:
        fail("watch cursor input must be a JSON string or null")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 180000):
        fail("invalid watch cursor")
    data, _ = kt.load()
    project = kt.find_project(data, args.project)["id"]
    bound = {"v": 1, "board": kt._current_board(), "project": project}
    today = kt.board_today(data).isoformat()
    chosen = []
    for task in data.get("tasks") or []:
        if isinstance(task, dict) and task.get("id") and task.get("project") == project:
            chosen.append(task)
            if len(chosen) > 256:
                fail("watch project exceeds the pilot cursor bound; use a smaller project")
    # Project before hashing; no unrelated cards or global Review Inbox work.
    current = {"cards": {}, "proposals": {}}
    size = len(json.dumps({"scope": bound, "snapshot": current}, separators=(",", ":"), ensure_ascii=False).encode())
    for task in chosen:
        watch_projection_bound(kt, task)
        entry = kt.watch_entry(data, task, today, True)
        fragment = json.dumps({task["id"]: entry}, separators=(",", ":"), ensure_ascii=False).encode()
        size += len(fragment) - 2 + bool(current["cards"])
        if size > 131072:
            fail("watch project exceeds the pilot cursor bound; use a smaller project")
        current["cards"][task["id"]] = entry
    old = None
    if cursor:
        try:
            decoded = base64.b64decode(cursor.encode(), altchars=b"-_", validate=True)
            prior = json.loads(decoded)
        except (ValueError, UnicodeError):
            fail("invalid watch cursor encoding")
        if not isinstance(prior, dict) or set(prior) != {"scope", "snapshot"} or prior["scope"] != bound:
            fail("watch cursor belongs to another board, project or version")
        old = prior["snapshot"]
        if not isinstance(old, dict) or set(old) != {"cards", "proposals"} or old["proposals"] != {} or \
                not isinstance(old["cards"], dict) or len(old["cards"]) > 256:
            fail("invalid watch snapshot")
        # Exact public schema. Reject rather than round-trip unknown/private keys.
        template = kt.watch_entry(data, {"id": "t_cursor"}, today, True)
        for tid, entry in old["cards"].items():
            if not isinstance(tid, str) or not re.fullmatch(r"t_[a-z0-9]{4,20}", tid) or not isinstance(entry, dict) or set(entry) != set(template):
                fail("invalid watch entry")
            if entry.get("m") is not True or any(type(entry[k]) is not type(v) for k, v in template.items() if k not in {"num", "claim", "wait"}):
                fail("invalid watch entry fields")
            if entry["num"] is not None and type(entry["num"]) is not int or \
                    entry["claim"] is not None and (not isinstance(entry["claim"], str) or entry["claim"] not in {"running", "done", "blocked", "stale", "stuck"}) or \
                    entry["wait"] is not None and not isinstance(entry["wait"], str):
                fail("invalid watch entry state")
            if any(not isinstance(x, str) for x in entry["comments"]) or \
                    any(not isinstance(x, list) or len(x) != 3 or not isinstance(x[0], str) or type(x[1]) is not bool or not isinstance(x[2], str) for x in entry["todos"]):
                fail("invalid watch entry lists")
            if set(entry["fields"]) != set(kt.WATCH_FIELDS) or set(entry["research"]) != {"request", "admission", "current"} or \
                    any(not isinstance(v, str) or (v and not re.fullmatch(r"[a-f0-9]{12}", v)) for v in list(entry["fields"].values()) + list(entry["research"].values())) or \
                    any(not re.fullmatch(r"[a-f0-9]{12}", str(k)) or not isinstance(v, str) or v not in {"running", "finished", "held", "resolved"} for k, v in entry["coord"].items()):
                fail("invalid watch entry hashes")
    payload = json.dumps({"scope": bound, "snapshot": current}, separators=(",", ":"), ensure_ascii=False).encode()
    if len(current["cards"]) > 256 or len(payload) > 131072:
        fail("watch project exceeds the pilot cursor bound; use a smaller project")
    token = base64.urlsafe_b64encode(payload).decode()
    events = kt.watch_events(old, current, data, me="") if old is not None else []
    print(json.dumps({"events": events, "cursor": token, "baseline": old is None, "semantics": "snapshot-diff"}, ensure_ascii=False))


def command(kt, work, args):
    action = args.work_action.removeprefix("research-")
    if action == "read-failed":
        return read_failed(kt, work, args)
    if action == "note":
        private = _private_receipt(args.admission_receipt); result = {}
        owner = args.reason in {"source_rejected", "admission_expired"}
        def change(data):
            kt._MUT["recheck"] = kt._MUT["rerun"] = True; result.clear()
            task = kt.find(data, args.id); co = work.coordinate(task)
            verify(kt, data, task, private, args.policy_digest)
            if task.get("claim") or any(work.unresolved(r) for r in co["runs"]):
                fail("prelaunch note cannot replace an active or unresolved attempt")
            text = {"source_unavailable": "A public source is temporarily unavailable; Rook can retry within the admission window.",
                    "source_rejected": "Use public HTTPS source links, then hand this request to Rook again.",
                    "admission_expired": "The run window ended before launch. Hand this request to Rook again if it is still wanted.",
                    "host_unavailable": "Configured research execution is not available yet; no worker started. Rook will recheck."}[args.reason]
            current = {"done": "Owner request saved; no research worker launched.", "remaining": text, "next_actor": "owner" if owner else "rook"}
            if co["research"].get("current") != current:
                co["research"]["current"] = current
                kt.hist(task, "Rook research needs owner input before launch" if owner else "Rook research waiting before launch")
            if owner:
                co["research"]["admission"]["active"] = False
                kt.move_task_to_column(data, task, "backlog")
                added = "needs-human" not in task.setdefault("labels", [])
                if added:
                    task["labels"].append("needs-human"); kt.hist(task, "labels: needs-human")
                co["research"]["prelaunch_note"] = {"reason": args.reason, "label_added": added}
            result.update(task=work.view(kt, task, data=data))
        kt.mutate(change, "Rook: research prelaunch status")
        print(json.dumps(result, ensure_ascii=False)); return
    if action == "reconcile":
        data, _ = kt.load(); task = kt.find(data, args.id)
        proof = work.receipt(args.receipt, args.run_id)
        run = work.attempt(kt, data, task, args.run_id, proof, retiring=True)
        saved = sealed_handover(task, run, proof) if run.get("research_handover") else None
        print(json.dumps({"task": work.view(kt, task, data=data), "run": work.public(run), "handover": saved}, ensure_ascii=False))
        return
    if action == "candidates":
        data, _ = kt.load(); p = policy(data)
        project = kt.find_project(data, args.project)["id"]
        if project not in p["projects"]: fail("project is outside the research pilot")
        candidates, actions = [], {}
        for t in data.get("tasks", []):
            if not isinstance(t, dict) or not re.fullmatch(r"t_[a-z0-9]{4,20}", str(t.get("id", ""))): continue
            co = t.get("coordination") if isinstance(t.get("coordination"), dict) else {}
            r = co.get("research") if isinstance(co.get("research"), dict) else {}
            request = r.get("request") if isinstance(r.get("request"), dict) else {}
            grant = r.get("admission") if isinstance(r.get("admission"), dict) else {}
            runs = co.get("runs") if isinstance(co.get("runs"), list) else []
            if t.get("project") == project and (request and t.get("column") == "backlog" or
                    grant.get("active") is True or
                    co.get("executor") == EXECUTOR and any(work.unresolved(x) for x in runs if isinstance(x, dict))):
                candidates.append(t["id"])
                if len(candidates) > 256: fail("too many research candidates for this pilot")
                if request and t.get("column") == "backlog" and request.get("answer_id") != grant.get("answer_id"):
                    try:
                        current = scope(data, t); work.safe_content(kt, current)
                        if request.get("content_hash") == digest(current):
                            actions[t["id"]] = {key: request.get(key) for key in ("approval_id", "answer_id", "content_hash")}
                    except SystemExit:
                        pass  # Invalid/stale requests are data, not admission candidates.
        if len(candidates) > 256: fail("too many research candidates for this pilot")
        print(json.dumps({"schema": SCHEMA, "tasks": sorted(candidates), "actions": actions}))
        return
    if action == "admit":
        return admit(kt, work, args)
    if action == "retire":
        proof = work.receipt(args.receipt, args.run_id); result = {}
        def retire(data):
            kt._MUT["recheck"] = kt._MUT["rerun"] = True
            task = kt.find(data, args.id); run = work.attempt(kt, data, task, args.run_id, proof, retiring=True)
            resolution = run.get("resolution")
            if not run.get("terminal") or not isinstance(resolution, dict) or \
                    (proof.get("owner_resolution") or {}).get("digest") != digest(resolution).removeprefix("sha256:"):
                fail("a checked private owner resolution is required before retiring research")
            co = work.coordinate(task); grant = (co.get("research") or {}).get("admission") or {}
            if not run.get("research_admission") or grant.get("id") != run["research_admission"] or task.get("claim") or \
                    any(work.unresolved(r) for r in co["runs"]):
                fail("cannot retire a successor, claimed task or unresolved research attempt")
            grant["active"] = False
            if task.get("column") not in {"done", "pending-review"}:
                kt.move_task_to_column(data, task, "backlog")
                co["research"]["current"] = {"done": "Owner checked and retired the interrupted attempt.",
                    "remaining": "A fresh owner action is needed to research this request again.", "next_actor": "owner"}
            result.update(retired=True, run_id=args.run_id)
        kt.mutate(retire, "Rook: retire checked research resolution")
        print(json.dumps(result)); return
    if action == "handover":
        raw = kt.sys.stdin.read(16385)
        if len(raw.encode()) > 16384: fail("handover exceeds 16 KiB")
        return handover(kt, work, args, json.loads(raw))
    data, _ = kt.load(); task = kt.find(data, args.id)
    if action == "snapshot":
        spec = None
        try:
            spec = scope(data, task)
            work.safe_content(kt, spec)
        except SystemExit:
            spec = None  # retain recovery identity, never the rejected input
        print(json.dumps({"schema": SCHEMA, "task": work.view(kt, task, data=data), "scope": spec}, ensure_ascii=False))
        return
    if action == "draft":
        value = proposal_input(data, task); work.safe_content(kt, scope(data, task))
        print(json.dumps({"schema": SCHEMA, "proposal": value, "content_hash": value["change"]["content_hash"]}, ensure_ascii=False))
    else:
        private = _private_receipt(args.admission_receipt)
        record = verify(kt, data, task, private, args.policy_digest)
        print(json.dumps({"schema": SCHEMA, "scope": scope(data, task), "admission": work.public(record),
            "admitted_at": private["admitted_at"], "task": work.view(kt, task, data=data)}, ensure_ascii=False))
