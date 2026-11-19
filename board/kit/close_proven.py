"""Explicit evidence-based reconciliation. Evidence and preferences never grant authority.

Kit145: disabled until a person owner enables it. Legacy prose requires that person's
exact snapshot review; known waits/questions/claims are never overridden by review.
"""
import copy
import base64
import datetime as dt
import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace

KIT = 145
MAX_RESPONSE = 524288
MAX_PRS = 32
MAX_BATCH = 8
MAX_ARCHIVE = 1048576
MAX_ARCHIVES = 128
MAX_ARCHIVE_TOTAL = 67108864
DEADLINE = 60
HEX = re.compile(r"[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
TASK = re.compile(r"t_[a-z0-9]{4,20}\Z")
PR_PATH = re.compile(r"/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/pull/([1-9][0-9]{0,9})(?:/(?:files|commits|checks))?/?\Z")


def refuse(reason):
    raise SystemExit("close-proven: " + reason + "; nothing changed")


def valid_stamp(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)',value):return False
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00'))<=dt.datetime.now(dt.timezone.utc)
    except (ValueError,OverflowError):return False


def digest(value):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError):
        refuse("metadata cannot be snapshotted safely")
    if len(raw) > 1048576:
        refuse("snapshot exceeds its byte budget")
    return hashlib.sha256(b"keeptrack-close-proven-v1\0" + raw).hexdigest()


def canonical_pr(value):
    """Return an identity, ignoring ordinary report query/fragment; never echo input."""
    if not isinstance(value, str) or len(value) > 4000 or re.search(r"\s|[\\<>\x00-\x1f\x7f]", value):
        return None
    try:
        url = urllib.parse.urlsplit(value)
        port = url.port
    except ValueError:
        return None
    if url.scheme != "https" or url.netloc.casefold() != "github.com" or url.username or url.password or port is not None or "%" in url.path:
        return None
    match = PR_PATH.fullmatch(url.path)
    if not match or match[2] in (".", ".."):
        return None
    return "https://github.com/" + match[1].casefold() + "/" + match[2].casefold() + "/pull/" + str(int(match[3]))


def pr_links(t):
    values = t.get("links", [])
    if not isinstance(values, list) or len(values) > 100:
        return None, None
    found, marked = set(), set()
    for link in values:
        if not isinstance(link, dict) or not isinstance(link.get("url"), str) or not isinstance(link.get("title", ""), str):
            return None, None
        value = link["url"]
        identity = canonical_pr(value)
        if identity:
            found.add(identity)
            if re.match(r"^\s*deliverable\b", link.get("title", ""), re.I):
                marked.add(identity)
        elif re.search(r"github\.com|/pull/", value, re.I):
            # An ordinary GitHub issue/repository URL is not a malformed PR.
            try:
                parsed = urllib.parse.urlsplit(value)
                is_pr = "/pull" in urllib.parse.unquote(parsed.path).casefold()
            except ValueError:
                is_pr = True
            if is_pr:
                return None, None
    return sorted(found), sorted(marked)


def board(kt):
    if kt.FILE:
        return {"local": digest(os.path.realpath(kt.FILE))}
    return {"repo": kt.REPO, "branch": kt.BRANCH, "path": kt.PATH}


def snapshot(kt, data, t, proposals=None):
    # Everything on the card except this feature's own records and incidental save time.
    # Comments, todos, unknown authority metadata and PR query strings are bound, not copied out.
    card = {k: v for k, v in t.items() if k not in ("close_review", "close_evidence", "updated")}
    # Bind workflow facts separately from PR state: a new/different answer or done
    # record invalidates person review, while a legitimate later merge does not.
    inventory=related_questions(t, data.get('proposals',[]) if proposals is None else proposals)
    return digest({"version": 1, "board": board(kt), "owner": kt.quiet_claim_setting_owner(data), "card": card,
                   "questions":[digest(p) for p in sorted(inventory,key=lambda p:str(p.get('id')))]})


def preflight(kt, writing):
    if kt.BACKEND == "hosted" and not kt.FILE:
        refuse("capability_unavailable in hosted phase 0")
    if writing and os.environ.get("KEEPTRACK_PROPOSALS_ONLY") == "1":
        refuse("KEEPTRACK_PROPOSALS_ONLY forbids card mutations")


