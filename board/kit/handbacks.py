"""Snapshot-bound follow-up moves and guarded completion. Receipts are data, never authority."""
import copy
import contextlib
import datetime as dt
import io
import hashlib
import json
import os
import re
import unicodedata
import urllib.parse

KIT = 144
GUARDED_NOTE = 8192
TASK = re.compile(r"t_[a-z0-9]{4,20}\Z")
TODO = re.compile(r"d_[a-z0-9]{4,20}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
KINDS = ("rollout", "device", "owner-decision")
MAX_BYTES = 16384
MAX_RECEIPTS = 64
MAX_RECEIPT_BYTES = 65536


def question_settled(kt,proposal,owner):
    """Factual native question lifecycle only. This never authorises the answer's external effects."""
    try:
        if not isinstance(proposal,dict) or proposal.get("kind") not in kt.ASK_KINDS or proposal.get("status")!="answered":return False
        decision=proposal.get("decision");change=proposal.get("change")
        if not isinstance(owner,str) or not owner or not isinstance(decision,dict) or not isinstance(change,dict) \
                or decision.get("action")!="answer" or not isinstance(decision.get("id"),str) or not re.fullmatch(r"a_[a-f0-9]{10}",decision["id"]):return False
        decider=proposal.get("decider") or owner
        if not isinstance(decider,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",decider):return False
        creator=proposal.get("createdBy");answered_by=decision.get("by");done=decision.get("done")
        if not isinstance(creator,str) or not isinstance(answered_by,str) or not answered_by or not isinstance(done,dict) \
                or not {"at","by"}<=set(done) or set(done)-{"at","by","acted","note"} \
                or "acted" in done and done["acted"] is not False or not isinstance(done.get("by"),str):return False
        agent_creator="@" in creator and creator.rsplit("@",1)[1].casefold()==owner.casefold()
        if answered_by.casefold()==decider.casefold():
            if "relayed" in decision:return False
        else:
            relayed=decision.get("relayed")
            if decider.casefold()!=owner.casefold() or not agent_creator or answered_by!=creator or not isinstance(relayed,dict) or set(relayed)!={"for","via"} \
                    or not isinstance(relayed.get("for"),str) or relayed["for"].casefold()!=owner.casefold() \
                    or not isinstance(relayed.get("via"),str) or not relayed["via"] or len(relayed["via"])>kt.RELAY_VIA_LIMIT \
                    or not kt.RELAY_VIA_RE.fullmatch(relayed["via"]) or proposal["kind"]=="ask.approve":return False
        if done["by"].casefold()!=decider.casefold() and not (agent_creator and done["by"]==creator):return False
        def stamp(value):
            if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)",value):raise ValueError()
            return dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        if not stamp(decision.get("at"))<=stamp(done["at"])<=stamp(kt.now()):return False
        if "note" in done:text(done["note"],300)
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):kt.check_stored_change(proposal)
        answer=decision.get("answer")
        if not isinstance(answer,dict) or not answer or set(answer)-{"choice","other","approved","text","note"}:return False
        if "approved" in answer and type(answer["approved"]) is not bool:return False
        for key in ("choice","other","text","note"):
            if key in answer:text(answer[key],300)
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            canonical=kt.ask_answer(proposal,choose=answer.get("choice"),other=answer.get("other"),approve=answer.get("approved"),text=answer.get("text"),note=answer.get("note"))
        if canonical!=answer:return False
        if proposal["kind"]=="ask.approve" and answer.get("approved") is not True and done.get("acted") is not False:return False
        return True
    except (SystemExit,TypeError,ValueError,KeyError,AttributeError,OverflowError,RecursionError):
        return False




def refuse(message):
    raise SystemExit("handback: " + message)


def encoded(value):
    try:
        out = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        refuse("snapshot is not bounded UTF-8 data")
    if len(out) > MAX_BYTES:
        refuse("snapshot exceeds its byte budget")
    return out


def digest(value):
    return hashlib.sha256(b"keeptrack-handback-v1\0" + encoded(value)).hexdigest()


