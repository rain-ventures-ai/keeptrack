"""The only view of a message the agent reads: headers it needs, and the body as plain visible text.

Mail is written by strangers, and some of it is written for the AI that reads it: instructions hidden where a person
never sees them (HTML comments, text styled invisible, zero-width or Unicode tag characters, long encoded blobs).
`view(message)` takes gog's JSON for one message, whatever its shape, and returns

    {"headers": {...}, "auth": {"spf": .., "dkim": .., "dmarc": ..}, "text": "...", "removed": {...}, "truncated": bool}

`text` is what a person would see: the HTML part with hidden parts removed, or text/plain when there is no HTML.
Attachments and forwarded messages inside it are never read. Input is capped (MAX_MARKUP, MAX_STYLE) and no regex
runs over a style block, so crafted markup cannot make the cleaner run for long.
`removed` counts what was taken out, so the skill can say so in a proposal ("hidden content removed"). Standard
library only. Nothing here decides what is true; it only keeps the invisible out of the agent's input.
"""
import base64
import binascii
import html.parser
import re

MAX_TEXT = 8000
HEADERS = ("from", "to", "cc", "date", "subject", "reply-to", "message-id")
# Characters a reader never sees: zero-width, joiners, bidi controls and isolates, soft hyphen, BOM, blank fillers
# (Hangul, Braille, Khmer), variation selectors, interlinear annotation marks and Unicode tags.
INVISIBLE = re.compile("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e"
                       "\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff9-\ufffb"
                       "\U000e0000-\U000e007f\U000e0100-\U000e01ef]")
BLOB = re.compile(r"[A-Za-z0-9+/=_-]{80,}")
# Base64 wrapped at 76 columns (two or more full lines in a row) and hex written in spaced or colon-separated pairs.
WRAPPED = re.compile(r"(?m)(?:^[ \t]*[A-Za-z0-9+/=_-]{40,}[ \t]*(?:\n|\Z)){2,}")
HEX_PAIRS = re.compile(r"(?i)(?:[0-9a-f]{2}[ :]){30,}[0-9a-f]{2}")
MAX_MARKUP = 400_000   # longer HTML is cut before parsing: the view keeps 8000 characters anyway
MAX_STYLE = 100_000    # style text read for hiding rules, and at most MAX_RULES rules
MAX_RULES = 2000
CODE_TAGS = {"script", "style", "title"}   # hidden by nature; text in them is code or a tab title, not removed content
SKIP_TAGS = {"script", "style", "head", "title", "template", "noscript", "svg", "object", "iframe"}
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track", "param"}
TABLE = {"table", "tr", "td", "th", "thead", "tbody", "tfoot"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "pre", "section"}
NAMED = {"white": (255, 255, 255), "snow": (255, 250, 250), "ivory": (255, 255, 240), "black": (0, 0, 0)}


def _decls(text):
    """CSS declarations as {property: value}, lower case, spaces and !important removed."""
    out = {}
    for d in (text or "").split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            out[k.strip().lower()] = re.sub(r"!\s*important", "", v.strip().lower()).replace(" ", "")
    return out


def _style(attrs):
    return _decls(dict(attrs).get("style") or "")


def _num(v):
    m = re.match(r"^(-?[0-9]*\.?[0-9]+)(px|pt|em|rem|%|)$", v or "")
    return (float(m.group(1)), m.group(2)) if m else None