def local_archive_stat(kt, rel):
    root = os.path.realpath(os.path.dirname(os.path.abspath(kt.FILE)))
    folder = os.path.join(root, 'archive')
    path = os.path.join(root, rel)
    try:
        if not stat.S_ISDIR(os.lstat(folder).st_mode):refuse('archive folder must not be a symlink')
        info = os.lstat(path)
    except OSError:
        refuse('archive dependency is unreadable')
    if not stat.S_ISREG(info.st_mode):refuse('archive input must be a regular file without symlinks')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def dependency_signature(kt, data):
    state = kt._BOARD_STATES.get(id(data), {})
    files = state.get('files')
    if not isinstance(files, dict):refuse('captured board dependencies are unavailable')
    archive = data.get('archive', {})
    if not isinstance(archive, dict) or not isinstance(archive.get('files', {}), dict):refuse('archive coverage index needs repair')
    entries = {rel: entry for rel,entry in files.items() if rel.startswith('archive/') and rel.endswith('.json')}
    if len(entries)>MAX_ARCHIVES:refuse('archive lookup exceeds its bounded part budget')
    indexed=set(archive.get('files', {}))
    if any(not isinstance(key,str) or not kt.valid_archive_key(key) for key in indexed):refuse('archive index identity needs repair')
    if not indexed <= {rel[8:-5] for rel in entries}:refuse('archive coverage is incomplete')
    deps={}
    for rel,entry in sorted(entries.items()):
        if not kt.valid_archive_key(rel[8:-5]) or not isinstance(entry,dict):refuse('archive dependency needs repair')
        if kt.FILE:
            deps[rel]=local_archive_stat(kt,rel)
        elif state.get('mode')=='api':
            sha=entry.get('sha')
            if not isinstance(sha,str) or not SHA.fullmatch(sha):refuse('archive blob identity is unavailable')
            deps[rel]=sha
        elif state.get('mode')=='git':
            head=state.get('head')
            if not isinstance(head,str) or not SHA.fullmatch(head):refuse('archive commit identity is unavailable')
            deps[rel]=head
        else:refuse('unsupported archive dependency transport')
    values=data.get('proposals',[])
    if not isinstance(values,list) or len(values)>8192 or any(not isinstance(p,dict) for p in values):refuse('active Inbox inventory needs repair')
    return {'archives':deps,'index':digest(archive),'active':digest(values)}


