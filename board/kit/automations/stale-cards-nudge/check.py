"""stale-cards-nudge check: list cards whose claim went STALE (or stuck/blocked) and still need a person.

Cheap and offline: it reads the local board through board/keeptrack.py (file mode, never the GitHub API) and
uses no model. Rules, in order:
  1. Only open cards (not in `done`) with a claim the board would show as stale, stuck or blocked count.
     "Stale" uses the board's own setting, settings.stale_after_minutes (default 30; an attended claim 12 hours),
     the same value keeptrack.py uses for STALE.
  2. Skip a card that is waiting (an open `waiting`), or labelled `held`.
  3. Skip a card nudged this ISO week: the seen log (key = card id, rev = week), a nudge proposal from this pack
     already pending in the Review Inbox or added this week, or a comment posted this week after the claim went stale
     (stuck or blocked: after the agent set that status, its last heartbeat; with no claim time, the history line
     that set the status). Comments by the claim's own agent never count: an agent that sets blocked also comments
     to ask for a person, and that is not a nudge.
  4. A card the check cannot read (no usable id, a broken claim time, a stuck or blocked claim with no time at all)
     is never dropped silently: one item `check:malformed-cards` per week asks the agent to raise it with the owner.
Output is one keeptrack-check/1 object; titles are fixed text and refs are card ids, never card text.
"""
import contextlib, datetime, importlib.util, io, json, os, re, sys
from pathlib import Path

DEFAULT_STALE = 30            # keeptrack.py's default for settings.stale_after_minutes
ATTENDED_STALE = 12 * 60      # keeptrack.py ATTENDED_STALE_MINUTES
HOLD_LABELS = {"held"}
TOKEN = re.compile(r"[A-Za-z0-9_./+=:-]{1,256}")
MALFORMED_KEY = "check:malformed-cards"
TITLES = {"stale": "Stale claim on a card", "stuck": "Stuck claim on a card", "blocked": "Blocked claim on a card"}


def emit(items=None, more=False, cursor=None, note=None):
    print(json.dumps(dict(schema="keeptrack-check/1", items=items or [], more=more, cursor=cursor, note=note)))


def state():
    try:
        value = json.loads(Path(os.environ["KEEPTRACK_STATE"]).read_text())
        return value if isinstance(value, dict) else {}
    except (KeyError, OSError, ValueError):
        return {}


def parse_time(value):
    """An ISO timestamp as an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)).astimezone(datetime.timezone.utc)


def stale_minutes(settings):
    """settings.stale_after_minutes when it is a whole number keeptrack.py accepts (5 to 1440), else the default."""
    v = (settings or {}).get("stale_after_minutes") if isinstance(settings, dict) else None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return v if isinstance(v, int) and not isinstance(v, bool) and 5 <= v <= 24 * 60 else DEFAULT_STALE


def week_of(t):
    return t.strftime("%G-W%V")


def load_board(root):
    """The board as keeptrack.py loads it (flat or split layout), read from local files only."""
    cli = root / "board" / "keeptrack.py"
    if not cli.is_file() or not (root / "board" / "tasks.json").is_file():
        return None, None
    spec = importlib.util.spec_from_file_location("stale_nudge_board", cli)
    kt = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(kt)
        # Force local read-only loading; a check must never fall back to GitHub credentials.
        kt.FILE = str(root / "board" / "tasks.json")
        data = kt.load()[0] if hasattr(kt, "load") else kt.load_board()
    return kt, data


def open_wait(kt, t):
    if hasattr(kt, "open_waiting"):
        return kt.open_waiting(t)
    w = t.get("waiting")
    return w if isinstance(w, dict) and w and t.get("column") != "done" else None


def status_set_at(t, status):
    """When the card's history last recorded the claim moving to `status` ("status blocked[: note]"), or None."""
    when = None
    for h in t.get("history") or [] if isinstance(t, dict) else []:
        text = h.get("text") if isinstance(h, dict) else None
        if isinstance(text, str) and re.match(r"status " + status + r"(?::|$)", text):
            when = parse_time(h.get("at")) or when
    return when