def _hides(s, color="", bg=""):
    """Does this set of declarations hide its text from a reader?"""
    if s.get("display") == "none" or s.get("visibility") in ("hidden", "collapse") or s.get("mso-hide") == "all":
        return True
    op = _num(s.get("opacity"))
    if op and op[0] <= 0.05:
        return True
    fs = _num(s.get("font-size"))
    if fs and (fs[0] <= 0 or (fs[1] in ("px", "pt", "") and fs[0] < 2) or (fs[1] in ("em", "rem") and fs[0] < 0.2)):
        return True   # zero or unreadably small text
    clipped = "hidden" in s.get("overflow", "")
    for k in ("max-height", "max-width") + (("height", "width") if clipped else ()):
        n = _num(s.get(k))
        if n and n[0] <= 0:
            return True
    w, h = _num(s.get("width")), _num(s.get("height"))
    if w and h and w[0] <= 0 and h[0] <= 0:
        return True   # a box with no size
    if re.match(r"rect\(0", s.get("clip", "")) or re.search(r"inset\(50%|inset\(100%|circle\(0", s.get("clip-path", "")):
        return True
    if s.get("position") in ("absolute", "fixed"):
        for k in ("left", "top", "right", "bottom", "text-indent"):
            n = _num(s.get(k))
            if n and n[0] <= -500:
                return True   # moved off the screen
    ti = _num(s.get("text-indent"))
    if ti and ti[0] <= -500:
        return True
    if re.search(r"scale\(0[,)]|scale\(0\.0", s.get("transform", "")):
        return True
    c = s.get("color") or color
    b = s.get("background-color") or s.get("background") or bg
    if c in ("transparent",) or re.fullmatch(r"rgba\([^)]*,0(\.0+)?\)", c or "") or re.fullmatch(r"#[0-9a-f]{6}00|#[0-9a-f]{3}0", c or ""):
        return True
    if c and b and c == b:
        return True   # text the same colour as its background
    rc, rb = _rgb(c), _rgb(b)
    if rc and rb and max(abs(x - y) for x, y in zip(rc, rb)) <= 16:
        return True   # text all but the same colour as its background
    if rc and min(rc) >= 0xF0 and (not b or (rb and min(rb) >= 0xF0)):
        return True   # white or near-white text on a white (default) page
    return False


def _rgb(c):
    """(r, g, b) for #rgb, #rrggbb, rgb()/rgba() and a few names; None for anything else."""
    c = (c or "").strip()
    if c in NAMED:
        return NAMED[c]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})(?:[0-9a-f]{1,2})?", c)
    if m:
        h = m.group(1)
        return tuple(int(h[i] * 2, 16) for i in range(3)) if len(h) == 3 else tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(([0-9]{1,3}),([0-9]{1,3}),([0-9]{1,3})(?:,[0-9.]+)?\)", c)
    return tuple(min(255, int(x)) for x in m.groups()) if m else None


def _hidden(tag, attrs, inherited_bg, hidden_selectors=frozenset()):
    a = {k.lower(): (v or "") for k, v in attrs}
    if "hidden" in a or a.get("aria-hidden", "").lower() == "true":
        return True
    if tag in hidden_selectors or ("#" + a.get("id", "").strip().lower()) in hidden_selectors:
        return True
    if any(("." + c.lower()) in hidden_selectors for c in a.get("class", "").split()):
        return True
    color = a.get("color", "").lower() if tag == "font" else ""
    bg = a.get("bgcolor", "").lower() or inherited_bg
    return _hides(_style(attrs), color, bg)


def _style_text(markup):
    """The text of every <style> block, found with plain string search (no regex over mail), at most MAX_STYLE."""
    low, out, pos, size = markup.lower(), [], 0, 0
    while size < MAX_STYLE:
        a = low.find("<style", pos)
        if a < 0:
            break
        b = low.find(">", a)
        e = low.find("</style", b + 1) if b >= 0 else -1
        if b < 0 or e < 0:
            break
        out.append(markup[b + 1:e]); size += e - b; pos = e + 7
    text = "".join(out)[:MAX_STYLE]
    while "/*" in text:   # drop CSS comments
        a = text.find("/*"); e = text.find("*/", a + 2)
        text = text[:a] + (text[e + 2:] if e >= 0 else "")
    return text


def _hidden_selectors(markup):
    """Simple selectors (.class, #id, tag) that a <style> block hides: `.x{display:none}` and the like."""
    found = set()
    for rule in _style_text(markup).split("}")[:MAX_RULES]:
        sel, brace, body = rule.rpartition("{")
        if not brace or not _hides(_decls(body)):
            continue
        sel = sel.rpartition("{")[2]   # inside @media: the inner selector
        for one in sel.split(","):
            last = one.strip().split()[-1].lower() if one.strip() else ""
            m = re.fullmatch(r"([a-z0-9]*)((?:[.#][a-z0-9_-]+)*)", last[:200])
            if m:
                parts = re.findall(r"[.#][a-z0-9_-]+", m.group(2))
                found.update(parts or ([m.group(1)] if m.group(1) else []))
    return frozenset(found)