def archive_json(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_ARCHIVE:refuse('archive exceeds its byte budget')
    # Archive parts may be900KiB. Bound their structure before allocating JSON objects,
    # without applying the much smaller interactive-question payload's limits.
    stack=[];quoted=escaped=False;nodes=tokens=0
    for byte in raw:
        if quoted:
            if escaped:escaped=False
            elif byte==92:escaped=True
            elif byte==34:quoted=False
        elif byte==34:quoted=True
        elif byte in (123,91,44,58):
            tokens+=1
            if tokens>200000:refuse('archive structure exceeds its budget')
            if byte in (123,91):
                nodes+=1
                if nodes>50000 or len(stack)>=32:refuse('archive structure exceeds its budget')
                stack.append(byte)
        elif byte in (125,93):
            if not stack or stack.pop()!=(123 if byte==125 else 91):refuse('archive structure is invalid')
    if quoted or stack:refuse('archive structure is incomplete')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:refuse('archive contains duplicate fields')
            result[key]=value
        return result
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except (ValueError,UnicodeError,RecursionError):refuse('archive is not valid bounded JSON')
    # Native archives retain schema3 even on schema4 split boards (ARCHIVE_SCHEMA),
    # including900KiB year parts. Do not invent compatibility with unknown versions.
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=3 or value.get('archive') is not True or not isinstance(value.get('proposals',[]),list):refuse('archived question inventory needs repair')
    return value


def bounded_process(command, body, deadline, limit):
    try:proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    except OSError:return None
    selector=None
    try:
        if body:proc.stdin.write(body)
        proc.stdin.close()
        selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ)
        chunks=[];size=0
        while True:
            left=deadline-time.monotonic()
            if left<=0 or not selector.select(left):return None
            chunk=os.read(proc.stdout.fileno(),min(65536,limit+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if size>limit:return None
        if proc.wait(timeout=max(.01,deadline-time.monotonic()))!=0:return None
        return b''.join(chunks)
    except (OSError,subprocess.SubprocessError):return None
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if proc.stdout:proc.stdout.close()
        if proc.stdin and not proc.stdin.closed:proc.stdin.close()
        if selector:selector.close()


class ProposalContext:
    """An immutable complete bounded question inventory, acquired before the CAS lock."""
    def __init__(self,kt,data,deadline):
        self.signature=dependency_signature(kt,data)
        self.archived=[];total=0
        state=kt._BOARD_STATES[id(data)]
        for rel,dependency in self.signature['archives'].items():
            entry=state['files'][rel]
            if kt.FILE:
                root=os.path.realpath(os.path.dirname(os.path.abspath(kt.FILE)))
                try:
                    fd=os.open(os.path.join(root,rel),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
                    with os.fdopen(fd,'rb') as source:
                        info=os.fstat(source.fileno())
                        identity=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
                        if identity!=dependency or not stat.S_ISREG(info.st_mode):refuse('archive dependency changed')
                        raw=source.read(MAX_ARCHIVE+1)
                except OSError:refuse('archive could not be read safely')
            elif 'text' in entry:
                if not isinstance(entry['text'],str) or len(entry['text'])>MAX_ARCHIVE:refuse('archive exceeds its byte budget')
                try:raw=entry['text'].encode('utf-8','strict')
                except UnicodeError:refuse('archive is not UTF-8')
            elif state.get('mode')=='git':
                raw=bounded_process(['git','-C',kt.ROOT,'cat-file','blob',dependency+':'+kt.archive_path(rel[8:-5])],None,deadline,MAX_ARCHIVE)
            else:
                envelope=bounded_json(kt,None,deadline,path='repos/'+kt.REPO+'/git/blobs/'+dependency,limit=2*MAX_ARCHIVE)
                if not isinstance(envelope,dict) or envelope.get('sha')!=dependency or envelope.get('encoding')!='base64' or not isinstance(envelope.get('content'),str) or len(envelope['content'])>2*MAX_ARCHIVE:refuse('archive blob proof is incomplete')
                try:raw=base64.b64decode(''.join(envelope['content'].split()),validate=True)
                except (ValueError,UnicodeError):refuse('archive blob proof is invalid')
                if type(envelope.get('size')) is not int or envelope['size']!=len(raw):refuse('archive blob size changed')
            if raw is None or len(raw)>MAX_ARCHIVE:refuse('archive read was incomplete or exceeded its budget')
            if not kt.FILE and state.get('mode')=='api' and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=dependency:refuse('archive blob identity changed')
            total+=len(raw)
            if total>MAX_ARCHIVE_TOTAL or time.monotonic()>=deadline:refuse('archive coverage exceeded its total budget')
            self.archived.extend(archive_json(raw).get('proposals',[]))
        if dependency_signature(kt,data)!=self.signature:refuse('archive coverage changed while reading')
        self.existing(data)

    def matches(self,kt,data):
        return dependency_signature(kt,data)==self.signature

    def existing(self,data):
        values=list(data.get('proposals',[]))+self.archived
        if len(values)>8192 or any(not isinstance(p,dict) for p in values):refuse('complete Inbox inventory exceeds its budget')
        return values

    def view(self,kt):
        # Native144 pure guard sees this verified inventory, never its default lazy reader.
        return SimpleNamespace(**dict(vars(kt),_all_proposals=lambda data:self.existing(data)))


def related_questions(t,proposals):
    if not isinstance(proposals,list) or any(not isinstance(p,dict) for p in proposals):refuse('question inventory needs repair')
    records=t.get('owner_questions',{})
    bound={r['proposal_id'] for r in records.values() if isinstance(r,dict) and isinstance(r.get('proposal_id'),str)} if isinstance(records,dict) else set()
    result=[]
    for p in proposals:
        change=p.get('change');target=p.get('target')
        related=p.get('id') in bound or isinstance(change,dict) and change.get('task')==t['id'] or isinstance(target,dict) and target.get('type')=='task' and target.get('id')==t['id']
        if related and (p.get('id') in bound or p.get('kind') in ('ask.choose','ask.approve','ask.question')):result.append(p)
    return result


def question_state(kt,t,proposals,owner):
    records = t.get("owner_questions", {})
    if not isinstance(records, dict) or len(records) > 256 or any(not isinstance(r, dict) or not isinstance(r.get("proposal_id"), str) for r in records.values()):
        return "question_metadata", []
    bound = {r["proposal_id"] for r in records.values()}
    relevant = related_questions(t,proposals)
    ids = [p.get("id") for p in relevant]
    if any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)) or not bound <= set(ids):
        return "question_metadata", relevant
    # Native terminal workflow is a factual disposition, never proof of an external
    # effect or approval.145 still requires exact person review of this inventory.
    if any(not kt.handback_module().question_settled(kt,p,owner) for p in relevant):
        return "owner_question", relevant
    return None, relevant


def reviewed(kt, data, t, snap, prs):
    record = t.get("close_review")
    if record is None:
        return False, []
    if not isinstance(record, dict) or set(record) != {"version", "snapshot", "owner", "associations", "reviewed_at"} or type(record.get("version")) is not int or record["version"] != 1 or record.get("snapshot") != snap or record.get("owner") != kt.quiet_claim_setting_owner(data):
        return False, []
    associations = record.get("associations")
    if not isinstance(associations, list) or not associations or len(associations) > MAX_PRS or associations != sorted(set(associations)) or any(x not in prs for x in associations):
        return False, []
    return True, associations


def valid_review(record):
    if not isinstance(record, dict) or set(record) != {'version','snapshot','owner','associations','reviewed_at'} or type(record.get('version')) is not int or record['version'] != 1:
        return False
    values = record.get('associations')
    return isinstance(record.get('snapshot'), str) and bool(HEX.fullmatch(record['snapshot'])) and isinstance(record.get('owner'), str) and bool(record['owner']) and valid_stamp(record.get('reviewed_at')) and isinstance(values, list) and bool(values) and len(values) <= MAX_PRS and all(isinstance(x, str) and canonical_pr(x) == x for x in values) and values == sorted(set(values))


def eligibility(kt, data, t, proposals):
    if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not TASK.fullmatch(t["id"]):
        return "card_metadata", None
    if "coordination" in t:
        return "coordinated", None
    if t.get("column") == "done" or t.get("archived") or t.get("outcome") == "cancelled":
        return "not_open", None
    columns=data.get('columns')
    if not isinstance(columns,list) or any(not isinstance(c,dict) or not isinstance(c.get('id'),str) or not isinstance(c.get('name'),str) for c in columns):
        return 'column_metadata',None
    selected=[c for c in columns if c['id']==t.get('column')]
    if len(selected)!=1:return 'column_metadata',None
    if selected[0]['name'].strip().casefold()=='done':return 'not_open',None
    if sum(c['id']=='done' for c in columns)!=1:return 'column_metadata',None
    if selected[0]['name'].strip().casefold().replace('-',' ')=='pending review':
        return 'owner_gate',None
    if t.get("claim") is not None:
        return "claim_retained", None
    if t.get("waiting") is not None:
        return "wait_retained", None
    if 'close_review' in t and not valid_review(t['close_review']):
        return 'review_metadata', None
    labels, assignees = t.get("labels", []), t.get("assignees", [])
    if not isinstance(labels, list) or not isinstance(assignees, list) or any(not isinstance(v, str) for v in labels + assignees):
        return "scope_metadata", None
    owner = kt.quiet_claim_setting_owner(data)
    if assignees and owner not in {x.casefold() for x in assignees}:
        return "outside_owner_scope", None
    if t.get("column") == "pending-review" or set(x.casefold() for x in labels) & {"needs-human", "held"}:
        return "owner_gate", None
    if any(k in t for k in ("owner_bridge", "owner_hold", "pending_owner_decision")):
        return "owner_gate", None
    if 'asked' in t:
        asked = t['asked']
        if not isinstance(asked,dict) or set(asked) != {'at','via','mode'} or not isinstance(asked.get('at'),str) or not kt.ASKED_STAMP.fullmatch(asked['at']) or not isinstance(asked.get('via'),str) or not kt.ASKED_VIA.fullmatch(asked['via']) or asked.get('mode') not in ('now','dispatch'):
            return 'owner_gate', None
    qreason, relevant = question_state(kt,t,proposals,owner)
    if qreason:
        return qreason, None
    todos = t.get("todos")
    if not isinstance(todos, list) or len(todos) > 200 or any(not isinstance(d, dict) or type(d.get("done")) is not bool for d in todos):
        return "todo_metadata", None
    prs, marked = pr_links(t)
    if prs is None:
        return "link_metadata", None
    if not prs:
        return "no_pr_evidence", None
    if len(prs) > MAX_PRS:
        return "pr_budget", None
    snap = snapshot(kt, data, t,proposals)
    has_review, associated = reviewed(kt, data, t, snap, prs)
    comments = t.get("comments", [])
    if not isinstance(comments, list) or any(not isinstance(c, dict) for c in comments):
        return "comment_metadata", None
    if comments and not has_review:
        return "legacy_comment_review_required", {"snapshot": snap, "prs": prs}
    if relevant and not has_review:
        return "resolved_question_review_required", {"snapshot":snap,"prs":prs}
    if not todos and not has_review:
        return "empty_checklist_review_required", {"snapshot": snap, "prs": prs}
    if not marked and not associated:
        return "association_review_required", {"snapshot": snap, "prs": prs}
    details = {"snapshot": snap, "prs": prs, "associations": sorted(set(marked + associated))}
    if any(d["done"] is not True for d in todos):
        return "open_todo", details
    return None, details


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def bounded_json(kt, query, deadline, *, path="graphql", limit=MAX_RESPONSE):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    body = json.dumps({"query": query}).encode() if query is not None else None
    raw = None
    if kt.use_http():
        if not kt.token():
            return None
        req = urllib.request.Request(kt.github_api_base() + "/" + path, data=body, headers={"Authorization": "Bearer " + kt.token(), "Content-Type": "application/json", "Accept": "application/vnd.github+json", "User-Agent": "keeptrack-close-proof"})
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=remaining) as response:
                chunks, size = [], 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    # HTTPResponse exposes the underlying socket here. Fail closed if a
                    # nonstandard response cannot carry a per-read remaining deadline.
                    sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
                    if sock is None:
                        return None
                    sock.settimeout(remaining)
                    chunk = response.read1(min(65536, limit + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk); size += len(chunk)
                    if size > limit:
                        return None
                    if response.isclosed():
                        break
                raw = b''.join(chunks)
        except urllib.error.HTTPError as error:
            error.close()
            return None
        except (OSError, ValueError, urllib.error.URLError):
            return None
    else:
        command = ["gh", "api", path] + (["--input", "-"] if body is not None else [])
        raw = bounded_process(command, body, deadline, limit)
    if raw is None or len(raw) > limit:
        return None
    # This query has very small bounded answers; reuse the pre-allocation structural guard.
    try:
        kt.owner_question_module().preflight(raw)
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:raise ValueError()
                result[key] = value
            return result
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (SystemExit, ValueError, UnicodeError, RecursionError):
        return None


def merged_proof(identity, value):
    if not isinstance(identity, str) or canonical_pr(identity) != identity or not isinstance(value, dict) or value.get("state") != "MERGED" or canonical_pr(value.get("url")) != identity:
        return None
    sha = value.get("mergeCommit")
    sha = sha.get("oid") if isinstance(sha, dict) else None
    stamp = value.get("mergedAt")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", stamp):
        return None
    try:
        parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed > dt.datetime.now(dt.timezone.utc):
        return None
    return {"url": identity, "merge_commit": sha, "merged_at": parsed.astimezone(dt.timezone.utc).isoformat()}


def read_proofs(kt, identities, deadline=None):
    if kt.FILE or len(identities) > MAX_PRS:
        return {}
    deadline = deadline or time.monotonic() + DEADLINE
    result = {}
    for offset in range(0, len(identities), MAX_BATCH):
        batch = identities[offset:offset + MAX_BATCH]
        parts = []
        for n, identity in enumerate(batch):
            path = urllib.parse.urlsplit(identity).path.split("/")
            parts.append('p%d:repository(owner:%s,name:%s){nameWithOwner pullRequest(number:%d){number url state mergedAt mergeCommit{oid}}}' % (n, json.dumps(path[1]), json.dumps(path[2]), int(path[4])))
        value = bounded_json(kt, "query{" + " ".join(parts) + "}", deadline)
        if not isinstance(value, dict) or value.get("errors") or not isinstance(value.get("data"), dict):
            continue
        for n, identity in enumerate(batch):
            node = value["data"].get("p%d" % n)
            path = urllib.parse.urlsplit(identity).path.split("/")
            if not isinstance(node, dict) or not isinstance(node.get("nameWithOwner"), str) or node["nameWithOwner"].casefold() != (path[1] + "/" + path[2]).casefold():
                continue
            pull = node.get("pullRequest")
            if not isinstance(pull, dict) or type(pull.get("number")) is not int or pull["number"] != int(path[4]):
                continue
            proof = merged_proof(identity, pull)
            if proof:
                result[identity] = proof
    return result


def get_task(kt, data, tid):
    if not isinstance(tid, str) or not TASK.fullmatch(tid):
        refuse("a stable card ID is required")
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        refuse("card index needs repair")
    matches = [t for t in tasks if isinstance(t, dict) and t.get("id") == tid]
    if len(matches) != 1:
        refuse("card is missing, archived or ambiguous")
    return matches[0]


def report_digest(kt,data,context):
    tasks=data.get('tasks')
    if not isinstance(tasks,list) or any(not isinstance(t,dict) or not isinstance(t.get('id'),str) or not TASK.fullmatch(t['id']) for t in tasks):refuse('report card inventory needs repair')
    ids=[t['id'] for t in tasks]
    if len(ids)!=len(set(ids)):refuse('report card identities are ambiguous')
    proposals=context.existing(data)
    settings=data.get('settings')
    if not isinstance(settings,dict):refuse('report settings need repair')
    settings={k:v for k,v in settings.items() if k not in ('min_kit','reconcile_close_proven','reconcile_close_report')}
    business={k:v for k,v in data.items() if k not in ('tasks','proposals','archive','contacts','history','settings','next_num')}
    return digest({'version':1,'board':board(kt),'owner':kt.quiet_claim_setting_owner(data),
                   'settings':digest(settings),'business':digest(business),
                   'cards':[(t['id'],snapshot(kt,data,t,proposals)) for t in sorted(tasks,key=lambda t:t['id'])],
                   'questions':sorted(digest(p) for p in proposals if p.get('kind') in ('ask.choose','ask.approve','ask.question'))})


def valid_activation(data,owner):
    settings=data.get('settings')
    record=settings.get('reconcile_close_report') if isinstance(settings,dict) else None
    return isinstance(record,dict) and set(record)=={'version','digest','owner','enabled_at'} and type(record.get('version')) is int and record['version']==1 and record.get('owner')==owner and isinstance(record.get('digest'),str) and bool(HEX.fullmatch(record['digest'])) and valid_stamp(record.get('enabled_at'))


def setting_context(kt,data,expected):
    preflight(kt,True)
    if kt.agent_run():refuse('only a person kit owner may enable evidence closure')
    if not isinstance(expected,str) or not HEX.fullmatch(expected):refuse('enablement needs the exact reviewed strict-report digest')
    context=ProposalContext(kt,data,time.monotonic()+DEADLINE)
    if report_digest(kt,data,context)!=expected:refuse('reviewed strict report changed; read the dry run again')
    return context


def enable_reviewed(kt,data,context,expected):
    if not context.matches(kt,data) or report_digest(kt,data,context)!=expected:refuse('reviewed strict report or coverage changed')
    owner=kt.quiet_claim_setting_owner(data)
    old=data['settings'].get('reconcile_close_report')
    if not isinstance(old,dict) or old.get('digest')!=expected or old.get('owner')!=owner:
        data['settings']['reconcile_close_report']={'version':1,'digest':expected,'owner':owner,'enabled_at':kt.now()}


def review(kt, a):
    preflight(kt, True)
    if kt.agent_run():
        refuse("only a person kit owner may record an exact closure review")
    expected = getattr(a, "expected_snapshot", None)
    if not isinstance(expected, str) or not HEX.fullmatch(expected):
        refuse("expected snapshot must come from the reviewed strict report")
    associations = getattr(a, "associate_pr", None)
    if not isinstance(associations, list) or not associations or len(associations) > MAX_PRS:
        refuse("review needs an explicit linked PR association")
    canonical = [canonical_pr(x) for x in associations]
    if any(x is None for x in canonical):
        refuse("review association is not a valid GitHub PR identity")
    canonical = sorted(set(canonical))
    loaded,_=kt.load()
    context=ProposalContext(kt,loaded,time.monotonic()+DEADLINE)
    initial_owner = None
    answer = {}
    def change(data):
        nonlocal initial_owner
        kt._MUT['recheck'] = True
        kt.require_review_storage(data)
        if not context.matches(kt,data):refuse('question coverage changed during exact review')
        owner = kt.quiet_claim_setting_owner(data)
        if initial_owner is None:initial_owner = owner
        elif initial_owner != owner:refuse("owner changed during review")
        t = get_task(kt, data, a.review_close)
        if t.get('column') == 'done' or 'coordination' in t:
            refuse("review target is not an ordinary open card")
        current = snapshot(kt, data, t,context.existing(data))
        if current != expected:
            refuse("review snapshot changed")
        prs, _ = pr_links(t)
        if prs is None or any(x not in prs for x in canonical):
            refuse("review must associate an existing linked PR")
        # This declares exact legacy-comment review and association only. Known gates remain.
        record = {'version': 1, 'snapshot': current, 'owner': owner, 'associations': canonical, 'reviewed_at': kt.now()}
        old = t.get('close_review')
        if isinstance(old, dict) and all(old.get(k) == v for k, v in record.items() if k != 'reviewed_at'):
            record = old
        t['close_review'] = record
        data['settings']['min_kit'] = max(kt.board_min_kit(data), KIT)
        answer.clear(); answer.update(card_id=t['id'], snapshot=current, associations=canonical, reviewed=True)
    kt.mutate(change, 'Record a person-reviewed exact closure snapshot')
    print(json.dumps(answer))


def evidence_key(kt, t, proof):
    return digest({'board': board(kt), 'card_id': t['id'], 'delivery': proof})


def completion_args(t):
    note = 'Evidence reconciled: all linked pull requests are merged; canonical merge proofs are retained in the closure receipt.'
    return type('DoneArgs', (), {'id': t['id'], 'note': note, 'force': False, 'cancel': False})()


def reviewed_empty(kt,data,t,info):
    # No board flag, truthy input or Inbox answer can select this144internal extension.
    return t.get('todos')==[] and reviewed(kt,data,t,info['snapshot'],info['prs'])[0] is True


def row(kt, data, t, proposals, proofs):
    reason, info = eligibility(kt, data, t, proposals)
    ident = t.get('id') if isinstance(t,dict) else None
    result = {'card_id': ident if isinstance(ident,str) and TASK.fullmatch(ident) else None, 'card_url':None, 'action': 'leave', 'reason': reason}
    if result['card_id'] and not kt.FILE and type(t.get('num')) is int and t['num']>0:
        try:
            comment_url,_=kt.owner_question_module().links(kt,t,'c_000000','r_0000000000')
            result['card_url']=comment_url.split('#',1)[0]+'#'+str(t['num'])
        except SystemExit:
            pass
    if info:
        result.update(snapshot=info['snapshot'], prs=info['prs'])
    if reason not in (None, 'open_todo'):
        return result
    if reason=='open_todo':
        request=question_payload(kt,t['id'],info['prs'])['request_id']
        key='owner-question:'+t['id']+':'+kt.owner_question_module().digest(request)[:32]
        if any(p.get('action_key')==key for p in proposals):
            result['reason']='previous_question_work_remaining'
            return result
    proof = [proofs.get(url) for url in info['prs']]
    if any(p is None for p in proof):
        result['reason'] = 'pr_unverified'
        return result
    key = evidence_key(kt, t, proof)
    previous = t.get('close_evidence')
    if previous is not None:
        if not isinstance(previous, dict) or set(previous) != {'version','delivery','evidence','snapshot','post_snapshot','owner','completed_at'} or type(previous.get('version')) is not int or previous['version'] != 1 or not isinstance(previous.get('delivery'), str) or not HEX.fullmatch(previous['delivery']) or not isinstance(previous.get('snapshot'), str) or not HEX.fullmatch(previous['snapshot']) or not isinstance(previous.get('post_snapshot'),str) or not HEX.fullmatch(previous['post_snapshot']) or not isinstance(previous.get('owner'), str) or not isinstance(previous.get('completed_at'), str) or not isinstance(previous.get('evidence'), list) or not previous['evidence'] or len(previous['evidence']) > MAX_PRS:
            result['reason'] = 'closure_receipt_metadata'
            return result
        old_proofs=[]
        for item in previous['evidence']:
            if not isinstance(item,dict) or set(item) != {'url','merge_commit','merged_at'}:
                result['reason']='closure_receipt_metadata';return result
            validated=merged_proof(item.get('url'),{'url':item.get('url'),'state':'MERGED','mergedAt':item.get('merged_at'),'mergeCommit':{'oid':item.get('merge_commit')}})
            if validated != item:
                result['reason']='closure_receipt_metadata';return result
            old_proofs.append(item)
        if evidence_key(kt,t,old_proofs) != previous['delivery']:
            result['reason']='closure_receipt_metadata';return result
        if previous['delivery'] == key:
            result['reason'] = 'reopened_same_delivery'
            return result
    if reason is None:
        try:
            handback = kt.handback_module()
            args = completion_args(t)
            empty=reviewed_empty(kt,data,t,info)
            expected = handback.digest(handback.completion_projection(kt, data, t, args.note,reviewed_empty=empty))
            handback.guard_completion(kt, data, t, expected, args,reviewed_empty=empty)
        except SystemExit:
            result['reason'] = 'native_completion_guard'
            return result
    result.update(action='ask' if reason == 'open_todo' else 'close', reason=reason or 'all_proven', evidence=proof, delivery=key)
    return result


def question_payload(kt, tid, prs):
    # Stable per delivery identity, never per date or transient reason/status.
    request = 'close_' + digest({'board': board(kt), 'card_id': tid, 'prs': prs})[:24]
    return {'version': 1, 'request_id': request, 'question': 'Review the remaining work?',
            'waiting': 'Merged work has an unfinished checklist; the card stays open.',
            'viewpoints': [{'who': 'Owner', 'wants': 'An accurate board'}, {'who': 'Maintainer', 'wants': 'Remaining work retained'}],
            'options': [{'key': 'review', 'label': 'Review remaining work', 'score': 9, 'reason': 'Keep unfinished work explicit', 'basis': 'judgement'},
                        {'key': 'leave', 'label': 'Leave open', 'score': 7, 'reason': 'Retain the current checklist', 'basis': 'judgement'}],
            'recommended': 'review', 'recommendation_reason': 'A merge cannot finish unchecked work.',
            'next_step': 'Review the checklist; this answer grants no permission and starts no work.'}


def completed_retry(kt,data,t,expected,proposals,owner):
    record=t.get('close_evidence')
    if not isinstance(record,dict) or set(record)!={'version','delivery','evidence','snapshot','post_snapshot','owner','completed_at'} or type(record.get('version')) is not int or record['version']!=1:
        return False
    if t.get('column')!='done' or t.get('outcome')!='completed' or t.get('claim') is not None or t.get('waiting') is not None or question_state(kt,t,proposals,owner)[0] is not None:
        return False
    return record.get('delivery')==expected['delivery'] and record.get('snapshot')==expected['snapshot'] and record.get('evidence')==expected['evidence'] and record.get('owner')==owner and record.get('post_snapshot')==snapshot(kt,data,t,proposals)


def run(kt, a):
    writing = not getattr(a, 'dry_run', False)
    preflight(kt, writing)
    data, _ = kt.load()
    kt.require_review_storage(data)
    owner = kt.quiet_claim_setting_owner(data)
    enabled = isinstance(data.get('settings'), dict) and data['settings'].get('reconcile_close_proven') is True
    if writing and not enabled:
        refuse('reconcile_close_proven is off; a person owner enables it after reviewing the dry run')
    if writing and not valid_activation(data,owner):refuse('reviewed-report enablement receipt is missing or invalid')
    deadline = time.monotonic() + DEADLINE
    context = ProposalContext(kt, data, deadline)
    proposals = context.existing(data)
    view = context.view(kt)
    tasks = data.get('tasks')
    if not isinstance(tasks, list):refuse('card index needs repair')
    ids = [t.get('id') for t in tasks if isinstance(t, dict)]
    if any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)):refuse('card identities are ambiguous')
    identities = set()
    for t in tasks:
        reason, info = eligibility(kt, data, t, proposals)
        if info and reason in (None, 'open_todo'):
            identities.update(info['prs'])
    proofs = read_proofs(kt, sorted(identities),deadline=deadline)
    planned = [row(view, data, t, proposals, proofs) for t in tasks]
    if not writing:
        token=report_digest(kt,data,context)
        print(json.dumps({'version': 1, 'enabled': enabled, 'report_digest':token,'rows': planned}) if getattr(a, 'json', False) else 'reviewed report '+token+'\n'+'\n'.join(str(r['card_id']) + ' ' + r['action'] + ' ' + str(r['reason']) for r in planned))
        return
    targets = {r['card_id']: r for r in planned if r['action'] in ('close', 'ask')}
    transactions = {}
    for tid, r in targets.items():
        if r['action'] == 'ask':
            args = type('QuestionArgs', (), {'id': tid})()
            transactions[tid] = kt.owner_question_module().prepare_transaction(kt, args, question_payload(kt, tid, r['prs']), existing_index=lambda data: context.existing(data))
    outcomes = []
    calls = 0
    class RefreshEvidence(Exception):
        pass
    def change(current):
        nonlocal calls
        calls += 1
        if calls > 1:
            # The storage adapter observed a CAS conflict. Leave its retry and re-read
            # authenticated evidence outside its critical section before trying again.
            raise RefreshEvidence()
        kt._MUT['recheck'] = True
        if kt.quiet_claim_setting_owner(current) != owner or not isinstance(current.get('settings'), dict) or current['settings'].get('reconcile_close_proven') is not True or not valid_activation(current,owner):
            refuse('owner or opt-in changed')
        if not context.matches(kt, current):
            raise RefreshEvidence()
        current_proposals = context.existing(current)
        current_view = context.view(kt)
        # Validate every selected candidate before any mutation; a failed candidate aborts all.
        ready = []
        for tid, expected in targets.items():
            t = get_task(kt, current, tid)
            if expected['action']=='close' and completed_retry(current_view,current,t,expected,current_proposals,owner):
                ready.append((t,dict(expected,already=True)))
                continue
            if expected['action']=='ask':
                request=question_payload(kt,tid,expected['prs'])['request_id']
                records=t.get('owner_questions',{})
                if isinstance(records,dict) and kt.owner_question_module().digest(request) in records:
                    # The canonical seam verifies the full existing question/comment/receipt
                    # and owner scope. Return that saved fact; it grants no new authority.
                    callback,answer=transactions[tid]
                    callback(current)
                    if answer.get('created') is not False:refuse('recorded question did not coalesce')
                    ready.append((t,dict(expected,already=True,proposal_id=answer['proposal_id'])))
                    continue
            actual = row(current_view, current, t, current_proposals, proofs)
            if actual != expected:
                refuse('candidate changed; rerun the strict dry run')
            ready.append((t, actual))
        outcomes.clear()
        for t, r in ready:
            if r.get('already'):
                outcome={'card_id':t['id'],'action':r['action'],'already':True}
                if r['action']=='ask':outcome['proposal_id']=r['proposal_id']
                outcomes.append(outcome)
                continue
            if r['action'] == 'ask':
                callback, answer = transactions[t['id']]
                callback(current)
                outcomes.append({'card_id': t['id'], 'action': 'ask', 'proposal_id': answer['proposal_id']})
            else:
                handback = kt.handback_module()
                args = completion_args(t)
                empty=reviewed_empty(current_view,current,t,r)
                expected = handback.digest(handback.completion_projection(current_view, current, t, args.note,reviewed_empty=empty))
                handback.guard_completion(current_view, current, t, expected, args,reviewed_empty=empty)
                kt.apply_completed_model(current, t, args, args.note, guarded=True)
                t['close_evidence'] = {'version': 1, 'delivery': r['delivery'], 'evidence': copy.deepcopy(r['evidence']), 'snapshot': r['snapshot'], 'post_snapshot':snapshot(kt,current,t,current_proposals), 'owner': owner, 'completed_at': kt.now()}
                outcomes.append({'card_id': t['id'], 'action': 'close'})
        if ready:current['settings']['min_kit'] = max(kt.board_min_kit(current), KIT)
    if targets:
        for attempt in range(4):
            calls = 0
            try:
                kt.mutate(change, 'Reconcile proven completed cards and retain mixed work')
                break
            except RefreshEvidence:
                if attempt == 3 or time.monotonic() >= deadline:
                    refuse('concurrent updates exceeded the proof retry budget')
                # Semantic changes still refuse in the callback; unrelated changes may
                # proceed only with complete newly fetched merge proofs.
                refreshed, _ = kt.load()
                context = ProposalContext(kt, refreshed, deadline)
                proofs = read_proofs(kt, sorted(identities), deadline=deadline)
    print(json.dumps({'version': 1, 'outcomes': outcomes}))