def claim_status(claim, limit, now, t=None):
    """("stale"|"stuck"|"blocked"|None, went_stale_at) for a claim; raises ValueError on a broken claim."""
    if not claim:
        return None, None
    if not isinstance(claim, dict):
        raise ValueError("claim")
    status = claim.get("status")
    last = parse_time(claim.get("heartbeat_at") or claim.get("claimed_at"))
    if status in ("stuck", "blocked"):
        if claim.get("blocked_by_wait"):
            return None, None          # a claim blocked by the card's own wait: the wait rules handle it
        # With no claim time, the history line that set the status says since when; with neither, the check
        # cannot tell an earlier comment from a nudge, so the card is malformed rather than silently skipped.
        last = last or status_set_at(t, status)
        if last is None:
            raise ValueError("claim time")
        return status, last
    if status == "done":
        return None, None
    if last is None:
        raise ValueError("claim time")
    mins = ATTENDED_STALE if claim.get("attended") else limit
    went = last + datetime.timedelta(minutes=mins)
    return ("stale", went) if now > went else (None, None)


def claim_author(claim):
    """The comment author the claim's own agent writes as (keeptrack.py who_am_i: agent@user, else agent), lower-case."""
    if not isinstance(claim, dict) or not isinstance(claim.get("agent"), str) or not claim["agent"]:
        return None
    user = claim.get("on_behalf_of") if isinstance(claim.get("on_behalf_of"), str) else ""
    return (claim["agent"] + "@" + user if user else claim["agent"]).lower()


def proposal_index(data, prefix):
    """{target card id: [this pack's proposals]}, built once per run instead of once per stale card."""
    index = {}
    for p in data.get("proposals") or []:
        if not isinstance(p, dict) or not str(p.get("action_key") or "").startswith(prefix):
            continue
        target = (p.get("target") or {}).get("id") if isinstance(p.get("target"), dict) else None
        if isinstance(target, str):
            index.setdefault(target, []).append(p)
    return index


def nudged_this_week(t, proposals, week, since):
    for p in proposals.get(t.get("id"), []):
        created = parse_time(p.get("created"))
        if p.get("status") == "pending" or (created and week_of(created) == week):
            return True
    own = claim_author(t.get("claim"))
    for c in t.get("comments") or []:
        at = parse_time(c.get("at")) if isinstance(c, dict) else None
        if own and str(c.get("by") or "").lower() == own:
            continue
        if at and week_of(at) == week and (since is None or at >= since):
            return True
    return False


def main():
    root = Path.cwd()
    try:
        kt, data = load_board(root)
    except (SystemExit, Exception):  # noqa: BLE001 -- any load failure is reported as a fixed code, never as text
        emit(note="source-error"); return 2
    if data is None:
        emit(note="source-missing"); return 2
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        emit(note="source-error"); return 2
    now = datetime.datetime.now(datetime.timezone.utc)
    week = week_of(now)
    limit = stale_minutes(data.get("settings"))
    prefix = "auto:" + (os.environ.get("KEEPTRACK_AUTOMATION") or "stale-cards-nudge") + ":"
    seen = state().get("keys") or {}
    proposals = proposal_index(data, prefix)
    found, malformed = [], 0
    for t in data["tasks"]:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not TOKEN.fullmatch(t["id"]) or "://" in t["id"]:
            malformed += 1; continue
        if t.get("column") == "done":
            continue
        try:
            status, since = claim_status(t.get("claim"), limit, now, t)
        except ValueError:
            malformed += 1; continue
        if not status:
            continue
        labels = {str(x).strip().lower() for x in (t.get("labels") or []) if isinstance(x, str)}
        if labels & HOLD_LABELS or open_wait(kt, t):
            continue
        # since: when the claim went stale, or (stuck/blocked) the heartbeat that set that status
        if seen.get(t["id"]) == week or nudged_this_week(t, proposals, week, since):
            continue
        found.append((since or now, t["id"], status))
    found.sort()
    items = [dict(key=key, rev=week, title=TITLES[status], ref=key) for _, key, status in found]
    if malformed and seen.get(MALFORMED_KEY) != week:
        items.insert(0, dict(key=MALFORMED_KEY, rev=week, title="Cards the check could not read", ref="malformed-cards"))
    more = len(items) > 50
    emit(items[:50], more, items[49]["key"] if more else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