class _Visible(html.parser.HTMLParser):
    def __init__(self, hidden_selectors=frozenset()):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.removed = [], [], {"html_comments": 0, "hidden_elements": 0}
        self.hidden_selectors = hidden_selectors

    def _bg(self):
        for e in reversed(self.stack):
            if e[2]:
                return e[2]
        return ""

    def _hidden_now(self):
        return any(e[1] for e in self.stack)

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self.out.append("\n")
        if tag in VOID:
            return
        s = _style(attrs)
        bg = s.get("background-color") or s.get("background") or dict(attrs).get("bgcolor", "") or ""
        hide = tag in SKIP_TAGS or _hidden(tag, attrs, self._bg(), self.hidden_selectors)
        if hide and tag not in SKIP_TAGS and not self._hidden_now():
            self.removed["hidden_elements"] += 1
        # [tag, hides, background, text in it already counted as removed]
        self.stack.append([tag, hide, bg.lower(), tag not in SKIP_TAGS or tag in CODE_TAGS])

    def handle_endtag(self, tag):
        # Close the nearest open tag of this name (mail HTML is sloppy), but never across a table cell, row or table:
        # a browser ignores `</div>` inside a cell whose div opened outside it, so a hidden block stays hidden.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
            if self.stack[i][0] in TABLE and tag not in TABLE:
                break
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._hidden_now():
            self.out.append(data)
        elif data.strip():
            # Text inside a tag a page never shows (noscript, template, svg, an iframe's fallback, text in <head>)
            # is counted once per tag, so the proposal says hidden content was removed.
            for e in self.stack:
                if e[1] and e[0] in SKIP_TAGS:
                    if not e[3]:
                        e[3] = True; self.removed["hidden_elements"] += 1
                    break

    def handle_comment(self, data):
        if not _conditional(data):
            self.removed["html_comments"] += 1

    def handle_pi(self, data):
        self.removed["html_comments"] += 1

    def unknown_decl(self, data):
        if not _conditional(data):
            self.removed["html_comments"] += 1


def _conditional(data):
    """Outlook's `<!--[if mso]>..<![endif]-->` wrappers holding only markup: in almost every mail a tool writes, so
    not counted. One that holds text (shown only in Outlook) is dropped and counted like any comment."""
    d = data.strip().lower()
    if not d.startswith(("[if", "if ", "endif", "[endif")) or len(d) > 20000:
        return False
    inner = d.split("]", 1)[1] if "]" in d else ""
    return not re.sub(r"<[^<>]*>|<!\[endif\]|&nbsp;", "", inner).strip(" >\t\r\n")


def visible_text(markup):
    """(text, removed) for an HTML body: only what a person sees."""
    markup = markup[:MAX_MARKUP]
    p = _Visible(_hidden_selectors(markup))
    try:
        p.feed(markup); p.close()
    except Exception:   # malformed beyond the parser: keep nothing rather than the raw markup
        return "", {"html_comments": 0, "hidden_elements": 1}
    return "".join(p.out), p.removed


def _decode(data):
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError, TypeError):
        return None
    return raw.decode("utf-8", errors="replace")


def _parts(node, depth=0, out=None):
    """(mimeType, decoded text) for each body part in Gmail API shape, and any decoded body string gog adds."""
    out = [] if out is None else out
    if depth > 12:
        return out
    if isinstance(node, dict):
        mime = str(node.get("mimeType") or node.get("mime_type") or "").lower()
        if (isinstance(node.get("filename"), str) and node["filename"].strip()) or mime == "message/rfc822":
            return out   # an attachment or a forwarded message inside this one: never read
        body = node.get("body")
        if isinstance(body, dict) and isinstance(body.get("data"), str) and mime.startswith("text/"):
            text = _decode(body["data"])
            if text is not None:
                out.append((mime, text))
        for key in ("body", "text", "html", "textBody", "htmlBody", "plain"):
            v = node.get(key)
            if isinstance(v, str) and v.strip():
                out.append(("text/html" if key in ("html", "htmlBody") or "<" in v else "text/plain", v))
        for k, v in node.items():
            if k not in ("headers",) and isinstance(v, (dict, list)):
                _parts(v, depth + 1, out)
    elif isinstance(node, list):
        for v in node:
            _parts(v, depth + 1, out)
    return out


