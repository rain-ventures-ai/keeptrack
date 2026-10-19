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


def _style(attrs):
    return {k.strip().lower(): v.strip().lower().replace(" ", "") for k, v in
            (d.split(":", 1) for d in (dict(attrs).get("style") or "").split(";") if ":" in d)}


def _hidden(tag, attrs, inherited_bg):
    a = {k.lower(): (v or "") for k, v in attrs}
    if "hidden" in a or a.get("aria-hidden", "").lower() == "true":
        return True
    s = _style(attrs)
    if s.get("display") == "none" or s.get("visibility") in ("hidden", "collapse") or s.get("opacity") in ("0", "0.0"):
        return True
    zero = lambda v: re.fullmatch(r"0(\.0+)?(px|pt|em|rem|%)?(!important)?", v or "x") is not None
    if zero(s.get("font-size")):
        return True
    clipped = "hidden" in s.get("overflow", "")
    if any(zero(s.get(k)) for k in ("max-height", "max-width")) or (clipped and any(zero(s.get(k)) for k in ("height", "width"))):
        return True
    color = s.get("color") or (a.get("color", "").lower() if tag == "font" else "")
    bg = s.get("background-color") or s.get("background") or a.get("bgcolor", "").lower() or inherited_bg
    if color and bg and color.replace("!important", "") == bg.replace("!important", ""):
        return True   # text the same colour as its background
    if color.replace("!important", "") in WHITE and (not bg or bg.replace("!important", "") in WHITE):
        return True   # white text on a white (default) page
    return False


class _Visible(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.removed = [], [], {"html_comments": 0, "hidden_elements": 0}

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
        hide = tag in SKIP_TAGS or _hidden(tag, attrs, self._bg())
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
    p = _Visible()
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
    for line in results:
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
    plain = [t for m, t in parts if m.startswith("text/plain")]
    if plain:
        text = plain[0]
        if re.search(r"<!--|<[a-zA-Z][^>]*>", text):   # "plain" that carries markup is cleaned as HTML
            text, r = visible_text(text); removed.update({k: removed[k] + v for k, v in r.items()})
    else:
        htmls = [t for m, t in parts if m.startswith("text/html")]
        text, r = visible_text(htmls[0]) if htmls else ("", {})
        removed.update({k: removed[k] + v for k, v in r.items()})
    text = clean(text, removed)
    truncated = len(text) > MAX_TEXT
    return {"headers": {k: clean(" ".join(v), {})[:500] for k, v in hdr.items() if k != "authentication-results"},
            "auth": _auth(hdr.get("authentication-results", [])), "text": text[:MAX_TEXT], "removed": removed,
            "truncated": truncated}


def headers_only(message):
    """The saved message without any body: the agent reads the body only through view()."""
    if isinstance(message, dict):
        return {k: headers_only(v) for k, v in message.items() if k not in ("body", "parts", "raw", "text", "html",
                                                                              "textBody", "htmlBody", "plain", "snippet")}
    if isinstance(message, list):
        return [headers_only(v) for v in message]
    return message
