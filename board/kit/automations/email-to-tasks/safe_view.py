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
import codecs
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
URL = re.compile(r"(https?://[^\s<>\"']+)")
# Base64 wrapped at 76 columns (two or more full lines in a row) and hex written in spaced or colon-separated pairs.
WRAPPED = re.compile(r"(?m)(?:^[ \t]*[A-Za-z0-9+/=_-]{40,}[ \t]*(?:\n|\Z)){2,}")
HEX_PAIRS = re.compile(r"(?i)(?:[0-9a-f]{2}[ :]){30,}[0-9a-f]{2}")
MAX_MARKUP = 400_000   # longer HTML is cut before reading its text: the view keeps 8000 characters anyway
MAX_SCAN = 5_000_000   # longer HTML is TooComplex; a <style> past MAX_MARKUP is TooComplex too
MAX_STYLE = 300_000    # style text read for hiding rules, and at most MAX_RULES rules: over either, the message is
MAX_RULES = 6000       # reported unreadable (TooComplex), never read with some rules skipped
CODE_TAGS = {"script", "style", "title"}   # hidden by nature; text in them is code or a tab title, not removed content
SKIP_TAGS = {"script", "style", "head", "title", "template", "noscript", "svg", "object", "iframe", "textarea", "xmp",
             "noembed", "noframes"}
# Elements a browser reads as raw text (a `</div>` inside is text, not an end tag): parsed the same way here.
RAW_TEXT = ("script", "style", "textarea", "xmp", "noembed", "noframes", "iframe", "noscript")
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track", "param"}
TABLE = {"table", "tr", "td", "th", "thead", "tbody", "tfoot"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "pre", "section"}
NAMED = {"white": (255, 255, 255), "snow": (255, 250, 250), "ivory": (255, 255, 240), "black": (0, 0, 0)}


def _decls(text):
    """CSS declarations as {property: value}, lower case, !important removed, spaces only between words."""
    out = {}
    for d in (text or "").split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            v = re.sub(r"!\s*important", "", v.strip().lower())
            out[k.strip().lower()] = re.sub(r"\s+", " ", re.sub(r"\s*([,()/])\s*", r"\1", v)).strip()
    return out


def _style(attrs):
    return _decls(dict(attrs).get("style") or "")


def _num(v):
    m = re.match(r"^(-?[0-9]*\.?[0-9]+)(px|pt|em|rem|%|)$", v or "")
    return (float(m.group(1)), m.group(2)) if m else None


def _hard_hides(s):
    """Declarations that hide an element and everything in it, whatever its children set (display, visibility,
    opacity, no size, clipped, moved off the screen). Colour and font size are not here: a child can set its own,
    so they are judged at the text itself (`_invisible`)."""
    if s.get("display") == "none" or s.get("visibility") in ("hidden", "collapse"):
        return True
    op = _num(s.get("opacity"))
    if op and op[0] <= 0.05:
        return True
    clipped = "hidden" in s.get("overflow", "")
    for k in ("max-height", "max-width") + (("height", "width") if clipped else ()):
        n = _num(s.get(k))
        if n and n[0] <= 0:
            return True
    w, h = _num(s.get("width")), _num(s.get("height"))
    if w and h and w[0] <= 0 and h[0] <= 0:
        return True   # a box with no size
    if clipped and w and h and w[0] <= 1 and h[0] <= 1 and w[1] in ("px", "") and h[1] in ("px", ""):
        return True   # the 1px box: text clipped to a dot
    for v in re.findall(r"translate[xy]?\(([^)]*)\)", s.get("transform", "")):
        if any(n and n[0] <= -500 for n in map(_num, v.split(","))):
            return True   # moved off the screen
    if re.match(r"rect\(0", s.get("clip", "")) or re.search(r"inset\(50%|inset\(100%|circle\(0", s.get("clip-path", "")):
        return True
    if s.get("position") in ("absolute", "fixed"):
        for k in ("left", "top", "right", "bottom"):
            n = _num(s.get(k))
            if n and n[0] <= -500:
                return True   # moved off the screen
    ti = _num(s.get("text-indent"))
    if ti and ti[0] <= -500:
        return True
    return bool(re.search(r"scale\(0[,)]|scale\(0\.0", s.get("transform", "")))