def _headers(node, depth=0, out=None):
    out = {} if out is None else out
    if depth > 8:
        return out
    if isinstance(node, dict):
        name, value = node.get("name"), node.get("value")
        if isinstance(name, str) and isinstance(value, str):
            n = name.lower()
            if n in HEADERS or n == "authentication-results":
                out.setdefault(n, []).append(value)
        for k, v in node.items():
            if isinstance(k, str) and isinstance(v, str) and k.lower() in HEADERS and k.lower() not in out:
                out[k.lower()] = [v]
            elif isinstance(v, (dict, list)):
                _headers(v, depth + 1, out)
    elif isinstance(node, list):
        for v in node:
            _headers(v, depth + 1, out)
    return out


def _auth(results):
    """spf/dkim/dmarc from Gmail's own Authentication-Results, or "none". Gmail adds its line on top of any the
    sender wrote, so only the topmost header counts, and only when it is Gmail's. `(...)` comments are dropped and
    only each result's own word is read; any failing DKIM signature makes dkim "fail"."""
    found = {}
    top = results[0].lower()[:4000] if results else ""
    if not top.strip().startswith("mx.google.com"):
        return {mech: "none" for mech in ("spf", "dkim", "dmarc")}
    for _ in range(5):   # nested comments, innermost first
        top = re.sub(r"\([^()]*\)", " ", top)
    for part in top.split(";"):
        m = re.match(r"\s*(spf|dkim|dmarc)\s*=\s*([a-z]+)", part)
        if m:
            mech, res = m.groups()
            if mech not in found or (mech == "dkim" and res == "fail"):
                found[mech] = res
    return {mech: found.get(mech, "none") for mech in ("spf", "dkim", "dmarc")}


def clean(text, removed):
    # No entity decoding here: the HTML parser already turned entities into what a reader sees, and plain text shows
    # `&#8203;` as those characters, so decoding it again would make text no one saw.
    n = len(INVISIBLE.findall(text))
    if n:
        removed["invisible_characters"] = removed.get("invisible_characters", 0) + n
        text = INVISIBLE.sub("", text)
    for rx in (WRAPPED, HEX_PAIRS):
        hits = rx.findall(text)
        if hits:
            removed["encoded_blobs"] = removed.get("encoded_blobs", 0) + len(hits)
            text = rx.sub("[encoded text removed]\n", text)
    blobs = BLOB.findall(text)
    if blobs:
        removed["encoded_blobs"] = removed.get("encoded_blobs", 0) + len(blobs)
        text = BLOB.sub("[encoded text removed]", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def view(message):
    hdr = _headers(message)
    parts = _parts(message)
    removed = {"html_comments": 0, "hidden_elements": 0, "invisible_characters": 0, "encoded_blobs": 0}
    # HTML first: it is what mail clients show. A plain-text part sits behind it unseen, so text only it carries is
    # exactly where an instruction for the AI hides; plain text is read only when the message has no HTML.
    htmls = [t for m, t in parts if m.startswith("text/html")]
    plain = [t for m, t in parts if m.startswith("text/plain")]
    if htmls:
        text, r = visible_text(htmls[0])
    elif plain:
        text, r = (visible_text(plain[0]) if re.search(r"<!--|<[a-zA-Z][^>]*>", plain[0]) else (plain[0], {}))
    else:
        text, r = "", {}
    for k, v in r.items():
        removed[k] += v
    text = clean(text, removed)
    truncated = len(text) > MAX_TEXT
    return {"headers": {k: one_line(" ".join(v)) for k, v in hdr.items() if k != "authentication-results"},
            "auth": _auth(hdr.get("authentication-results", [])), "text": text[:MAX_TEXT], "removed": removed,
            "truncated": truncated}


SAVE_HEADERS = ("from", "to", "cc", "date", "subject", "message-id")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def one_line(value, limit=500):
    """A header value as one line: control characters (CR, LF, tabs) and invisible characters become spaces."""
    return re.sub(r" +", " ", CONTROL.sub(" ", INVISIBLE.sub("", str(value)))).strip()[:limit]


def headers_only(message):
    """What --save keeps of a message: its ids and the headers step 3 needs, nothing else (no body, no other
    header). The Message-ID is kept as sent (the resolver alone hashes it); the others as one line each."""
    keep = []
    for name, values in _headers(message).items():
        if name in SAVE_HEADERS:
            for v in values[:3]:
                keep.append({"name": name.title() if name != "message-id" else "Message-ID",
                             "value": v if name == "message-id" else one_line(v)})
    out = {"payload": {"headers": keep}}
    if isinstance(message, dict):
        for k in ("id", "threadId"):
            if isinstance(message.get(k), str):
                out[k] = one_line(message[k], 64)
    return out