def emit(value):
    print(encoded(value).decode("utf-8"))


def text(value, cap, optional=False, multiline=False):
    if not isinstance(value, str) or len(value) > cap or (not optional and not value.strip()):
        refuse("text is missing or exceeds its limit")
    try:value.encode("utf-8", "strict")
    except UnicodeError:refuse("text is not UTF-8")
    if any((unicodedata.category(c).startswith("C") and not (multiline and c in "\n\t")) or c in "\u2028\u2029" for c in value):
        refuse("text contains unsupported characters")
    return value


def screen(kt, value):
    pending, strings = [value], []
    while pending:
        item = pending.pop()
        if isinstance(item, dict):pending.extend(item.values())
        elif isinstance(item, list):pending.extend(item)
        elif isinstance(item, str):
            strings.append(unicodedata.normalize("NFKC", item))
            if "://" in item:strings.append(unicodedata.normalize("NFKC",urllib.parse.unquote(item)))
    policy = kt.owner_question_module()
    # Separate fields cannot supply incidental assignment punctuation inside a URL/repo/column. Other privacy
    # patterns still see cross-field context; secret assignments require explicit key/operator/value boundaries.
    joined=[" ".join(order) for order in (strings,reversed(strings))]
    secret=r"(?:password|passphrase|api[_ -]?key|secret|token|credential)"
    operator=r"(?:(?:is|was|are)\b|[:=,\-–—])"
    label=re.compile(r"("+secret+r")(?:\s*("+operator+r"))?\s*",re.I)
    prefix=re.compile(r"^\s*("+operator+r")\s*(.*)$",re.I|re.S)
    labels=[]
    for index,string in enumerate(strings):
        match=label.fullmatch(string.strip())
        if match:labels.append((match[1],match[2],{index}))
    api=[i for i,value in enumerate(strings) if value.strip().casefold()=="api"]
    for i in api:
        for j,value in enumerate(strings):
            if i==j:continue
            if value.strip().casefold()=="key":labels.append(("API key",None,{i,j}))
            elif value.strip().casefold().startswith("key"):
                tail=prefix.match(value.strip()[3:])
                if tail:
                    if tail[2].strip():refuse("copied content failed the board privacy screen")
                    labels.append(("API key",tail[1],{i,j}))
    split_secret=False
    for key,op,used in labels:
        for index,string in enumerate(strings):
            if index in used or not string.strip():continue
            if op and policy.BOARD_PRIVATE.search(key+" "+op+" "+string):split_secret=True
            tail=prefix.match(string)
            if not op and tail:
                if tail[2].strip() and policy.BOARD_PRIVATE.search(key+" "+string):split_secret=True
                elif not tail[2].strip() and any(j not in used|{index} and value.strip() for j,value in enumerate(strings)):
                    split_secret=True
    cross_other=any(not re.match(secret+r"\b",match.group(),re.I) for value in joined for match in policy.BOARD_PRIVATE.finditer(value))
    blob=any(any(c.isdigit() for c in match.group()) and not (re.fullmatch(r"[0-9a-f]{40}",match.group()) and re.search(r"\b(?:commit|sha|sha-?1)[:\s]\s{0,2}$",line[max(0,match.start()-12):match.start()],re.I))
             for line in strings for match in re.finditer(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/=]{40,}",line))
    if kt.work_module().private_text(strings) or any(policy.BOARD_PRIVATE.search(value) or policy.PRIVATE_NEIGHBOURS.search(value) for value in strings) \
            or any(policy.PRIVATE_NEIGHBOURS.search(value) for value in joined) or cross_other or split_secret or blob:
        refuse("copied content failed the board privacy screen")




def preflight(kt):
    if kt.BACKEND == "hosted" and not kt.FILE:
        refuse("capability_unavailable: safe handbacks are unavailable in hosted phase 0")
    if os.environ.get("KEEPTRACK_PROPOSALS_ONLY") == "1":
        refuse("KEEPTRACK_PROPOSALS_ONLY: safe handbacks mutate cards")


def task(kt, data, tid, allow_done=False):
    if not isinstance(tid, str) or not TASK.fullmatch(tid):
        refuse("a stable source card ID is required")
    matches = [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id") == tid]
    if len(matches) != 1:refuse("source is missing, archived or ambiguous")
    t = matches[0]
    model_fields(t)
    if "coordination" in t:refuse("coordinated tasks require their existing completion protocol")
    if data.get("version") != 4 or data.get("layout") != "split":refuse("safe handbacks require schema4 split storage")
    if (t.get("column") == "done" and not allow_done) or t.get("archived") or t.get("outcome") == "cancelled":
        refuse("source must be an open card")
    return t


def model_fields(t):
    for field,cap in (("comments",1024),("history",4096),("related",256)):
        values=t.get(field,[])
        if not isinstance(values,list) or len(values)>cap or any(not isinstance(value,dict) for value in values):
            refuse("card history, comment or relation shape needs repair")
    if type(t.get("num")) is not int or t["num"]<=0:refuse("card display identity needs repair")


def item(t, did):
    if not isinstance(did, str) or not TODO.fullmatch(did):refuse("a stable to-do ID is required")
    values = t.get("todos")
    if not isinstance(values, list) or len(values) > 200 or not all(isinstance(v, dict) for v in values):
        refuse("source checklist needs repair")
    ids = [v.get("id") for v in values]
    if any(not isinstance(x, str) or not TODO.fullmatch(x) for x in ids) or len(ids) != len(set(ids)):
        refuse("source checklist IDs must be unique and stable")
    matches = [(n, value) for n, value in enumerate(values, 1) if value.get("id") == did]
    if len(matches) != 1:refuse("selected to-do is missing")
    return matches[0]


def questions(kt, data, tid):
    try:proposals = kt._all_proposals(data)
    except (ValueError, TypeError, AttributeError):refuse("Inbox identity needs repair")
    if not isinstance(proposals, list) or len(proposals) > 4096:refuse("Inbox exceeds the guarded lookup budget")
    source=next(t for t in data["tasks"] if isinstance(t,dict) and t.get("id")==tid)
    records=source.get("owner_questions",{})
    if not isinstance(records,dict) or len(records)>256 or any(not isinstance(record,dict) or not isinstance(record.get("proposal_id"),str) for record in records.values()):
        refuse("owner-question bindings need repair")
    bound_ids={record["proposal_id"] for record in records.values()}
    found_ids=set()
    result = []
    for proposal in proposals:
        if not isinstance(proposal, dict):refuse("Inbox identity needs repair")
        if proposal.get("id") is not None and not isinstance(proposal.get("id"),str):refuse("Inbox identity needs repair")
        change = proposal.get("change")
        if proposal.get("id") in bound_ids or isinstance(change, dict) and change.get("task") == tid and proposal.get("kind") in kt.ASK_KINDS:
            if proposal.get("id") in found_ids:refuse("owner-question identity is ambiguous")
            found_ids.add(proposal.get("id"))
            if proposal.get("kind") not in kt.ASK_KINDS:refuse("owner-question kind changed")
            result.append({**{k: proposal.get(k) for k in ("id", "kind", "status", "decider")},"change_digest":digest(change),
                           "decision_digest":digest(proposal.get("decision")),"settled":question_settled(kt,proposal,kt.quiet_claim_setting_owner(data))})
    if not bound_ids<=found_ids:refuse("a recorded owner question is missing")
    result.sort(key=lambda p: str(p.get("id")))
    return result




def source_projection(kt, data, t):
    metadata = {"id":t["id"], "title":text(t.get("title"),160), "client":text(t.get("client", ""),100,True),
                "project":text(t.get("project", ""),100,True), "priority":t.get("priority", "medium"), "column":text(t.get("column"),60)}
    if metadata["priority"] not in ("high","medium","low"):refuse("source priority needs repair")
    for field, cap, count in (("labels",46,32),("assignees",100,20)):
        values=t.get(field,[])
        if not isinstance(values,list) or len(values)>count:refuse("source copied metadata needs repair")
        metadata[field]=[text(x,cap) for x in values]
    claim=t.get("claim")
    if claim is not None and not isinstance(claim,dict):refuse("claim metadata needs repair")
    # Heartbeat movement is not a semantic change; the actual session proof remains local and authoritative.
    public_claim = {k:claim.get(k) for k in ("generation","agent","on_behalf_of","status","claimed_at")} if claim else None
    if public_claim:
        for key,value in public_claim.items():
            if value is not None:text(value,100)
    links=t.get("links",[])
    if not isinstance(links,list) or len(links)>100 or any(not isinstance(x,dict) for x in links):refuse("source links need repair")
    link_values=[]
    for link in links:
        link_values.append({"url":text(link.get("url"),2000),"title":text(link.get("title",""),160,True)})
    value={"version":1,"board":{"repo":text(kt.REPO,200,True),"branch":text(kt.BRANCH,255),"path":text(kt.PATH,1024),"local":bool(kt.FILE)},
           "owner":kt.quiet_claim_setting_owner(data),"source":metadata,"claim":public_claim,
           "waiting":digest(t["waiting"]) if t.get("waiting") is not None else None,"questions":questions(kt,data,t["id"]),"links":link_values}
    screen(kt,{"source":metadata,"claim":public_claim,"links":link_values,"board":value["board"],"owner":value["owner"]})
    if kt.FILE:value["board"]["file_digest"]=hashlib.sha256(os.fsencode(os.path.realpath(kt.FILE))).hexdigest()
    encoded(value)
    return value


def request(a):
    kind=getattr(a,"handback_kind",None) or "rollout"
    if kind not in KINDS:refuse("unknown handback kind")
    return {"title":text(getattr(a,"title",None) or "",160,True),
            "details":text(getattr(a,"details",None) or "",1500,True,multiline=True),"kind":kind}


def move_projection(kt,data,t,d,a):
    value=source_projection(kt,data,t)
    if type(d.get("done")) is not bool or d["done"]:refuse("selected to-do is already done")
    value.update(todo={"id":d["id"],"text":text(d.get("text"),300),"done":False},request=request(a))
    screen(kt,{"source":value["source"],"todo":value["todo"],"request":value["request"],"links":value["links"]})
    encoded(value)
    return value


def links(kt,t,o):
    if kt.FILE:return None,None
    return kt.card_url(t["num"],t["id"]),kt.card_url(o["num"],o["id"])


def verify_pair(kt,data,t,d,record,a,check_source=True):
    if not isinstance(record,dict) or set(record)!={"version","snapshot","projection","destination","copied_digest","comments"} or type(record.get("version")) is not int or record.get("version")!=1:
        refuse("move receipt needs repair; never recreate an uncertain pair")
    projection=record["projection"]
    if not isinstance(projection,dict) or set(projection)!={"version","board","owner","source","claim","waiting","questions","links","todo","request"} \
            or not isinstance(projection.get("todo"),dict) or set(projection["todo"])!={"id","text","done"} \
            or not isinstance(projection.get("source"),dict) or not isinstance(projection.get("links"),list) \
            or any(not isinstance(link,dict) or set(link)!={"url","title"} or not all(isinstance(v,str) for v in link.values()) for link in projection["links"]) \
            or not isinstance(record.get("snapshot"),str) or not DIGEST.fullmatch(record["snapshot"]) \
            or not isinstance(record.get("copied_digest"),str) or not DIGEST.fullmatch(record["copied_digest"]) \
            or not isinstance(record.get("destination"),str) or not TASK.fullmatch(record["destination"]) \
            or digest(projection)!=record["snapshot"] or projection.get("request")!=request(a):
        refuse("retry content differs or its receipt is inconsistent")
    if projection.get("todo",{}).get("id")!=d["id"] or projection.get("source",{}).get("id")!=t["id"]:
        refuse("move receipt has a different source")
    current=source_projection(kt,data,t)
    # Native move adds its follow-up link; otherwise a retry must retain the screened source/scope.
    oldlinks=projection.get("links")
    added_links=[]
    for other in t.get("todos",[]):
        receipt=other.get("handback") if isinstance(other,dict) else None
        if not isinstance(receipt,dict):continue
        destinations=[x for x in data.get("tasks",[]) if isinstance(x,dict) and x.get("id")==receipt.get("destination")]
        if len(destinations)==1:
            destination=destinations[0]
            relation=kt.relation(t,destination["id"])
            if relation and relation.get("kind")=="related" and relation.get("from")==t["id"] and relation.get("status")=="confirmed":
                if not kt.FILE:added_links.append({"url":kt.card_url(destination["num"],destination["id"]),"title":f"Follow-up #{destination['num']}"})
    current["links"]=[x for x in current["links"] if x not in added_links or x in oldlinks]
    expected=copy.deepcopy(projection);expected.pop("todo",None);expected.pop("request",None)
    expected["links"]=oldlinks
    if check_source and current!=expected:refuse("source scope or claim changed since the move")
    matches=[x for x in data.get("tasks",[]) if isinstance(x,dict) and x.get("id")==record["destination"]]
    if len(matches)!=1 or matches[0].get("archived"):refuse("recorded follow-up is missing or archived; never recreate it")
    o=matches[0]
    model_fields(o)
    if not isinstance(o.get("links",[]),list) or any(not isinstance(link,dict) for link in o.get("links",[])):
        refuse("follow-up links need repair")
    if "coordination" in o:refuse("recorded follow-up changed completion protocol")
    copied={key:o.get(key) for key in ("title","client","project","priority","labels","assignees","details","todos")}
    if digest(copied)!=record["copied_digest"]:refuse("recorded follow-up content changed; never recreate it")
    original=projection["todo"]["text"]
    if d.get("done") is not True or d.get("text")!=f"Moved to #{o['num']} ({o['id']}): {original}":refuse("source move marker changed")
    for left,right in ((t,o),(o,t)):
        relation=kt.relation(left,right["id"])
        if not relation or relation.get("kind")!="related" or relation.get("from")!=t["id"] or relation.get("status")!="confirmed":refuse("follow-up relation changed")
    source_url,destination_url=links(kt,t,o)
    for left,target,url,title in ((t,o,destination_url,f"Follow-up #{o['num']}"),(o,t,source_url,f"Split from #{t['num']}")):
        if url and not any(x.get("url")==url and x.get("title")==title for x in left.get("links",[]) if isinstance(x,dict)):refuse("follow-up link changed")
    comments=record.get("comments")
    if not isinstance(comments,list) or len(comments)!=2 or any(not isinstance(comment,dict) for comment in comments):refuse("move comment receipt needs repair")
    for card,expected_comment in zip((t,o),comments):
        actual=[x for x in card.get("comments",[]) if isinstance(x,dict) and x.get("id")==expected_comment.get("id")]
        if len(actual)!=1 or actual[0]!=expected_comment:refuse("move comment changed")
    screen(kt,copied)
    return o


def result(kt,t,d,o,created):
    source_url,destination_url=links(kt,t,o)
    value={"source_id":t["id"],"todo_id":d["id"],"destination_id":o["id"],"created":created,
            "source_url":source_url,"destination_url":destination_url}
    encoded(value)  # Validate the exact receipt before a mutation callback may commit it.
    return value


def move(kt,a):
    preflight(kt);req=request(a)
    if not getattr(a,"json",False):refuse("safe move requires --json")
    expected=getattr(a,"expected_snapshot",None)
    if expected is not None and (not isinstance(expected,str) or not DIGEST.fullmatch(expected)):refuse("expected snapshot must be a digest")
    if bool(getattr(a,"snapshot",False))==bool(expected):refuse("choose exactly one snapshot read or expected-snapshot write")
    def locate(data):
        t=task(kt,data,a.id);n,d=item(t,a.n)
        return t,n,d
    if a.snapshot:
        data,_=kt.load();t,n,d=locate(data)
        record=d.get("handback")
        if record is not None:
            o=verify_pair(kt,data,t,d,record,a,check_source=False)
            emit({"version":1,"snapshot":record["snapshot"],"projection":record["projection"],"existing":result(kt,t,d,o,False)});return
        projection=move_projection(kt,data,t,d,a)
        emit({"version":1,"snapshot":digest(projection),"projection":projection,"existing":None});return
    answer={}
    def change(data):
        kt._MUT["recheck"]=True
        t,n,d=locate(data)
        record=d.get("handback")
        if record is not None:
            o=verify_pair(kt,data,t,d,record,a)
            if record["snapshot"]!=expected:refuse("retry snapshot differs")
            answer.clear();answer.update(result(kt,t,d,o,False));return
        projection=move_projection(kt,data,t,d,a)
        if digest(projection)!=expected:refuse("source snapshot changed; read and screen it again")
        kt.claim_owner_check(data,t,a,"done")
        if not any(isinstance(c,dict) and c.get("id")=="backlog" for c in data.get("columns",[])):refuse("a Backlog column is required; never substitute To do")
        o=kt.apply_todo_move(data,t,n,d,req["title"],req["details"])
        copied={key:o.get(key) for key in ("title","client","project","priority","labels","assignees","details","todos")}
        d["handback"]={"version":1,"snapshot":expected,"projection":projection,"destination":o["id"],"copied_digest":digest(copied),
                       "comments":[copy.deepcopy(t["comments"][-1]),copy.deepcopy(o["comments"][-1])]}
        receipts=[value["handback"] for value in t["todos"] if "handback" in value]
        if len(receipts)>MAX_RECEIPTS or sum(len(encoded(value)) for value in receipts)>MAX_RECEIPT_BYTES:
            refuse("move receipt capacity is reached; no pair was created")
        data.setdefault("settings",{})["min_kit"]=max(kt.board_min_kit(data),KIT)
        answer.clear();answer.update(result(kt,t,d,o,True))
    kt.mutate(change,"Move a snapshot-bound follow-up to Backlog")
    emit(answer)


def completion_projection(kt,data,t,note,*,reviewed_empty=False):
    if type(reviewed_empty) is not bool:refuse("reviewed-empty context must be a strict internal boolean")
    value=source_projection(kt,data,t)
    todos=t.get("todos")
    if not isinstance(todos,list) or (not todos and not reviewed_empty) or len(todos)>200:refuse("completion needs a bounded checklist and explicit review for empty criteria")
    if reviewed_empty:value["reviewed_empty"]=True
    value["todos"]=[]
    for d in todos:
        if not isinstance(d,dict):refuse("completion checklist needs repair")
        value["todos"].append({"id":d.get("id"),"text":d.get("text"),"done":d.get("done"),
                               "handback_digest":digest(d["handback"]) if "handback" in d else None})
    value["note"]=note
    encoded(value)
    return value


def guard_completion(kt,data,t,expected,a,*,reviewed_empty=False):
    """Reusable same-CAS precondition. No mutation, claim cleanup or nested save occurs here."""
    if task(kt,data,t.get("id")) is not t:refuse("completion task is not the current source")
    if not isinstance(expected,str) or not DIGEST.fullmatch(expected):refuse("expected completion snapshot must be a digest")
    projection=completion_projection(kt,data,t,text(getattr(a,"note",None) or "",1000,multiline=True),reviewed_empty=reviewed_empty)
    if digest(projection)!=expected:refuse("completion snapshot changed; nothing closed")
    kt.claim_owner_check(data,t,a,"done")
    if t.get("column")=="pending-review":refuse("Pending review still requires the owner's decision")
    if t.get("waiting") is not None:refuse("a wait is still open; nothing closed")
    if "needs-human" in t.get("labels",[]):refuse("needs-human remains open; nothing closed")
    if any(p.get("settled") is not True for p in projection["questions"]):refuse("an owner question remains open; nothing closed")
    for d in t["todos"]:
        if not isinstance(d,dict) or d.get("done") is not True:refuse("completion has an unfinished acceptance criterion")
        if "handback" in d:
            req=d["handback"].get("projection",{}).get("request",{}) if isinstance(d["handback"],dict) else {}
            args=type("MoveArgs",(),{"title":req.get("title"),"details":req.get("details"),"handback_kind":req.get("kind")})()
            # The historical pair proves where this completed criterion went, not current permission. Current
            # source/claim/blockers were independently bound and checked above by the fresh completion snapshot.
            verify_pair(kt,data,t,d,d["handback"],args,check_source=False)
        elif kt.MOVED_TODO.match(str(d.get("text",""))):refuse("moved acceptance criterion lacks a verified receipt")
    return projection


def completed_retry(kt,data,t,expected,note):
    record=t.get("guarded_completion")
    projection=completion_projection(kt,data,t,note)
    if not isinstance(record,dict) or set(record)!={"version","snapshot","note_digest","post_digest"} or type(record.get("version")) is not int or record.get("version")!=1 \
            or record.get("snapshot")!=expected or record.get("note_digest")!=digest(note) or record.get("post_digest")!=digest(projection) \
            or t.get("column")!="done" or t.get("outcome")!="completed" or t.get("claim") is not None or t.get("waiting") is not None:
        refuse("completed outcome cannot be verified; nothing changed")
    for d in t.get("todos",[]):
        if isinstance(d,dict) and "handback" in d:
            record=d["handback"]
            req=record.get("projection",{}).get("request",{}) if isinstance(record,dict) else {}
            args=type("MoveArgs",(),{"title":req.get("title"),"details":req.get("details"),"handback_kind":req.get("kind")})()
            verify_pair(kt,data,t,d,record,args,check_source=False)
    return projection


def done(kt,a):
    preflight(kt)
    if getattr(a,"cancel",False):refuse("guarded completion cannot cancel")
    if not getattr(a,"json",False):refuse("guarded completion requires --json")
    expected=getattr(a,"expected_snapshot",None)
    if bool(getattr(a,"snapshot",False))==bool(expected):refuse("choose exactly one completion snapshot read or expected-snapshot write")
    note=text(getattr(a,"note",None) or "",1000,multiline=True)
    screen(kt,[note])
    if a.snapshot:
        data,_=kt.load();t=task(kt,data,a.id,allow_done=True)
        if t.get("column")=="done":
            record=t.get("guarded_completion")
            projection=completed_retry(kt,data,t,record.get("snapshot") if isinstance(record,dict) else None,note)
            emit({"version":1,"snapshot":record["snapshot"],"projection":projection,"existing":{"card_id":t["id"],"closed":True}});return
        projection=completion_projection(kt,data,t,note)
        screen(kt,{"source":projection["source"],"links":projection["links"],"note":note})
        emit({"version":1,"snapshot":digest(projection),"projection":projection,"existing":None});return
    kt._claim_sure()
    answer={}
    def change(data):
        kt._MUT["recheck"]=True
        t=task(kt,data,a.id,allow_done=True)
        if t.get("column")=="done":
            completed_retry(kt,data,t,expected,note)
            answer.clear();answer.update(card_id=t["id"],closed=True);return
        guard_completion(kt,data,t,expected,a)
        kt.apply_completed_model(data,t,a,note,guarded=True)
        t["guarded_completion"]={"version":1,"snapshot":expected,"note_digest":digest(note),"post_digest":digest(completion_projection(kt,data,t,note))}
        data.setdefault("settings",{})["min_kit"]=max(kt.board_min_kit(data),KIT)
        answer.clear();answer.update(card_id=t["id"],closed=True)
    kt.mutate(change,"Complete a snapshot-guarded card")
    emit(answer)
