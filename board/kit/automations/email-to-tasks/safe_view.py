"""The only view of a message the agent reads: headers it needs, and the body as plain visible text.

Mail is written by strangers, and some of it is written for the AI that reads it: instructions hidden where a person
never sees them (HTML comments, text styled invisible, zero-width or Unicode tag characters, long encoded blobs).
`view(message)` takes gog's JSON for one message, whatever its shape, and returns

    {"headers": {...}, "auth": {"spf": .., "dkim": .., "dmarc": ..}, "text": "...", "removed": {...}, "truncated": bool}

`text` is what a person would see: text/plain when the message has it, else the HTML with hidden parts removed.
`removed` counts what was taken out, so the skill can say so in a proposal ("hidden content removed"). Standard
library only. Nothing here decides what is true; it only keeps the invisible out of the agent's input.
"""
import base64
import binascii
import html
import html.parser
import re

MAX_TEXT = 8000
HEADERS = ("from", "to", "cc", "date", "subject", "reply-to", "message-id")
# Characters a reader never sees: zero-width, joiners, bidi controls and isolates, soft hyphen, BOM, Unicode tags.
INVISIBLE = re.compile("[­؜᠎​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
BLOB = re.compile(r"[A-Za-z0-9+/=_-]{80,}")
SKIP_TAGS = {"script", "style", "head", "title", "template", "noscript", "svg", "object", "iframe"}
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track", "param"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "pre", "section"}
WHITE = {"#fff", "#ffffff", "white", "rgb(255,255,255)", "rgba(255,255,255,1)", "#fefefe", "#fdfdfd"}


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
    if c in WHITE and (not b or b in WHITE):
        return True   # white text on a white (default) page
    return False


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


def _hidden_selectors(markup):
    """Simple selectors (.class, #id, tag) that a <style> block hides: `.x{display:none}` and the like."""
    found = set()
    for block in re.findall(r"<style[^>]*>(.*?)</style>", markup, flags=re.S | re.I):
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            if _hides(_decls(body)):
                for one in sel.split(","):
                    last = one.strip().split()[-1] if one.strip() else ""
                    m = re.fullmatch(r"([a-z0-9]*)((?:[.#][a-z0-9_-]+)*)", last.lower())
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
        for _, _, bg in reversed(self.stack):
            if bg:
                return bg
        return ""

    def _hidden_now(self):
        return any(h for _, h, _ in self.stack)

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
        self.stack.append((tag, hide, bg.lower()))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):   # close the nearest open tag of this name (mail HTML is sloppy)
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._hidden_now():
            self.out.append(data)

    def handle_comment(self, data):
        self.removed["html_comments"] += 1

    def handle_pi(self, data):
        self.removed["html_comments"] += 1

    def unknown_decl(self, data):
        self.removed["html_comments"] += 1


def visible_text(markup):
    """(text, removed) for an HTML body: only what a person sees."""
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
    """spf/dkim/dmarc results from Authentication-Results (the receiving server's, Gmail's), or "none"."""
    found = {}
    ours = [l for l in results if l.strip().lower().startswith("mx.google.com")][:1]   # a sender can add its own
    for line in ours:
        for mech in ("spf", "dkim", "dmarc"):
            m = re.search(r"\b" + mech + r"=([a-z]+)", line.lower())
            if m and mech not in found:
                found[mech] = m.group(1)
    return {mech: found.get(mech, "none") for mech in ("spf", "dkim", "dmarc")}


def clean(text, removed):
    text = html.unescape(text) if "&" in text else text
    n = len(INVISIBLE.findall(text))
    if n:
        removed["invisible_characters"] = removed.get("invisible_characters", 0) + n
        text = INVISIBLE.sub("", text)
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