def _tiny(fs):
    n = _num(fs)
    return bool(n) and (n[0] <= 0 or (n[1] in ("px", "pt", "") and n[0] < 2) or (n[1] in ("em", "rem") and n[0] < 0.2)
                        or (n[1] == "%" and n[0] < 20))


def _invisible(color, bg, fs):
    """Is text with this inherited colour, background and font size invisible to a reader? `bg` "image" means a
    background picture: its colour is unknown, so the colour tests are skipped."""
    if _tiny(fs):
        return True   # zero or unreadably small text
    c = color or ""
    if c == "transparent" or re.fullmatch(r"rgba?\([^)]*[,/]0(\.0+)?%?\)", c) or re.fullmatch(r"#[0-9a-f]{6}00|#[0-9a-f]{3}0", c):
        return True
    if bg == "image":
        return False
    rc, rb = _rgb(c), _rgb(bg)
    if c and bg and c == bg:
        return True
    if rc and rb and max(abs(x - y) for x, y in zip(rc, rb)) <= 16:
        return True   # text all but the same colour as its background
    return bool(rc and min(rc) >= 0xF0 and (not bg or (rb and min(rb) >= 0xF0)))   # white on a white page


def _rgb(c):
    """(r, g, b) for #rgb, #rrggbb, rgb()/rgba() and a few names; None for anything else."""
    c = (c or "").strip()
    if c in NAMED:
        return NAMED[c]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})(?:[0-9a-f]{1,2})?", c)
    if m:
        h = m.group(1)
        return tuple(int(h[i] * 2, 16) for i in range(3)) if len(h) == 3 else tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(([0-9]{1,3})[, ]([0-9]{1,3})[, ]([0-9]{1,3})(?:[,/][0-9.]+%?)?\)", c)
    return tuple(min(255, int(x)) for x in m.groups()) if m else None


def _bg_of(d):
    """The background a declaration set gives: a colour, "image" for a picture, or "" for none."""
    image = d.get("background-image", "")
    b = d.get("background-color") or d.get("background") or ""
    if "url(" in image or "url(" in b or "gradient(" in image or "gradient(" in b:
        return "image"
    m = re.search(r"#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|\b[a-z]+\b", b)
    v = m.group(0) if m else ""
    return "" if v in ("none", "transparent", "inherit", "initial", "unset", "no") else v


class TooComplex(ValueError):
    """The style text is over the caps: the message is reported unreadable, never read with some rules unread."""


def _strip_comments(css):
    """CSS comments removed in one pass; an unterminated `/*` runs to the end of its own block, as in a browser."""
    kept, i = [], 0
    while True:
        a = css.find("/*", i)
        if a < 0:
            return "".join(kept + [css[i:]])
        kept.append(css[i:a]); e = css.find("*/", a + 2)
        if e < 0:
            return "".join(kept)
        i = e + 2


