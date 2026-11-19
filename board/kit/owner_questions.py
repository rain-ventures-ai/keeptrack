"""An explicit owner-choice comment and its Inbox item are one idempotent board transaction.

Questions and answers are data. This module never grants authority, starts work or changes a wait/claim.
"""
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
import urllib.parse

KIT = 143
MAX_BYTES = 16384
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,19}\Z")
RID = re.compile(r"r_[a-z0-9]{10}\Z")
CID = re.compile(r"c_[a-f0-9]{6,32}\Z")
TASK = re.compile(r"t_[a-z0-9]{4,20}\Z")
ROOT_FIELDS = {"version", "request_id", "question", "waiting", "viewpoints", "options", "recommended", "recommendation_reason", "next_step"}
# Existing Relay BOARD_BLOCK categories, also enforced here so a direct structured CLI call cannot bypass
# connector screening. The ordinary comment command is unchanged. No match text is included in an error.
BOARD_PRIVATE = re.compile(
    r"\b(?:password|passphrase|api[_ -]?key|secret|token|credential)\b[^.\n]{0,40}\b(?:is|was|are)\b[\s:]*\S"
    r"|\b(?:password|passphrase|api[_ -]?key|secret|token|credential)\b[^:=\n]{0,30}[:=,\-–—]\s*\S"
    r"|\b(?:diagnosed|diagnosis|medicat\w*|antidepress\w*|antibiotic\w*|pills?|cancer|diabet\w*|prescri\w+|therap(?:y|ist)|illness|disease|disorder|adhd|autis\w*|anxiety|depress\w*|pregnan\w*|surgery|hospital|allerg\w*|disabilit\w*|mental health|chronic|blood (?:pressure|sugar)|(?:my|his|her|their|the|a) (?:doctor|gp|dentist))\b"
    r"|\b(?:salary|salaries|income|iban|sort code|account (?:number|no)|credit card|card number|mortgage|loan|net worth|pension|tax return|shares in|cap table|valuation)\b"
    r"|\b(?:performance review|disciplinary|grievance|dismissal|(?:was|got|been|being) fired|redundan\w*|sick (?:leave|note)|maternity|paternity|visa status|right to work|background check|appraisal)\b"
    r"|\b\d{1,5}[a-z]?\s+\w+(?:\s\w+)?\s+(?:street|st|road|rd|avenue|ave|lane|drive|crescent|gardens)\b"
    r"|\b(?:home address|(?:i|he|she|they|user|owner) lives? (?:at|in|on)|my address)\b"
    r"|\b(?:ignore (?:all |any |the )?(?:previous|prior|above|earlier) (?:instructions|rules)|disregard (?:the |your )?(?:rules|instructions)|system prompt|you (?:must|should) now|you are now|new instructions|act as (?:me|the user|the owner)|skip (?:the )?reviews?|auto-?merge|deploy to prod\w*)\b",
    re.I)
PRIVATE_NEIGHBOURS = re.compile(
    r"\b(?:doctor'?s appointment|gp appointment|(?:his|her|my|their) symptoms?|(?:my|his|her|personal) (?:bank|bonus|debts?|investments?|portfolio))\b"
    r"|(?-i:\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b)"
    r"|(?-i:\b\d{1,5}[a-z]?\s+[A-Z]\w+(?:\s[A-Z]\w+)?\s+(?:Close|Court|Ct|Way|Place|Terrace|Grove|Mews|Row|Square)\b)", re.I)


def refuse(message):
    raise SystemExit("owner question: " + message)


def preflight(raw):
    """Bound containers and separators before the JSON decoder allocates an object graph."""
    stack = []
    quoted = escaped = False
    containers = items = 0
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (123, 91, 44, 58):
            items += 1
            if items > 512:
                refuse("JSON structure exceeds its limit")
            if byte in (123, 91):
                containers += 1
                if containers > 96 or len(stack) >= 8:
                    refuse("JSON structure exceeds its limit")
                stack.append(byte)
        elif byte in (125, 93):
            if not stack or stack.pop() != (123 if byte == 125 else 91):
                refuse("invalid JSON structure")
    if quoted or stack:
        refuse("incomplete JSON structure")