class _Styles(html.parser.HTMLParser):
    """Collects each <style> block's CSS with the same tokenizer that reads the text, so both agree on where a block
    starts and ends (comments, `<style>` written inside CSS or inside an HTML comment)."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks, self.inside, self.size = [], False, 0

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.inside = True; self.blocks.append([])

    def handle_endtag(self, tag):
        if tag == "style":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.size += len(data)
            if self.size > MAX_STYLE:
                raise TooComplex("style blocks over MAX_STYLE")
            self.blocks[-1].append(data)


def _scan_styles(markup):
    """Every `<style` to the next `</style`, by plain string search over the whole message (linear time)."""
    low, out, pos, size = markup.lower(), [], 0, 0
    while True:
        a = low.find("<style", pos)
        if a < 0:
            break
        b = low.find(">", a)
        e = low.find("</style", b + 1) if b >= 0 else -1
        if e < 0:
            break
        size += e - b
        if size > MAX_STYLE:
            raise TooComplex("style blocks over MAX_STYLE")
        out.append(markup[b + 1:e]); pos = e + 7
    return out


def _ambiguous_comment(markup):
    """A comment browsers and this parser may end in different places: one opened as `<!-->` or `<!--->`, or one
    closed with `--!>`. Walks comment to comment (linear time); `<!--[if !mso]><!-->` is an ordinary comment."""
    pos = 0
    while True:
        a = markup.find("<!--", pos)
        if a < 0:
            return False
        if markup.startswith((">", "->"), a + 4):
            return True
        e = markup.find("-->", a + 4)
        bang = markup.find("--!>", a + 4)
        if bang >= 0 and (e < 0 or bang < e):
            return True
        if e < 0:
            return False
        if re.search(r"--\s+>", markup[a + 4:e]):
            return True   # older Python ends the comment at `-- >`, a browser does not
        pos = e + 3


def _style_text(markup):
    """The CSS of every <style> block in the part the text is read from (MAX_MARKUP), one string per block, comments
    removed, found two ways: the HTML parser's own reading and a string scan. A rule either finds counts. A <style>
    past MAX_MARKUP, style over MAX_STYLE, markup over MAX_SCAN, or comment forms browsers and this parser read
    differently raise TooComplex."""
    if len(markup) > MAX_SCAN:
        raise TooComplex("markup over MAX_SCAN")
    if _ambiguous_comment(markup) or "<plaintext" in markup.lower():
        raise TooComplex("ambiguous comment or <plaintext>")
    p = _Styles()
    try:
        p.feed(markup[:MAX_MARKUP]); p.close()
    except TooComplex:
        raise
    except Exception as e:   # the text parser would fail on it too; never read it with rules unknown
        raise TooComplex("unparsable markup") from e
    head = markup[:MAX_MARKUP].lower()
    if p.inside or "<style" in markup[MAX_MARKUP - 8:].lower() or head.rfind("<style") > head.rfind("</style"):
        raise TooComplex("a style block past MAX_MARKUP")   # its rules would be read by no tokenizer that agrees
    blocks = ["".join(b) for b in p.blocks] + _scan_styles(markup[:MAX_MARKUP])
    return [_strip_comments(b) for b in blocks]


DESKTOP = 1200   # the reader modelled: a desktop mail client about 1200px wide, in light mode


def _at_applies(prelude):
    """Does an at-rule's block apply to that reader? @media is evaluated; @keyframes, @font-face and the like hold
    no rules for elements; any other at-rule (e.g. @supports) is taken to apply."""
    p = prelude.lower()
    if not p.startswith("@"):
        return True
    if not p.startswith("@media"):   # unknown at-rules apply; only these hold no rules for elements
        return not p.startswith(("@keyframes", "@-webkit-keyframes", "@font-face", "@page", "@counter-style",
                                 "@property", "@font-feature-values", "@font-palette-values", "@namespace"))
    for alt in p[6:].split(","):
        alt = alt.strip()
        if alt.startswith("not ") or alt.startswith("not("):
            return True   # unsure: apply it
        if re.search(r"\b(print|speech)\b", alt) and not re.search(r"\b(screen|all)\b", alt):
            continue
        ok = True
        for feat, val in re.findall(r"\(\s*([a-z-]+)\s*:\s*([^()]*)\)", alt):
            n = _num(val.strip().replace(" ", ""))
            if feat == "prefers-color-scheme":
                ok = ok and val.strip() != "dark"
            elif feat in ("max-width", "max-device-width") and n and n[1] in ("px", ""):
                ok = ok and n[0] >= DESKTOP
            elif feat in ("min-width", "min-device-width") and n and n[1] in ("px", ""):
                ok = ok and n[0] <= DESKTOP
        if ok:
            return True
    return False


def _rules(css):
    """(applies, selector, declarations) for each rule in one style block, nested at-rules tracked; a block left
    open at the end is closed, as a browser does."""
    out, stack, buf = [], [], []   # stack: (prelude, does everything around it apply)
    for tok in re.split(r"([{}])", css):
        if tok == "{":
            prelude = "".join(buf).strip(); buf = []
            outer = stack[-1][1] if stack else True
            stack.append((prelude, outer and _at_applies(prelude)))
            if len(stack) > 32:
                raise TooComplex("CSS nested too deep")
        elif tok == "}":
            body, buf = "".join(buf), []
            if stack:
                prelude, _ = stack.pop()
                if not prelude.startswith("@"):
                    out.append((stack[-1][1] if stack else True, prelude, body))
        else:
            buf.append(tok)
    while stack:
        prelude, _ = stack.pop()
        if not prelude.startswith("@"):
            out.append((stack[-1][1] if stack else True, prelude, "".join(buf)))
        buf = []
    return out


STATE = re.compile(r"::?(?:hover|focus|focus-within|focus-visible|active|visited|target|before|after|selection|"
                   r"placeholder|first-line|first-letter|marker|backdrop)\b")
DARK_HOOKS = ("[data-ogsc]", "[data-ogsb]", "[data-outlook-cycle]", ".dark-mode", "[data-darkreader")


def _selector_keys(one):
    """The keys (`.class`, `#id`, tag) an element must carry for this selector to hit it, read from its last
    compound; [] when it never applies to a reader in light mode at rest; None when it cannot be named."""
    one = one.strip().lower()
    if not one:
        return []
    last = re.split(r"[\s>+~]+", one)[-1]
    if "not(" not in one and any(h in one[:len(one) - len(last)] for h in DARK_HOOKS):
        return []   # an Outlook dark-mode hook on an ancestor: never set for a light-mode reader
    bare = last
    for _ in range(4):   # what sits inside :not()/:is()/:where() does not decide when the rule applies
        bare = re.sub(r"\([^()]*\)", "", bare)
    if STATE.search(bare):
        return []   # only on hover, focus, a pseudo-element: not the text a reader sees at rest
    keys = re.findall(r"[.#][a-z0-9_-]+", re.sub(r"\[[^\]]*\]|\([^)]*\)", "", last))
    named = True
    for attr, val in re.findall(r"\[\s*([a-z-]+)\s*[~|^$*]?=?\s*[\"']?([^\"'\]]*)", last):
        if attr in ("class", "id") and val.strip():
            keys += [("." if attr == "class" else "#") + v for v in val.split()]
        else:
            named = False
    tag = re.match(r"[a-z][a-z0-9]*", last)
    if keys:
        return keys
    if tag and named:
        return [tag.group(0)]
    return None


def _style_rules(markup):
    """(hard, soft) from the message's <style> blocks: keys whose rules hide an element outright, and per key the
    colour, background and font size the rules give it (later rules win). A rule that would hide text but whose
    elements cannot be named makes the message TooComplex."""
    hard, soft, count = set(), {}, 0
    for block in _style_text(markup):
        for applies, prelude, body in _rules(block):
            count += 1
            if count > MAX_RULES:
                raise TooComplex("style rules over MAX_RULES")
            if not applies:
                continue
            d = _decls(body)
            important = {k.strip().lower() for k, v in (x.split(":", 1) for x in body.split(";") if ":" in x)
                         if re.search(r"!\s*important", v, re.I)}
            hides = _hard_hides(d)
            props = {k: v for k, v in (("color", d.get("color", "")), ("bg", _bg_of(d)),
                                       ("fs", d.get("font-size", ""))) if v}
            if not hides and not props:
                continue
            for one in prelude.split(","):
                keys = _selector_keys(one)
                if keys is None:
                    if hides or _invisible(props.get("color", ""), props.get("bg", ""), props.get("fs", "")):
                        raise TooComplex("a hiding rule for elements this cleaner cannot name")   # `[data-x]`, `*`
                    continue
                for k in keys:
                    if hides:
                        hard.add(k)
                    cur = soft.setdefault(k, {})
                    for prop, v in props.items():
                        # A value that makes text invisible sticks: a later rule for the same key (whose specificity
                        # is not modelled) never makes the text visible again. An !important one beats inline style.
                        if cur.get("sticky_" + prop):
                            continue
                        cur[prop] = v
                        if _hiding_value(prop, v):
                            cur["sticky_" + prop] = True
                            cur["important_" + prop] = ("font-size" if prop == "fs" else "background" if prop == "bg"
                                                        else prop) in important
    return frozenset(hard), soft


def _hiding_value(prop, v):
    if prop == "fs":
        return _px(v, 16.0) < 2
    if prop == "color":
        rc = _rgb(v)
        return v == "transparent" or bool(re.fullmatch(r"rgba?\([^)]*[,/]0(\.0+)?%?\)", v)) or bool(rc and min(rc) >= 0xF0)
    return False


SIZES = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24, "xx-large": 32,
         "xxx-large": 48}


def _px(v, parent):
    """A font-size in px, given the parent's. inherit/unset keep the parent's; a value this cannot read counts as
    0 (hidden), so an unreadable size never shows text a reader may not see."""
    v = (v or "").strip()
    if not v or v in ("inherit", "unset", "revert"):
        return parent
    if v == "initial":
        return 16.0
    if v in SIZES:
        return float(SIZES[v])
    if v in ("smaller", "larger"):
        return parent / 1.2 if v == "smaller" else parent * 1.2
    n = _num(v)
    if not n:
        return 0.0
    return {"px": n[0], "": n[0], "pt": n[0] * 4 / 3, "em": n[0] * parent, "rem": n[0] * 16, "%": n[0] * parent / 100}[n[1]]


QUOTE_KEYS = (".gmail_quote", ".gmail_quote_container", ".yahoo_quoted", "#divrplyfwdmsg", "#appendonsend",
              ".moz-cite-prefix", "blockquote")


class _Visible(html.parser.HTMLParser):
    CDATA_CONTENT_ELEMENTS = RAW_TEXT

    def __init__(self, rules=(frozenset(), {}), strip_quotes=False):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.removed = [], [], {"html_comments": 0, "hidden_elements": 0}
        self.hard, self.soft = rules
        self.strip_quotes, self.quoted = strip_quotes, False

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self.out.append("\n")
        if tag in VOID:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        ident = a.get("id", "").strip().lower()
        keys = [tag] + (["#" + ident] if ident else []) + ["." + c.lower() for c in a.get("class", "").split()]
        props, locked = {}, set()
        for k in keys:   # style-block rules first, then the element's own attributes and inline style
            rule = self.soft.get(k, {})
            for prop in ("color", "bg", "fs"):
                if prop in rule and prop not in locked:
                    props[prop] = rule[prop]
                    if rule.get("important_" + prop):
                        locked.add(prop)   # an !important hiding value beats the element's own style
        inline = _style(attrs)
        own = {}
        if tag == "font" and a.get("color"):
            own["color"] = a["color"].lower()
        if a.get("bgcolor"):
            own["bg"] = a["bgcolor"].lower()
        own.update({k: v for k, v in (("color", inline.get("color", "")), ("bg", _bg_of(inline)),
                                      ("fs", inline.get("font-size", ""))) if v})
        for prop, v in own.items():
            if prop not in locked:
                props[prop] = v
        parent = self.stack[-1] if self.stack else {"color": "", "bg": "", "px": 16.0}
        color = props.get("color", "")
        color = parent["color"] if color in ("", "inherit", "currentcolor", "unset", "revert") else \
            ("" if color == "initial" else color)
        bg = props.get("bg", "")
        bg = parent["bg"] if bg in ("", "inherit") else bg
        px = _px(props.get("fs", ""), parent["px"])
        quote = self.strip_quotes and any(k in QUOTE_KEYS for k in keys)
        self.quoted = self.quoted or quote
        hard = tag in SKIP_TAGS or "hidden" in a or a.get("aria-hidden", "").lower() == "true" or \
            any(k in self.hard for k in keys) or _hard_hides(inline) or quote
        if hard and not quote and tag not in SKIP_TAGS and not any(e["hard"] for e in self.stack):
            self.removed["hidden_elements"] += 1
        self.stack.append({"tag": tag, "hard": hard, "color": color, "bg": bg, "px": px,
                           "counted": tag not in SKIP_TAGS or tag in CODE_TAGS})

    def handle_endtag(self, tag):
        # Close the nearest open tag of this name (mail HTML is sloppy), but never across a table cell, row or table:
        # a browser ignores `</div>` inside a cell whose div opened outside it, so a hidden block stays hidden.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break
            if self.stack[i]["tag"] in TABLE and tag not in TABLE:
                break
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if any(e["hard"] for e in self.stack):
            if data.strip():
                # Text in a tag a page never shows (noscript, template, svg, text loose in <head>) is counted once
                # per tag; the innermost such tag decides, so a <style> or <title> in <head> counts nothing.
                for e in reversed(self.stack):
                    if e["hard"] and e["tag"] in SKIP_TAGS:
                        if not e["counted"]:
                            e["counted"] = True; self.removed["hidden_elements"] += 1
                        break
            return
        top = self.stack[-1] if self.stack else {"color": "", "bg": "", "px": 16.0}
        if data.strip() and _invisible(top["color"], top["bg"], f"{top['px']}px"):
            top = self.stack[-1] if self.stack else None
            if top is not None and not top.get("soft_counted"):
                top["soft_counted"] = True; self.removed["hidden_elements"] += 1
            return
        self.out.append(data)

    def handle_comment(self, data):
        if not _conditional(data):
            self.removed["html_comments"] += 1

    def handle_pi(self, data):
        self.removed["html_comments"] += 1

    def unknown_decl(self, data):
        if not _conditional(data):
            self.removed["html_comments"] += 1


def _cut_blocks(d, tag):
    """`d` without its <tag ...>...</tag> blocks (string search, linear)."""
    out, pos = [], 0
    while True:
        a = d.find("<" + tag, pos)
        if a < 0:
            return "".join(out + [d[pos:]])
        e = d.find("</" + tag, a)
        if e < 0:
            return "".join(out + [d[pos:a]])
        out.append(d[pos:a]); pos = d.find(">", e) + 1 or len(d)


def _conditional(data):
    """Outlook's conditional comments (`<!--[if mso]>..<![endif]-->`, `<!--[if !mso]><!-->`, `<!--<![endif]-->`)
    holding only markup, Outlook's own styles or its XML settings: in almost every mail a tool writes, so not
    counted. One that holds text (shown only in Outlook) is dropped and counted like any comment."""
    d = data.strip().lower()
    if len(d) > 20000 or not re.match(r"\[?(?:end)?if\b|<!\[endif\]", d):
        return False
    d = re.sub(r"^\[?(?:end)?if\b[^\]>]*\]?>?", "", d)
    d = _cut_blocks(_cut_blocks(d, "style"), "xml")
    return not re.sub(r"<[^<>]*>|<!\[endif\]|<!|&nbsp;", "", d).strip(" >\t\r\n")


def visible_text(markup, strip_quotes=False):
    """(text, removed) for an HTML body: only what a person sees. With strip_quotes (mail the owner sent), the
    quoted earlier message is left out too: it is the other side's words, not the owner's."""
    rules = _style_rules(markup)   # TooComplex goes up: never read with rules unknown
    markup = markup[:MAX_MARKUP]    # text past the cut is dropped, never shown
    p = _Visible(rules, strip_quotes)
    try:
        p.feed(markup); p.close()
    except Exception:   # malformed beyond the parser: keep nothing rather than the raw markup
        return "", {"html_comments": 0, "hidden_elements": 1}
    if p.quoted:
        p.removed["quoted_reply"] = 1
    return "".join(p.out), p.removed


def _decode(data, charset="utf-8"):
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError, TypeError):
        return None
    return raw.decode(charset, errors="replace")


def _parts(node, depth=0, out=None, skipped=None, loose=False):
    """(mimeType, decoded text) for each body part in Gmail API shape, and any decoded body string gog adds. In a
    multipart/alternative only the last alternative with text is read, as a mail client shows it; `skipped` counts
    alternatives passed over that held HTML (a second HTML version is where text for the AI alone can sit)."""
    out = [] if out is None else out
    skipped = {"html": 0} if skipped is None else skipped
    if depth > 12:
        return out
    if isinstance(node, dict):
        mime = str(node.get("mimeType") or node.get("mime_type") or "").lower()
        if (isinstance(node.get("filename"), str) and node["filename"].strip()) or mime == "message/rfc822":
            return out   # an attachment or a forwarded message inside this one: never read
        kids = node.get("parts")
        if mime == "multipart/alternative" and isinstance(kids, list):
            alts = [g for g in (_parts(kid, depth + 1, None, skipped) for kid in kids) if g]
            html_alts = [g for g in alts if any(m.startswith("text/html") for m, _ in g)]
            # A client shows the last alternative it can render: the last HTML one, else the last with text.
            out.extend(html_alts[-1] if html_alts else (alts[-1] if alts else []))
            skipped["html"] += max(0, len(html_alts) - 1)
            return out
        body = node.get("body")
        if isinstance(body, dict) and isinstance(body.get("data"), str) and mime.startswith("text/"):
            text = _decode(body["data"], _charset(node))
            if text is not None:
                out.append((mime, text))
        for key in ("body", "text", "html", "textBody", "htmlBody", "plain") if loose else ():
            v = node.get(key)
            if isinstance(v, str) and v.strip():
                out.append(("text/html" if key in ("html", "htmlBody") or re.search(r"<(?:html|body|div|p|br|table)\b", v, re.I)
                            else "text/plain", v))
        for k, v in node.items():
            if k not in ("headers",) and isinstance(v, (dict, list)):
                _parts(v, depth + 1, out, skipped, loose)
    elif isinstance(node, list):
        for v in node:
            _parts(v, depth + 1, out, skipped, loose)
    return out


def _charset(node):
    """The charset= of a part's own Content-Type header, if Python knows it."""
    for h in node.get("headers") or []:
        if isinstance(h, dict) and str(h.get("name", "")).lower() == "content-type":
            m = re.search(r"charset=\"?([a-z0-9_.:-]+)", str(h.get("value", "")), re.I)
            if m:
                try:
                    return codecs.lookup(m.group(1)).name
                except LookupError:
                    return "utf-8"
    return "utf-8"


def _message(node):
    """The message object itself: gog prints it as is, or wrapped as {"message": {...}}."""
    if isinstance(node, dict) and "payload" not in node and isinstance(node.get("message"), dict):
        return node["message"]
    return node if isinstance(node, dict) else {}


def _top_headers(message):
    """The message's own header list (payload.headers, or a flat top-level headers list): never a part's headers,
    which the sender writes and which would let a part's `Cc:` pose as the message's own."""
    m = _message(message)
    payload = m.get("payload")
    hs = payload.get("headers") if isinstance(payload, dict) else m.get("headers")
    return [h for h in hs if isinstance(h, dict) and isinstance(h.get("name"), str) and isinstance(h.get("value"), str)] \
        if isinstance(hs, list) else []


def _headers(message):
    """{lower-case name: [values]} for HEADERS, from the message's own headers, or gog's flat top-level fields."""
    out = {}
    for h in _top_headers(message):
        n = h["name"].lower()
        if n in HEADERS:
            out.setdefault(n, []).append(h["value"])
    if not out:
        for k, v in _message(message).items():
            if isinstance(k, str) and isinstance(v, str) and k.lower() in HEADERS:
                out[k.lower()] = [v]
    return out


def _top_auth_results(message):
    """Authentication-Results values from the message's own header list, in order: never from a part inside it."""
    return [h["value"] for h in _top_headers(message) if h["name"].lower() == "authentication-results"]