def read_input(path, stdin=None):
    if not isinstance(path, str) or not path.strip():
        refuse("input path must be nonempty; use - for stdin")
    try:
        if path == "-":
            stream = stdin if stdin is not None else getattr(sys.stdin, "buffer", None)
            if stream is None:
                refuse("binary stdin is required")
            raw = stream.read(MAX_BYTES + 1)
        else:
            if not getattr(os, "O_PATH", 0):
                refuse("safe file input is unavailable; use stdin")
            pin = os.open(path, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                info = os.fstat(pin)
                if not stat.S_ISREG(info.st_mode):
                    refuse("input must be a regular file; symlinks and special files are refused")
                fd = os.open("/proc/self/fd/%d" % pin, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                try:
                    opened = os.fstat(fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISREG(opened.st_mode):
                        refuse("input identity changed")
                    with os.fdopen(fd, "rb", closefd=False) as source:
                        raw = source.read(MAX_BYTES + 1)
                finally:
                    os.close(fd)
            finally:
                os.close(pin)
    except (OSError, ValueError):
        refuse("input could not be read safely")
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        refuse("input exceeds the byte limit")
    preflight(raw)
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                refuse("duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        refuse("input is not valid UTF-8 JSON")


def text(value, cap):
    if not isinstance(value, str) or not value.strip() or len(value) > cap:
        refuse("text field is missing or exceeds its limit")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        refuse("text must be valid Unicode")
    if any(unicodedata.category(c).startswith("C") or 0xFE00 <= ord(c) <= 0xFE0F or ord(c) in (0x034F, 0x180E, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2028, 0x2029, 0xFFFD) for c in value) or (re.search(r"[\u0370-\u03FF\u0400-\u052F]", value) and re.search(r"[A-Za-z]", value)):
        refuse("text contains control or invisible characters")
    return value.strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def payload(kt, value):
    if not isinstance(value, dict) or set(value) != ROOT_FIELDS or type(value.get("version")) is not int or value["version"] != 1:
        refuse("payload must contain exactly the version-1 question fields")
    result = {"version": 1}
    for key, cap in (("request_id", 128), ("question", 160), ("waiting", 160), ("recommended", 20), ("recommendation_reason", 160), ("next_step", 200)):
        result[key] = text(value.get(key), cap)
    views = value.get("viewpoints")
    if not isinstance(views, list) or not 2 <= len(views) <= 3:
        refuse("provide two or three viewpoints")
    result["viewpoints"] = []
    for view in views:
        if not isinstance(view, dict) or set(view) != {"who", "wants"}:
            refuse("each viewpoint needs who and wants")
        result["viewpoints"].append({"who": text(view["who"], 60), "wants": text(view["wants"], 80)})
    options = value.get("options")
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        refuse("provide two to four options")
    result["options"] = []
    seen = set()
    for option in options:
        if not isinstance(option, dict) or set(option) != {"key", "label", "score", "reason", "basis"}:
            refuse("each option needs key, label, score, reason and basis")
        key = text(option["key"], 20)
        if not ID.fullmatch(key) or key in seen or type(option["score"]) is not int or not 0 <= option["score"] <= 10:
            refuse("option keys must be unique and scores must be integers from 0 to 10")
        seen.add(key)
        basis = option["basis"]
        if basis != "judgement":
            if not isinstance(basis, dict) or set(basis) != {"url", "title"}:
                refuse("option basis must be judgement or a titled HTTPS link")
            basis = {"url": text(basis["url"], 2000), "title": text(basis["title"], 120)}
            try:
                parsed = urllib.parse.urlsplit(basis["url"])
                parsed.port
            except ValueError:
                refuse("evidence link is invalid")
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or re.search(r"\s|[<>\\\"]", basis["url"]):
                refuse("evidence link must be HTTPS without credentials")
        result["options"].append({"key": key, "label": text(option["label"], 80), "score": option["score"], "reason": text(option["reason"], 120), "basis": basis})
    if result["recommended"] not in seen:
        refuse("recommendation must name one option")
    pending, strings = [result], []
    while pending:
        item = pending.pop()
        if isinstance(item, dict):pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item, list):pending.extend(item)
        elif isinstance(item, str):strings.append(unicodedata.normalize("NFKC", item))
    whole = " ".join(strings)
    blob = any(any(c.isdigit() for c in match.group()) and not (re.fullmatch(r"[0-9a-f]{40}", match.group()) and re.search(r"\b(?:commit|sha|sha-?1)[:\s]\s{0,2}$", line[max(0, match.start()-12):match.start()], re.I))
               for line in strings for match in re.finditer(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/=]{40,}", line))
    if kt.work_module().private_text(strings) or BOARD_PRIVATE.search(whole) or PRIVATE_NEIGHBOURS.search(whole) or blob:
        refuse("content contains secret-shaped or contact information; link to an authorised document")
    # Keep the three CARDS viewpoints/context parts visible in the Inbox too, without truncation.
    question = result["question"] + " Viewpoints: " + "; ".join(x["who"] + " wants " + x["wants"] for x in result["viewpoints"])
    reason = result["waiting"] + " Recommend: " + result["recommendation_reason"] + " Next: " + result["next_step"]
    if len(question) > 300 or len(reason) > 300:
        refuse("combined question or context exceeds the board field limit; shorten the wording")
    return result, question, reason


def links(kt, task, comment_id, proposal_id):
    """Only trusted config keys enter links. File fixtures have no remote board location."""
    if kt.FILE:
        return None, None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.+$)[A-Za-z0-9_.-]{1,100}", kt.REPO or ""):
        refuse("board repository cannot be linked safely")
    for value in (kt.BRANCH, kt.PATH):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", value):
            refuse("board branch or path cannot be linked safely")
    if kt.PATH.startswith("/") or any(p in ("", ".", "..") for p in kt.PATH.split("/")):
        refuse("board path cannot be linked safely")
    if kt.work_module().private_text([kt.REPO, kt.BRANCH, kt.PATH]):
        refuse("board link configuration contains private information")
    query = urllib.parse.urlencode({"repo": kt.REPO, "branch": kt.BRANCH, "path": kt.PATH, "card": task["id"]})
    base = "https://rain-ventures-ai.github.io/keeptrack/board/?" + query
    return base + "#" + str(task["num"]) + "&comment=" + comment_id, base + "#proposal=" + proposal_id


def md(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~])", r"\\\1", value)


def render(value, owner, inbox_url):
    lines = ["@" + owner + " " + md(value["waiting"]), "", "## Now", "", "**Question:** " + md(value["question"]), "", "## Why", "", "**Who it affects:** " + "; ".join(md(v["who"]) + " wants " + md(v["wants"]) for v in value["viewpoints"]), "", "**Options**"]
    for index, option in enumerate(value["options"], 1):
        basis = "judgement" if option["basis"] == "judgement" else "[" + md(option["basis"]["title"]) + "](" + option["basis"]["url"].replace("(", "%28").replace(")", "%29") + ")"
        lines.append(str(index) + ". **" + md(option["label"]) + "** (" + str(option["score"]) + "/10): " + md(option["reason"]) + " (" + basis + ")")
    recommended = next(o for o in value["options"] if o["key"] == value["recommended"])
    lines.extend(["", "**Recommendation:** " + md(recommended["label"]) + ". " + md(value["recommendation_reason"]), "", "## Plan", "", "**Next step:** " + md(value["next_step"]), "", "## Done when", "", "The owner records a preference in the linked Inbox item. That preference grants no approval or permission and starts no work."])
    if inbox_url:
        lines.extend(["", "[Answer this question in the Review Inbox](" + inbox_url + ")"])
    else:
        lines.extend(["", "Local fixture: the linked Inbox item is stored locally; no remote link is available."])
    body = "\n".join(lines)
    if len(body) > 4000:
        refuse("rendered comment exceeds its limit")
    return body


def projected_options(value):
    options = []
    for option in value["options"]:
        item = {"key": option["key"], "label": option["label"], "note": str(option["score"]) + "/10 — " + option["reason"] + (" (judgement)" if option["basis"] == "judgement" else "")}
        if option["basis"] != "judgement":
            item["url"] = option["basis"]["url"]
        options.append(item)
    return options


def submit(kt, a):
    if kt.BACKEND == "hosted" and not kt.FILE:
        refuse("capability_unavailable: structured questions are unavailable in hosted phase 0")
    if os.environ.get("KEEPTRACK_PROPOSALS_ONLY") == "1":
        refuse("KEEPTRACK_PROPOSALS_ONLY: structured comments also mutate cards")
    if getattr(a, "text", None) is not None or getattr(a, "reply_to", None):
        refuse("structured mode cannot be combined with text or replies")
    value, question, reason = payload(kt, read_input(a.owner_question))
    semantic = dict(value); semantic.pop("request_id")
    original = digest(semantic)
    request_hash = digest(value["request_id"])
    answer = {}
    initial_owner = None
    initial_scope = None
    def change(data):
        nonlocal initial_owner, initial_scope
        kt._MUT["recheck"] = True
        kt.require_review_storage(data)
        owner = kt.quiet_claim_setting_owner(data)
        if initial_owner is None:
            initial_owner = owner
        elif owner != initial_owner:
            refuse("board owner changed; nothing posted")
        task = kt.find(data, a.id)
        if not TASK.fullmatch(task.get("id", "")) or type(task.get("num")) is not int or task["num"] <= 0 or task.get("column") == "done":
            refuse("target must be an open card with stable identity")
        who = task.get("assignees", [])
        if not isinstance(who, list) or not all(isinstance(x, str) for x in who) or (who and owner not in {x.casefold() for x in who}):
            refuse("target is outside this owner's served scope")
        if task.get("project") is not None and not isinstance(task["project"], str):
            refuse("target scope needs repair")
        scope = (task["id"], tuple(sorted(x.casefold() for x in who)), task.get("project"))
        if initial_scope is None:
            initial_scope = scope
        elif scope != initial_scope:
            refuse("target scope changed; nothing posted")
        records = task.get("owner_questions", {})
        if not isinstance(records, dict) or len(records) > 256:
            refuse("question receipts need repair or archival before new intake")
        key = "owner-question:" + task["id"] + ":" + request_hash[:32]
        try:
            proposals = kt._all_proposals(data)
            if not all(isinstance(p, dict) and (p.get("id") is None or isinstance(p["id"], str)) and (p.get("action_key") is None or isinstance(p["action_key"], str)) for p in proposals):
                refuse("Inbox identity needs repair")
        except (AttributeError, TypeError, ValueError):
            refuse("Inbox identity needs repair")
        found = [p for p in proposals if p.get("action_key") == key]
        if len(found) > 1:
            refuse("question identity is ambiguous")
        record = records.get(request_hash)
        if record is not None:
            if not isinstance(record, dict) or type(record.get("version")) is not int or record["version"] != 1 or type(record.get("card_num")) is not int or record["card_num"] <= 0 or record.get("digest") != original or record.get("scope_digest") != digest(scope) or not isinstance(record.get("created_by"), str) or not RID.fullmatch(str(record.get("proposal_id", ""))) or not CID.fullmatch(str(record.get("comment_id", ""))) or record.get("action_key") != key or record.get("decider") != owner:
                refuse("request already exists with different content or an inconsistent receipt")
            if len(found) != 1 or found[0].get("id") != record["proposal_id"] or sum(p.get("id") == record["proposal_id"] for p in proposals) != 1 or not isinstance(found[0].get("source"), dict) or found[0]["source"].get("revision") != original:
                refuse("recorded question cannot be verified; never recreate its identity")
            comment_url, inbox_url = links(kt, dict(task, num=record["card_num"]), record["comment_id"], record["proposal_id"])
            actual = found[0]
            if "change" not in actual:
                refuse("recorded question detail was retired; retained identity prevents recreation")
            expected_change = {"task": task["id"], "question": question, "options": projected_options(value), "recommended": value["recommended"], "links": [{"url": comment_url, "title": "Original question on the card"}] if comment_url else []}
            expected_source = {"kind": "other", "id": key, "revision": original, "title": "Owner choice from a card comment", "date": "", "url": ""}
            if actual.get("kind") != "ask.choose" or actual.get("decider") != owner or actual.get("createdBy") != record["created_by"] or actual.get("title") != value["question"] or actual.get("reason") != reason or actual.get("change") != expected_change or actual["source"] != expected_source:
                refuse("recorded question content changed; nothing posted")
            comments = task.get("comments", [])
            if not isinstance(comments, list):
                refuse("question comment index needs repair")
            matched = [c for c in comments if isinstance(c, dict) and c.get("id") == record["comment_id"]]
            meta = matched[0].get("owner_question") if len(matched) == 1 else None
            if len(matched) > 1 or matched and (not isinstance(meta, dict) or type(meta.get("version")) is not int or matched[0].get("by") != record["created_by"] or matched[0].get("text") != render(value, owner, inbox_url) or meta != {"version": 1, "proposal_id": record["proposal_id"], "request_hash": request_hash, "digest": original}):
                refuse("recorded question comment changed; nothing posted")
            answer.clear(); answer.update(card_id=task["id"], comment_id=record["comment_id"], proposal_id=record["proposal_id"], created=False, comment_url=comment_url, inbox_url=inbox_url)
            return
        if found or len(records) >= 256:
            refuse("question identity already exists or receipt capacity is reached; repair before intake")
        comment_id = "c_" + kt.uuid.uuid4().hex[:12]
        proposal_id = "r_" + kt.uuid.uuid4().hex[:10]
        comment_url, inbox_url = links(kt, task, comment_id, proposal_id)
        body = render(value, owner, inbox_url)
        options = projected_options(value)
        raw = {"id": proposal_id, "kind": "ask.choose", "title": value["question"], "decider": owner,
               "source": {"kind": "other", "id": key, "revision": original, "title": "Owner choice from a card comment"},
               "action_key": key, "work_key": key, "reason": reason,
               "change": {"task": task["id"], "question": question, "options": options, "recommended": value["recommended"], "links": [{"url": comment_url, "title": "Original question on the card"}] if comment_url else []}}
        added, _ = kt._prepare_proposals(data, [raw])
        if len(added) != 1:
            refuse("question identity was not unique; nothing posted")
        row = kt.append_comment(task, body, kt.who_am_i(task)); row["id"] = comment_id
        row["owner_question"] = {"version": 1, "proposal_id": proposal_id, "request_hash": request_hash, "digest": original}
        task.setdefault("owner_questions", {})[request_hash] = {"version": 1, "digest": original, "scope_digest": digest(scope), "card_num": task["num"], "proposal_id": proposal_id, "comment_id": comment_id, "action_key": key, "decider": owner, "created_by": kt.who_am_i(task), "created_at": kt.now()}
        data["settings"]["min_kit"] = max(kt.board_min_kit(data), KIT)
        task["updated"] = kt.now()
        answer.clear(); answer.update(card_id=task["id"], comment_id=comment_id, proposal_id=proposal_id, created=True, comment_url=comment_url, inbox_url=inbox_url)
    kt.mutate(change, "Post an owner-choice comment and linked Inbox question")
    print(json.dumps(answer) if getattr(a, "json", False) else "owner question " + answer["proposal_id"] + " linked to comment " + answer["comment_id"])