def sent_by_owner(message):
    """True when Gmail labels the message SENT: the owner wrote it, so there is no sender check to read. The label is
    Gmail's own, never a header the sender writes."""
    labels = _message(message).get("labelIds")
    return isinstance(labels, list) and "SENT" in {str(x).upper() for x in labels}


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
    # A link's path (a commit hash, a tracking id) is not a blob; a run inside a URL is cut only when very long.
    pieces = URL.split(text)
    for i, piece in enumerate(pieces):
        # In a link, hash-shaped hex (a commit id, a checksum: 32 to 64 hex digits) is not counted toward a blob.
        is_blob = (lambda m: len(re.sub(r"[0-9a-f]{32,64}", "", m.group(0))) >= 80) if i % 2 else (lambda m: True)
        hits = [m for m in BLOB.finditer(piece) if is_blob(m)]
        if hits:
            removed["encoded_blobs"] = removed.get("encoded_blobs", 0) + len(hits)
            pieces[i] = BLOB.sub(lambda m: "[encoded text removed]" if is_blob(m) else m.group(0), piece)
    text = "".join(pieces)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


QUOTE_START = re.compile(r"(?im)^(?:on .{1,300} wrote:|-{2,} ?original message ?-{2,}|_{10,})\s*$")


def _plain_without_quote(text):
    """Plain text of a sent reply without the quoted earlier message: from its "On .. wrote:" line on, and `>` lines."""
    m = QUOTE_START.search(text)
    kept = text[:m.start()] if m else text
    lines = [l for l in kept.split("\n") if not l.lstrip().startswith(">")]
    return "\n".join(lines), bool(m) or len(lines) < kept.count("\n") + 1


def view(message):
    hdr = _headers(message)
    sent = sent_by_owner(message)
    skipped = {"html": 0}
    parts = _parts(_message(message), 0, None, skipped)
    if not any(m.startswith("text/") for m, _ in parts):
        parts = _parts(_message(message), 0, None, skipped, loose=True)   # gog's own decoded body strings
    removed = {"html_comments": 0, "hidden_elements": 0, "invisible_characters": 0, "encoded_blobs": 0}
    if skipped["html"]:
        removed["hidden_elements"] += skipped["html"]   # an HTML alternative no client shows
    # HTML first: it is what mail clients show. A plain-text part sits behind it unseen, so text only it carries is
    # exactly where an instruction for the AI hides; plain text is read only when the message has no HTML.
    htmls = [t for m, t in parts if m.startswith("text/html")]
    if len(htmls) > 1:   # several HTML parts side by side (multipart/mixed): a client shows them all, in order
        htmls = ["\n".join(htmls)]
    plain = [t for m, t in parts if m.startswith("text/plain")]
    quoted = False
    if htmls:
        text, r = visible_text(htmls[0], strip_quotes=sent)
    elif plain:
        body = plain[0]
        if sent:
            body, quoted = _plain_without_quote(body)
        text, r = (visible_text(body, strip_quotes=sent) if re.search(r"<!--|<[a-zA-Z][^>]*>", body) else (body, {}))
    else:
        text, r = "", {}
    quoted = quoted or bool(r.pop("quoted_reply", 0))
    for k, v in r.items():
        removed[k] += v
    text = clean(text, removed)
    truncated = len(text) > MAX_TEXT
    return {"headers": {k: one_line(" ".join(v), 4000 if k in ("to", "cc") else 500)
                        for k, v in hdr.items() if k != "authentication-results"},
            "auth": ({m: "sent" for m in ("spf", "dkim", "dmarc")} if sent else _auth(_top_auth_results(message))),
            "text": text[:MAX_TEXT], "removed": removed, "truncated": truncated, "quoted_reply_removed": quoted}


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
    m = _message(message)
    for k in ("id", "threadId"):
        if isinstance(m.get(k), str):
            out[k] = one_line(m[k], 64)
    return out
