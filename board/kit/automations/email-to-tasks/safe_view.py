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
import colorsys
import html
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
SCOPE = TABLE | {"caption", "marquee", "applet", "object", "template", "html"}   # an end tag never closes past these
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "pre", "section"}
NAMED = {k: tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)) for k, v in {
    "aliceblue": "f0f8ff", "antiquewhite": "faebd7", "aqua": "00ffff", "aquamarine": "7fffd4", "azure": "f0ffff",
    "beige": "f5f5dc", "bisque": "ffe4c4", "black": "000000", "blanchedalmond": "ffebcd", "blue": "0000ff",
    "blueviolet": "8a2be2", "brown": "a52a2a", "burlywood": "deb887", "cadetblue": "5f9ea0", "chartreuse": "7fff00",
    "chocolate": "d2691e", "coral": "ff7f50", "cornflowerblue": "6495ed", "cornsilk": "fff8dc", "crimson": "dc143c",
    "cyan": "00ffff", "darkblue": "00008b", "darkcyan": "008b8b", "darkgoldenrod": "b8860b", "darkgray": "a9a9a9",
    "darkgreen": "006400", "darkgrey": "a9a9a9", "darkkhaki": "bdb76b", "darkmagenta": "8b008b", "darkolivegreen":
    "556b2f", "darkorange": "ff8c00", "darkorchid": "9932cc", "darkred": "8b0000", "darksalmon": "e9967a",
    "darkseagreen": "8fbc8f", "darkslateblue": "483d8b", "darkslategray": "2f4f4f", "darkslategrey": "2f4f4f",
    "darkturquoise": "00ced1", "darkviolet": "9400d3", "deeppink": "ff1493", "deepskyblue": "00bfff", "dimgray":
    "696969", "dimgrey": "696969", "dodgerblue": "1e90ff", "firebrick": "b22222", "floralwhite": "fffaf0",
    "forestgreen": "228b22", "fuchsia": "ff00ff", "gainsboro": "dcdcdc", "ghostwhite": "f8f8ff", "gold": "ffd700",
    "goldenrod": "daa520", "gray": "808080", "grey": "808080", "green": "008000", "greenyellow": "adff2f",
    "honeydew": "f0fff0", "hotpink": "ff69b4", "indianred": "cd5c5c", "indigo": "4b0082", "ivory": "fffff0",
    "khaki": "f0e68c", "lavender": "e6e6fa", "lavenderblush": "fff0f5", "lawngreen": "7cfc00", "lemonchiffon":
    "fffacd", "lightblue": "add8e6", "lightcoral": "f08080", "lightcyan": "e0ffff", "lightgoldenrodyellow":
    "fafad2", "lightgray": "d3d3d3", "lightgreen": "90ee90", "lightgrey": "d3d3d3", "lightpink": "ffb6c1",
    "lightsalmon": "ffa07a", "lightseagreen": "20b2aa", "lightskyblue": "87cefa", "lightslategray": "778899",
    "lightslategrey": "778899", "lightsteelblue": "b0c4de", "lightyellow": "ffffe0", "lime": "00ff00", "limegreen":
    "32cd32", "linen": "faf0e6", "magenta": "ff00ff", "maroon": "800000", "mediumaquamarine": "66cdaa",
    "mediumblue": "0000cd", "mediumorchid": "ba55d3", "mediumpurple": "9370db", "mediumseagreen": "3cb371",
    "mediumslateblue": "7b68ee", "mediumspringgreen": "00fa9a", "mediumturquoise": "48d1cc", "mediumvioletred":
    "c71585", "midnightblue": "191970", "mintcream": "f5fffa", "mistyrose": "ffe4e1", "moccasin": "ffe4b5",
    "navajowhite": "ffdead", "navy": "000080", "oldlace": "fdf5e6", "olive": "808000", "olivedrab": "6b8e23",
    "orange": "ffa500", "orangered": "ff4500", "orchid": "da70d6", "palegoldenrod": "eee8aa", "palegreen": "98fb98",
    "paleturquoise": "afeeee", "palevioletred": "db7093", "papayawhip": "ffefd5", "peachpuff": "ffdab9", "peru":
    "cd853f", "pink": "ffc0cb", "plum": "dda0dd", "powderblue": "b0e0e6", "purple": "800080", "rebeccapurple":
    "663399", "red": "ff0000", "rosybrown": "bc8f8f", "royalblue": "4169e1", "saddlebrown": "8b4513", "salmon":
    "fa8072", "sandybrown": "f4a460", "seagreen": "2e8b57", "seashell": "fff5ee", "sienna": "a0522d", "silver":
    "c0c0c0", "skyblue": "87ceeb", "slateblue": "6a5acd", "slategray": "708090", "slategrey": "708090", "snow":
    "fffafa", "springgreen": "00ff7f", "steelblue": "4682b4", "tan": "d2b48c", "teal": "008080", "thistle":
    "d8bfd8", "tomato": "ff6347", "turquoise": "40e0d0", "violet": "ee82ee", "wheat": "f5deb3", "white": "ffffff",
    "whitesmoke": "f5f5f5", "yellow": "ffff00", "yellowgreen": "9acd32", "windowtext": "000000", "buttontext":
    "000000", "canvastext": "000000", "text": "000000", "linktext": "0000ee", "window": "ffffff", "canvas":
    "ffffff", "buttonface": "f0f0f0"}.items()}


def _unescape_css(text):
    """CSS escapes decoded (`\\6e` is `n`, `\\n` is `n`), as a browser reads them."""
    def one(m):
        if m.group(1):
            n = int(m.group(1), 16)
            return chr(n) if 0 < n <= 0x10FFFF else "\ufffd"
        return m.group(2)
    return re.sub(r"\\([0-9a-fA-F]{1,6})[ \t\n]?|\\(.)", one, text)


def _decls(text):
    """CSS declarations as {property: value}. The text is split into declarations, and `!important` read, on the raw
    text; escapes are decoded only inside a name or value afterwards, so an escaped `;`, `:` or `!` never becomes
    syntax. An !important declaration beats a later normal one, as in a browser. A style over 20000 characters or
    a value over 1000 is not cut: it counts as `display:none` (when unsure, hide more)."""
    text = _strip_comments(text or "")
    if len(text) > 20000:
        return {"display": "none"}
    out, imp = {}, set()
    for d in text.split(";"):
        if ":" not in d:
            continue
        k, v = d.split(":", 1)
        k, v = _unescape_css(k).strip().lower(), _unescape_css(v).strip().lower()
        important = bool(re.search(r"!\s*important\s*$", v))
        v = re.sub(r"!\s*important\s*$", "", v)
        if len(v) > 1000 or "!" in v:
            return {"display": "none"}   # a value a browser may read differently: hide more
        if k in imp and not important:
            continue
        if important:
            imp.add(k)
        out[k] = re.sub(r"\s+", " ", re.sub(r"\s*([,()/])\s*", r"\1", v)).strip()
    fs = _font_size(out.get("font", ""))
    if fs and (not out.get("font-size") or _px(fs, 16.0) < _px(out["font-size"], 16.0)):
        out["font-size"] = fs   # the `font` shorthand sets the size too (`font:0/0 a`): the smaller of the two counts
    return out


FONT_SIZE = re.compile(r"(?:xx?x?-small|xx?x?-large|small|medium|large|smaller|larger|-?[0-9]*\.?[0-9]+(?:px|pt|em|rem|%))"
                       r"(?:/\S*)?|-?[0-9]*\.?[0-9]+/\S*|0")


def _font_size(v):
    """The font size a `font` shorthand sets, or "" when it sets none a browser would use (a system font keyword, or a
    value with no size, which a browser drops). A size written with calc(), var() and the like counts as 0."""
    if not v or v in ("inherit", "initial", "unset", "revert", "caption", "icon", "menu", "message-box",
                      "small-caption", "status-bar"):
        return ""
    if re.search(r"\b(?:calc|var|min|max|clamp|env|attr)\(", v):
        return "0"   # a size this cannot work out: hide more
    sizes = [t for t in v.split(" ") if FONT_SIZE.fullmatch(t)]
    return sizes[-1].split("/")[0] if sizes else ""


def _important(text):
    """The properties a declaration block marks !important, read the same way as _decls."""
    out = set()
    for d in _strip_comments(text or "")[:20000].split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            if re.search(r"!\s*important\s*$", _unescape_css(v), re.I):
                out.add(_unescape_css(k).strip().lower())
    return out


def _style(attrs):
    return _decls(dict(attrs).get("style") or "")


def _num(v):
    m = re.match(r"^(-?[0-9]*\.?[0-9]+)(px|pt|em|rem|%|)$", v or "")
    return (float(m.group(1)), m.group(2)) if m else None


# Properties that can hide text and whose values this cleaner does not model one by one: any value but these hides
# the element (when unsure, hide more).
OPAQUE = {"content-visibility": ("visible", "auto"), "filter": ("none",), "-webkit-filter": ("none",),
          "mask": ("none",), "mask-image": ("none",), "-webkit-mask": ("none",), "-webkit-mask-image": ("none",),
          "-webkit-mask-box-image": ("none",), "mix-blend-mode": ("normal",), "text-security": ("none",), "-webkit-text-security": ("none",), "font-size-adjust": ("none",)}


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
    if clipped and any(n and n[0] <= 1 and n[1] in ("px", "") for n in (w, h)):
        return True   # the 1px box: text clipped to a dot
    for v in re.findall(r"translate(?:[xyz]|3d)?\(([^)]{0,200})\)", s.get("transform", "")) + [s.get("translate", "")]:
        if any(n and n[0] <= -500 for n in map(_num, re.split(r"[, ]", v))):
            return True   # moved off the screen
    for v in re.findall(r"scale(?:[xyz]|3d)?\(([^)]{0,200})\)", s.get("transform", "")) + [s.get("scale", "")]:
        if any(n and abs(n[0] / (100 if n[1] == "%" else 1)) <= 0.05 for n in map(_num, re.split(r"[, ]", v))):
            return True   # shrunk to nothing
    for v in re.findall(r"matrix(3d)?\(([^)]{0,400})\)", s.get("transform", "")):
        try:
            m = [float(x) for x in v[1].split(",")]
            if abs(m[0] * m[5] - m[1] * m[4] if v[0] else m[0] * m[3] - m[1] * m[2]) <= 0.0025:
                return True   # a matrix that flattens the text
        except (ValueError, IndexError):
            return True   # a matrix this cannot read: hide more
    z = _num(s.get("zoom", "").replace("normal", "1").replace("reset", "1"))
    if s.get("zoom") and (not z or z[1] not in ("", "%") or z[0] / (100 if z[1] == "%" else 1) <= 0.05):
        return True   # zoomed to nothing, or a zoom this cannot read
    for k in ("margin-left", "margin-top", "margin"):
        if any(n and n[0] <= -500 for n in map(_num, s.get(k, "").split(" "))):
            return True   # pulled off the screen by a large negative margin
    for k, harmless in OPAQUE.items():
        v = s.get(k, "")
        if v and v not in harmless and not v.startswith(("progid:", "alpha(")):   # old IE filters: no client runs them
            return True   # a property that can hide text, with a value this does not model: hide more
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


def _invisible(color, bg, px):
    """Is text with this inherited colour, background and font size (in px) invisible to a reader? `bg` "image"
    means a background picture: its colour is unknown, so the colour tests are skipped. `bg` may hold several
    colours joined by `|` (a var() or light-dark() background): the text is invisible if it is against any of them.
    A colour this cannot read counts as invisible: when unsure, hide more."""
    if not px >= 2:   # also catches NaN
        return True   # zero or unreadably small text
    c = (color or "").strip()
    if not c:
        return False   # the reader's default colour
    rc = _rgba(c)
    if rc is None or rc[3] <= 0.2:
        return True   # unreadable colour, or (nearly) transparent
    if bg == "image":
        return False
    for one in (bg or "").split("|"):
        rb = _rgba(one) if one else None
        if rb and max(abs(x - y) for x, y in zip(rc[:3], rb[:3])) <= 16:
            return True   # text all but the same colour as its background
        # No background, or one this cannot read: the text is judged against a white page.
        if min(rc[:3]) >= 0xF0 and (rb is None or min(rb[:3]) >= 0xF0):
            return True   # white on a white page
    return False


def _rgb(c):
    """(r, g, b) of a CSS colour, or None."""
    v = _rgba(c)
    return v[:3] if v else None


def _channel(x, scale=255):
    x = x.strip()
    n = float(x[:-1]) * scale / 100 if x.endswith("%") else float(x)
    return max(0.0, min(float(scale), n))


def _rgba(c):
    """(r, g, b, alpha) for a CSS colour (hex with alpha, every named colour, rgb()/rgba() with numbers or %,
    hsl()/hsla(), transparent); None for anything else."""
    c = (c or "").strip().lower()
    if c == "transparent":
        return (0, 0, 0, 0.0)
    if c in NAMED:
        return NAMED[c] + (1.0,)
    m = re.fullmatch(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", c)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        alpha = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
    m = re.fullmatch(r"(rgba?|hsla?)\(([^()]{1,80})\)", c)
    if not m:
        return None
    args = [x for x in re.split(r"[,/ ]+", m.group(2).strip()) if x]
    try:
        alpha = _channel(args[3], 1) if len(args) > 3 else 1.0
        if m.group(1).startswith("rgb"):
            r, g, b = (_channel(x) for x in args[:3])
        else:
            h = float(args[0].replace("deg", "")) % 360 / 360
            r, g, b = (x * 255 for x in colorsys.hls_to_rgb(h, _channel(args[2], 1), _channel(args[1], 1)))
    except (ValueError, IndexError):
        return None
    return (int(r), int(g), int(b), alpha)


COLOUR_TOKEN = re.compile(r"#[0-9a-f]{3,8}\b|(?:rgba?|hsla?)\([^()]{0,80}\)|[a-z]+")
UNREADABLE_COLOUR = re.compile(r"\b(?:color-mix|color|hwb|lab|lch|oklab|oklch|device-cmyk)\(|"
                               r"\b(?:rgba?|hsla?)\([^()]{0,80}\(")   # a colour function, or rgb(calc(..)) and the like
MAX_CUSTOM = 5000   # custom property names (`--x: ..`) in one message, at most 100 values each; more is TooComplex


def _expand_vars(value, customs):
    """`value` with each var(--name, fallback) followed: the values every `--name` is given anywhere in the message
    (the right one depends on the cascade, so all count) are added next to the fallback. Four levels deep at most."""
    for _ in range(4):
        names = re.findall(r"var\(\s*(--[^,()\s]+)", value)
        if not names:
            return value
        if len(value) > 20000:
            raise TooComplex("custom properties expand too far")
        value = re.sub(r"var\(\s*--[^,()\s]+\s*,?", " ", value) + " " + \
            " ".join(v for n in dict.fromkeys(names) for v in (customs or {}).get(n, ()))
    raise TooComplex("custom properties nested too deep")


def _bg_of(d, customs=None):
    """The background a declaration set gives: a colour, "image" for a picture, or "" for none. A value written with
    var(), light-dark() or calc() gives every colour it may resolve to, joined by `|`, and text is judged against
    each of them (when unsure, hide more). A colour this cannot work out (color-mix(), lab(), rgb(calc())) makes
    the message TooComplex: it is never judged against a guess."""
    image = d.get("background-image", "")
    b = d.get("background-color") or d.get("background") or ""
    if b.strip() == "inherit":
        return "inherit"
    b = re.sub(r"(?:url|[a-z-]*gradient)\([^()]{0,1000}\)", " ", b[:1000]) if "url(" in b or "gradient(" in b else b[:1000]
    if not re.search(r"\b(?:var|env|calc|attr|light-dark)\(", b):
        if UNREADABLE_COLOUR.search(b):
            raise TooComplex("a background colour this cannot read")
        for tok in COLOUR_TOKEN.findall(b):
            c = _rgba(tok) if tok != "transparent" else None
            if c is not None:
                # The colour, also in a shorthand such as `url(x) no-repeat #003366`: judged against it. A (nearly)
                # transparent background shows the one behind it.
                return tok if c[3] > 0.2 else ""
    else:
        b = _expand_vars(b, customs)
        if UNREADABLE_COLOUR.search(b):
            raise TooComplex("a background colour this cannot read")
        found = [t for t in COLOUR_TOKEN.findall(b) if t != "transparent" and (_rgba(t) or (0, 0, 0, 0))[3] > 0.2]
        if "var(" in d.get("background-color", "") + d.get("background", "") and found:
            found.append("white")   # a custom property may be unset or invalid where it is used: then the page shows
        if found:
            return "|".join(dict.fromkeys(found))
    if "url(" in image or "url(" in d.get("background", "") or "gradient(" in image or "gradient(" in d.get("background", ""):
        return "image"   # a picture with no colour: its colour is unknown
    return ""


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


def _customs(text, out):
    """Adds each custom property declaration (`--x: #000`) in a declaration block to `out` ({name: [values]})."""
    for d in _strip_comments(text)[:20000].split(";"):
        if ":" in d:
            k, v = d.split(":", 1)
            k = _unescape_css(k).strip().lower()
            if k.startswith("--"):
                out.setdefault(k, []).append(_unescape_css(v).strip().lower()[:1000])
                if len(out) > MAX_CUSTOM or len(out[k]) > 100:
                    raise TooComplex("custom properties over MAX_CUSTOM")


class _Styles(html.parser.HTMLParser):
    """Collects each <style> block's CSS with the same tokenizer that reads the text, so both agree on where a block
    starts and ends (comments, `<style>` written inside CSS or inside an HTML comment)."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks, self.inside, self.size, self.customs = [], False, 0, {}

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.inside = True; self.blocks.append([])
        style = dict(attrs).get("style") or ""
        if "--" in style:
            _customs(style, self.customs)

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
    """(blocks, customs): the CSS of every <style> block in the part the text is read from (MAX_MARKUP), one string
    per block, comments removed, and the custom properties its inline styles declare. Blocks are found two ways: the HTML parser's own reading and a string scan. A rule either finds counts. A <style>
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
    return [_strip_comments(b) for b in blocks], p.customs


DESKTOP = 1200   # the main reader modelled: a desktop mail client about 1200px wide, in light mode
# A desktop window is not exactly 1200px wide: a hiding rule under @media counts when it applies at any of these
# widths (a bit mask of WIDTHS), so a rule that leaves only a narrow window around 1200px open still hides. A rule for
# phones only (`max-width:600px`) hides nothing here: a desktop reader sees that text, and responsive mail (MJML)
# puts its main text in such blocks.
WIDTHS = (DESKTOP, 1440, 1920)
ALL = (1 << len(WIDTHS)) - 1
DESK = 1 << WIDTHS.index(DESKTOP)


def _at_applies(prelude):
    """The widths (a mask of WIDTHS) at which an at-rule's block applies to a light-mode screen reader. @media is
    evaluated; @keyframes, @font-face and the like hold no rules for elements (0); any other at-rule (e.g. @supports)
    is taken to apply at every width. A media feature this cannot read is taken to apply (when unsure, hide more)."""
    p = prelude.lower()
    if not p.startswith("@"):
        return ALL
    if not p.startswith("@media"):   # unknown at-rules apply; only these hold no rules for elements
        return 0 if p.startswith(("@keyframes", "@-webkit-keyframes", "@font-face", "@page", "@counter-style",
                                  "@property", "@font-feature-values", "@font-palette-values", "@namespace")) else ALL
    out = 0
    for alt in p[6:].split(","):
        alt = alt.strip()
        if alt.startswith("not ") or alt.startswith("not("):
            return ALL   # unsure: apply it
        if re.search(r"\b(print|speech)\b", alt) and not re.search(r"\b(screen|all)\b", alt):
            continue
        ok = ALL
        for feat, val in re.findall(r"\(\s*([a-z-]+)\s*:\s*([^()]*)\)", alt):
            n = _num(val.strip().replace(" ", ""))
            px = n[0] * (16 if n[1] in ("em", "rem") else 1) if n and n[1] in ("px", "", "em", "rem") else None
            if feat == "prefers-color-scheme":
                ok = ok if val.strip() != "dark" else 0
            elif feat in ("max-width", "max-device-width") and px is not None:
                ok &= sum(1 << i for i, w in enumerate(WIDTHS) if w <= px)
            elif feat in ("min-width", "min-device-width") and px is not None:
                ok &= sum(1 << i for i, w in enumerate(WIDTHS) if w >= px)
        out |= ok
    return out


def _rules(css):
    """(widths, plain, selector, declarations) for each rule in one style block: `widths` the mask of WIDTHS at which
    every at-rule around it applies, `plain` True when nothing is around it (it surely applies). Nested at-rules are
    tracked; a block left open at the end is closed, as a browser does."""
    out, stack, buf = [], [], []   # stack: (prelude, the widths at which everything around it applies)
    for tok in re.split(r"([{}])", css):
        if tok == "{":
            prelude = "".join(buf).strip(); buf = []
            outer = stack[-1][1] if stack else ALL
            stack.append((prelude, outer & _at_applies(prelude)))
            if len(stack) > 32:
                raise TooComplex("CSS nested too deep")
        elif tok == "}":
            body, buf = "".join(buf), []
            if stack:
                prelude, _ = stack.pop()
                if not prelude.startswith("@"):
                    out.append((stack[-1][1] if stack else ALL, not stack, prelude, body))
        else:
            buf.append(tok)
    while stack:
        prelude, _ = stack.pop()
        if not prelude.startswith("@"):
            out.append((stack[-1][1] if stack else ALL, not stack, prelude, "".join(buf)))
        buf = []
    return out


STATE = re.compile(r"::?(?:hover|focus|focus-within|focus-visible|active|visited|target|before|after|selection|"
                   r"placeholder|first-line|first-letter|marker|backdrop)\b")
DARK_HOOKS = ("[data-ogsc]", "[data-ogsb]", "[data-outlook-cycle]", ".dark-mode", "[data-darkreader")


def _split_selector(one):
    """(compounds, combinators) of one selector: `img.g-img + div` is (["img.g-img", "div"], ["+"]). A combinator
    inside (), [] (`:nth-child(2n+1)`, `[title="a b"]`) is not one."""
    comps, combs, cur, depth, pending = [], [], [], 0, None
    for ch in one:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if not depth and ch in " \t\n\r\f>+~":
            if cur:
                comps.append("".join(cur)); cur = []; pending = pending or " "
            if ch in ">+~":
                pending = ch
            continue
        if not cur and comps and pending:
            combs.append(pending)
        if not cur:
            pending = None
        cur.append(ch)
    if cur:
        comps.append("".join(cur))
    return comps, combs


def _compound_keys(last):
    """The keys (`.class`, `#id`, tag) an element must carry to match one compound selector (any one of them counts:
    when unsure, hide more); [] when it never matches at rest in light mode; None when it cannot be named."""
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


def _selector_keys(one):
    """(keys, combinator, previous keys) for one selector. `keys` are read from its last compound, as _compound_keys
    reads them ([] when the selector never applies to a reader in light mode at rest). When the last compound follows
    a sibling combinator (`a + b`, `a ~ b`), `combinator` is that `+` or `~` and `previous keys` are the keys of the
    compound before it, so the rule hits only an element after such a sibling; otherwise both are None."""
    one = one.strip().lower()
    comps, combs = _split_selector(one)
    if not comps:
        return [], None, None
    head = one[:len(one) - len(comps[-1])]
    if "not(" not in one and any(h in head for h in DARK_HOOKS):
        return [], None, None   # an Outlook dark-mode hook on an ancestor: never set for a light-mode reader
    keys = _compound_keys(comps[-1])
    if keys and combs and combs[-1] in "+~":
        prev = _compound_keys(comps[-2])
        if prev == []:
            return [], None, None   # the sibling only matches on hover or the like: never at rest
        if prev:
            return keys, combs[-1], prev
    return keys, None, None


def _specificity(one):
    """A selector's specificity (ids, classes and attributes and pseudo-classes, tags), counted roughly: enough to
    order two rules for the same element as a browser does."""
    s = one.lower()
    return (len(re.findall(r"#[a-z0-9_-]", s)), len(re.findall(r"\.[a-z_-]|\[|(?<!:):(?!:)[a-z]", s)),
            len(re.findall(r"(?:^|[\s>+~(,])[a-z][a-z0-9]*", s)) + len(re.findall(r"::[a-z]", s)))


KEYWORDS = ("inherit", "currentcolor", "initial", "unset", "revert", "revert-layer")
MAX_SIBLING = 200   # rules with a sibling combinator (`a + b`) whose effect is modelled; more is TooComplex


def _factor(v):
    """An opacity or zoom value as a number (`50%` is 0.5), or None."""
    n = _num((v or "").replace("normal", "1").replace("reset", "1"))
    return n[0] / (100 if n[1] == "%" else 1) if n and n[1] in ("", "%") else None


class _Rules:
    """What the message's <style> blocks do, by key (`.class`, `#id`, tag):
    `hard`: {key: widths} the widths (a mask of WIDTHS) at which a rule hides the element outright;
    `sibling`: {key: [(combinator, previous keys, widths)]} the same for rules that hit an element only after a
    sibling (`img.g-img + div`), checked against its earlier siblings as the page is read;
    `soft`: {key: {prop: slot}} (see _cascade) the colour, text fill colour, background and font size the rules give
    it at DESKTOP width, and `op`/`zoom` the lowest opacity and zoom any rule gives it;
    `customs`: {name: [values]} the custom properties (`--x`) declared anywhere."""
    def __init__(self):
        self.hard, self.sibling, self.soft, self.customs = {}, {}, {}, {}


def _rank(e):
    return (e["imp"], e["rank"])


MAX_PURE = 50   # distinct simple selectors kept per key and property; more are kept as rules that may hit


def _cascade(slot, new):
    """Files a rule's value for a key into its slot. A rule with a simple selector (`.b`, `p.b`, `#k.a`; written with
    no at-rule around it and no escape in its value) surely hits an element that carries all its parts, `need`; it is
    kept per `need` ("pure"). For any other rule (`.a .b`, `.b:first-child`, under @media) it is unknown whether it
    hits: the slot keeps the highest-ranked (important, specificity, order) such value that hides text ("sticky")
    and that does not ("loose"). A pure value that hides text is kept as sticky too, since class names may match
    whatever their case. _winner picks between them for an element."""
    slot = slot or {"pure": {}, "sticky": None, "loose": None}
    need = new["need"]
    if need is not None and (need in slot["pure"] or len(slot["pure"]) < MAX_PURE):
        if need not in slot["pure"] or _rank(new) >= _rank(slot["pure"][need]):
            slot["pure"][need] = new
        if not new["sticky"]:
            return slot
    kind = "sticky" if new["sticky"] else "loose"
    if slot[kind] is None or _rank(new) >= _rank(slot[kind]):
        slot[kind] = new
    return slot


def _winner(slots, has):
    """The value a property takes for an element that carries the parts `has` (its tag, and its classes and id as
    written), from the slots of all its keys, as a browser's cascade picks it: the highest-ranked rule that surely
    hits it, unless a rule that may hit it ranks higher. Then, if any such rule hides the text, the text counts as
    hidden (when unsure, hide more)."""
    exact = max((e for s in slots for n, e in s["pure"].items() if n <= has), key=_rank, default=None)
    found = ([exact] if exact else []) + [s[k] for s in slots for k in ("sticky", "loose")
                                          if s[k] and (exact is None or _rank(s[k]) > _rank(exact))]
    sticky = [f for f in found if f["sticky"]]
    return max(sticky or found, key=_rank, default=None)


SIMPLE = re.compile(r"(?:[a-zA-Z][a-zA-Z0-9]*)?(?:[.#][a-zA-Z0-9_-]+)*")


def _need(one, plain):
    """The parts an element must carry for a simple selector to surely hit it (tag in lower case, classes and id as
    written), or None when the selector is not that simple or a rule around it may not apply."""
    one = one.strip()
    if not plain or not one or not SIMPLE.fullmatch(one):
        return None
    tag = re.match(r"[a-zA-Z][a-zA-Z0-9]*", one)
    return frozenset(([tag.group(0).lower()] if tag else []) + re.findall(r"[.#][a-zA-Z0-9_-]+", one))


def _escaped(text):
    """The properties whose value a declaration block writes with a `\\` escape: a browser may read such a value
    differently (`14px\\9` is an old IE hack), so it never surely beats another rule."""
    out = set()
    for d in _strip_comments(text or "")[:20000].split(";"):
        if ":" in d and "\\" in d.split(":", 1)[1]:
            out.add(_unescape_css(d.split(":", 1)[0]).strip().lower())
    return out


def _style_rules(markup):
    """A _Rules from the message's <style> blocks. A rule that would hide text but whose elements cannot be named
    makes the message TooComplex."""
    r, count, order, sibling = _Rules(), 0, 0, 0
    blocks, r.customs = _style_text(markup)
    unique = list(dict.fromkeys(blocks))   # the parser and the string scan mostly find the same blocks
    for block in blocks:
        count += len(_rules(block))
        if count > MAX_RULES:
            raise TooComplex("style rules over MAX_RULES")
    for block in unique:
        for widths, plain, prelude, body in _rules(block):
            if widths and "--" in body:
                _customs(body, r.customs)
    for block in unique:   # a second pass, so every custom property is known before a background uses one
        for widths, plain, prelude, body in _rules(block):
            if not widths:
                continue
            order += 1
            d = _decls(body)
            important, escaped = _important(body), _escaped(body)
            hides = _hard_hides(d)
            try:
                bg, unreadable = _bg_of(d, r.customs), None
            except TooComplex as e:   # fatal only when the rule hits an element (not for `:hover` or the like)
                bg, unreadable = "", e
            props = {k: v for k, v in (("color", d.get("color", "")), ("fill", d.get("-webkit-text-fill-color", "")),
                                       ("bg", bg), ("fs", d.get("font-size", "")),
                                       ("op", d.get("opacity", "")), ("zoom", d.get("zoom", ""))) if v}
            if not hides and not props and not unreadable:
                continue
            op = min(_factor(props.get("op")) or 1.0, 1.0) * min(_factor(props.get("zoom")) or 1.0, 1.0)
            pair = "bg" in props and any(_invisible(props[c], props["bg"], 16.0) for c in ("color", "fill") if c in props)
            # Hides text by itself, whatever the element inherits: a keyword (`inherit`) is not such a value.
            real = {p: v for p, v in props.items() if v not in KEYWORDS}
            alone = hides or op <= 0.05 or any(_hiding_value(p, real[p]) for p in ("color", "fill", "fs") if p in real) \
                or "bg" in real and any(_invisible(real[c], real["bg"], 16.0) for c in ("color", "fill") if c in real)
            desk = bool(widths & DESK)
            for one in prelude.split(","):
                keys, comb, prev = _selector_keys(one)
                need = _need(one, plain)
                if unreadable and keys != []:
                    raise unreadable
                if keys is None:
                    if desk and (alone or op < 1 or _invisible(
                            props.get("color", ""), props.get("bg", ""), _px(props.get("fs", ""), 16.0))):
                        raise TooComplex("a hiding rule for elements this cleaner cannot name")   # `[data-x]`, `*`
                    continue
                # Off the desktop width, or after a sibling, a rule that hides text by itself is kept as a hiding
                # rule for those widths or that sibling; one that only sets a colour is left out.
                hard_mask = widths if hides or (alone and (comb or not desk)) else 0
                for k in keys:
                    if hard_mask and comb:
                        sibling += 1
                        if sibling > MAX_SIBLING:
                            raise TooComplex("sibling rules over MAX_SIBLING")
                        r.sibling.setdefault(k, []).append((comb, tuple(prev), hard_mask))
                    elif hard_mask:
                        r.hard[k] = r.hard.get(k, 0) | hard_mask
                    if not desk or (comb and alone):
                        continue
                    cur = r.soft.setdefault(k, {})
                    for prop, v in props.items():
                        if prop in ("op", "zoom"):   # the lowest any rule gives the key
                            f = _factor(v)
                            if f is not None and f < cur.get(prop, 1.0):
                                cur[prop] = f
                            continue
                        name = {"fs": ("font-size", "font"), "bg": ("background", "background-color"),
                                "fill": ("-webkit-text-fill-color",)}.get(prop, (prop,))
                        new = {"v": v, "imp": any(n in important for n in name), "rank": (_specificity(one), order),
                               "sticky": _hiding_value(prop, v) or (pair and prop in ("color", "fill", "bg")),
                               "need": None if any(n in escaped for n in name) else need}
                        cur[prop] = _cascade(cur.get(prop), new)
    return r


def _hiding_value(prop, v):
    if prop == "fs":
        return _px(v, 16.0) < 2
    if prop == "fill":
        return v not in KEYWORDS and _hiding_value("color", v)
    if prop == "color":
        rc = _rgba(v)
        return rc is None or rc[3] <= 0.2 or min(rc[:3]) >= 0xF0
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


QUOTE_KEYS = (".gmail_quote", ".gmail_quote_container", ".yahoo_quoted", ".moz-cite-prefix", "blockquote")
QUOTE_REST = ("#divrplyfwdmsg", "#appendonsend")   # Outlook: the quote follows these, to the end of the message
HEAD_TAGS = {"head", "meta", "link", "style", "title", "script", "base", "noscript", "template", "xml", "o:officedocumentsettings"}
MAX_DEPTH = 256   # deeper nesting is TooComplex: no real mail needs it, and it keeps every step cheap


class _Visible(html.parser.HTMLParser):
    CDATA_CONTENT_ELEMENTS = RAW_TEXT

    def __init__(self, rules=None, strip_quotes=False):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.removed = [], [], {"html_comments": 0, "hidden_elements": 0}
        self.rules = rules or _Rules()
        self.strip_quotes, self.quoted, self.drop_rest = strip_quotes, False, False
        self.open = {}   # tag -> how many are open: an end tag with none open costs nothing
        self.top = {"prev": (), "seen": set()}   # the siblings read so far outside any element
        self.conditionals = []   # the text of Outlook conditional comments, checked against the visible text at the end
        self.bgs = {}

    def _bg(self, d):
        """_bg_of for an inline style, worked out once per distinct value (a var() one can be long to follow)."""
        key = (d.get("background-color"), d.get("background"), d.get("background-image"))
        if key not in self.bgs:
            self.bgs[key] = _bg_of(d, self.rules.customs)
        return self.bgs[key]

    def _pop_to(self, i):
        for e in self.stack[i:]:
            self.open[e["tag"]] -= 1
        del self.stack[i:]

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self.out.append("\n")
        if self.open.get("head") and tag not in HEAD_TAGS:
            # `</head>` may be left out: a browser ends <head> at <body> or the first tag that belongs in the body.
            self._pop_to(next(i for i, e in enumerate(self.stack) if e["tag"] == "head"))
        a = {k.lower(): (v or "") for k, v in attrs}
        ident = a.get("id", "").strip().lower()
        keys = [tag] + (["#" + ident] if ident else []) + ["." + c.lower() for c in a.get("class", "").split()]
        # Rules with a sibling combinator: `+` looks at the element just before this one, `~` at any before it.
        box = self.stack[-1] if self.stack else self.top
        widths = 0
        for k in keys:
            for comb, prev, w in self.rules.sibling.get(k, ()):
                if any(p in (box["prev"] if comb == "+" else box["seen"]) for p in prev):
                    widths |= w
        box["prev"] = keys; box["seen"].update(keys)
        if tag in VOID:
            return
        if len(self.stack) >= MAX_DEPTH:
            raise TooComplex("elements nested too deep")
        soft = self.rules.soft
        has = frozenset([tag] + (["#" + a["id"].strip()] if a.get("id", "").strip() else []) +
                        ["." + c for c in a.get("class", "").split()])   # its parts as written, for simple selectors
        props, locked = {}, set()
        for prop in ("color", "fill", "bg", "fs"):   # style-block rules first, then the element's own attributes
            best = _winner([soft[k][prop] for k in keys if prop in soft.get(k, {})], has)   # all its keys' rules
            if best:
                props[prop] = best["v"]
                if best["imp"]:
                    locked.add(prop)   # an !important rule beats the element's own (normal) style
        inline = _style(attrs)
        own = {}
        if tag == "font" and a.get("color"):
            own["color"] = a["color"].lower()
        if a.get("bgcolor"):
            own["bg"] = a["bgcolor"].lower()
        if tag == "body" and a.get("text"):
            own["color"] = a["text"].lower()
        own.update({k: v for k, v in (("color", inline.get("color", "")), ("fill", inline.get("-webkit-text-fill-color", "")),
                                      ("bg", self._bg(inline)), ("fs", inline.get("font-size", ""))) if v})
        for prop, v in own.items():
            if prop not in locked:
                props[prop] = v
        parent = self.stack[-1] if self.stack else {"color": "", "fill": "", "bg": "", "px": 16.0, "opacity": 1.0,
                                                    "zoom": 1.0, "widths": 0, "inside": False, "in_quote": False}
        color = props.get("color", "")
        color = parent["color"] if color in ("", "inherit", "currentcolor", "unset", "revert") else \
            ("" if color == "initial" else color)
        fill = props.get("fill", "")   # -webkit-text-fill-color paints the text in place of `color`, and is inherited
        fill = parent["fill"] if fill in ("", "inherit", "unset", "revert") else \
            ("" if fill in ("currentcolor", "initial") else fill)
        bg = props.get("bg", "")
        bg = parent["bg"] if bg in ("", "inherit") else bg
        px = _px(props.get("fs", ""), parent["px"])
        own_op, own_zoom = 1.0, 1.0
        for k in keys:
            own_op = min(own_op, soft.get(k, {}).get("op", 1.0))
            own_zoom = min(own_zoom, soft.get(k, {}).get("zoom", 1.0))
        own_op = min(own_op, _factor(inline.get("opacity")) or 1.0)
        own_zoom = min(own_zoom, _factor(inline.get("zoom")) or 1.0)
        opacity = parent["opacity"] * own_op
        zoom = parent["zoom"] * own_zoom   # zoom shrinks everything in the element, text of any size too
        quote = self.strip_quotes and any(k in QUOTE_KEYS for k in keys)
        if self.strip_quotes and any(k in QUOTE_REST for k in keys):
            self.drop_rest = True   # Outlook puts the quoted message after this header, not inside it
        for k in keys:
            widths |= self.rules.hard.get(k, 0)
        widths |= parent["widths"]   # hidden at a width by an ancestor: hidden at that width here too
        # Elements a browser does not show unless told to: <datalist>, <rp> (ruby fallback), a <dialog> without
        # `open`, and in a <details> without `open` everything but its first <summary>.
        closed = parent.get("closed") and not (tag == "summary" and not parent.get("summary_seen"))
        if parent.get("closed") and tag == "summary":
            parent["summary_seen"] = True
        hard = tag in SKIP_TAGS or "hidden" in a or a.get("aria-hidden", "").lower() == "true" or \
            _hard_hides(inline) or opacity <= 0.05 or zoom <= 0.05 or bool(widths) or \
            tag in ("datalist", "rp") or (tag == "dialog" and "open" not in a) or bool(closed)
        if hard and tag not in SKIP_TAGS and not parent["inside"]:
            self.removed["hidden_elements"] += 1
        # Everything a text node needs is worked out here, once, so each piece of text costs the same at any depth.
        self.stack.append({"tag": tag, "hard": hard, "color": color, "fill": fill, "bg": bg, "px": px,
                           "opacity": opacity, "zoom": zoom, "widths": widths, "inside": parent["inside"] or hard,
                           "in_quote": parent["in_quote"] or quote, "counted": tag not in SKIP_TAGS or tag in CODE_TAGS,
                           "closed": tag == "details" and "open" not in a, "prev": (), "seen": set()})
        self.open[tag] = self.open.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        # A browser ignores the `/` of `<div/>`: the element stays open, so what follows is inside it.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        # Close the nearest open tag of this name (mail HTML is sloppy), but never across a table cell, row or table:
        # a browser ignores `</div>` inside a cell whose div opened outside it, so a hidden block stays hidden.
        if self.open.get(tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] == tag:
                    self._pop_to(i)
                    break
                if self.stack[i]["tag"] in SCOPE and tag not in SCOPE:
                    break
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        top = self.stack[-1] if self.stack else None
        if top and top["in_quote"] or self.drop_rest:
            self.quoted = self.quoted or bool(data.strip())   # said only when quoted text was really left out
            return
        if top and top["inside"]:
            if data.strip():
                # Text in a tag a page never shows (noscript, template, svg, text loose in <head>) is counted once
                # per tag; the innermost such tag decides, so a <style> or <title> in <head> counts nothing.
                for e in reversed(self.stack):
                    if e["hard"] and e["tag"] in SKIP_TAGS:
                        if not e["counted"]:
                            e["counted"] = True; self.removed["hidden_elements"] += 1
                        break
            return
        if top and data.strip() and (top["closed"] or _invisible(top["color"], top["bg"], top["px"] * top["zoom"]) or
                                     top["fill"] and _invisible(top["fill"], top["bg"], top["px"] * top["zoom"])):
            if not top.get("soft_counted"):
                top["soft_counted"] = True; self.removed["hidden_elements"] += 1
            return
        self.out.append(data)

    def handle_comment(self, data):
        self._comment(data)

    def _comment(self, data):
        text = _conditional(data)
        if text is None:
            self.removed["html_comments"] += 1
        elif text:
            self.conditionals.append(text)

    def handle_pi(self, data):
        if not data.lower().startswith("xml"):   # `<?xml version..?>` heads XHTML templates
            self.removed["html_comments"] += 1

    def unknown_decl(self, data):
        self._comment(data)

    def close(self):
        super().close()
        # An Outlook conditional that holds text (a VML "bulletproof button") is counted as a hidden comment only when
        # its text is not also shown outside it: most templates write the same button for the other clients.
        shown = _squash("".join(self.out))
        self.removed["html_comments"] += sum(1 for t in self.conditionals if t not in shown)


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


def _squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _conditional(data):
    """Outlook's conditional comments (`<!--[if mso]>..<![endif]-->`, `<!--[if !mso]><!-->`, `<!--<![endif]-->`):
    in almost every mail a tool writes. Returns None for any other comment; "" for a conditional holding only markup,
    Outlook's own styles or its XML settings (not counted); else the text it holds (shown only in Outlook), which is
    dropped and counted as a comment unless the same text is also shown outside it."""
    d = data.strip().lower()
    if len(d) > 20000 or not re.match(r"\[?(?:end)?if\b|<!\[endif\]", d):
        return None
    d = re.sub(r"^\[?(?:end)?if\b[^\]>]*\]?>?", "", d)
    d = _cut_blocks(_cut_blocks(d, "style"), "xml")
    return _squash(html.unescape(re.sub(r"<[^<>]*>|<!\[endif\]|<!", " ", d)).strip(" >\t\r\n"))


def visible_text(markup, strip_quotes=False):
    """(text, removed) for an HTML body: only what a person sees. With strip_quotes (mail the owner sent), the
    quoted earlier message is left out too: it is the other side's words, not the owner's."""
    rules = _style_rules(markup)   # TooComplex goes up: never read with rules unknown
    markup = markup[:MAX_MARKUP]    # text past the cut is dropped, never shown
    p = _Visible(rules, strip_quotes)
    try:
        p.feed(markup); p.close()
    except TooComplex:
        raise
    except Exception:   # malformed beyond the parser: keep nothing rather than the raw markup
        return "", {"html_comments": 0, "hidden_elements": 1}
    text = "".join(p.out)
    if strip_quotes:   # Outlook quotes with no marker element: cut at its "From: .. Sent:" block or "On .. wrote:"
        m = QUOTE_START.search(text) or OUTLOOK_QUOTE.search(text)
        if m:
            text, p.quoted = text[:m.start()], True
    if p.quoted:
        p.removed["quoted_reply"] = 1
    return text, p.removed


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


def bulk_or_automatic(message):
    """True when the message's own headers mark it as list or automatic mail (List-Unsubscribe, List-Id,
    Precedence bulk/list/junk, or Auto-Submitted other than "no"): the skill's skip rule reads this."""
    for h in _top_headers(message):
        n, v = h["name"].lower(), h["value"].strip().lower()
        if n in ("list-unsubscribe", "list-id") or (n == "precedence" and v in ("bulk", "list", "junk")) \
                or (n == "auto-submitted" and v and v != "no"):
            return True
    return False


def sent_by_owner(message):
    """True when Gmail labels the message SENT: the owner wrote it, so there is no sender check to read. The label is
    Gmail's own, never a header the sender writes."""
    labels = _message(message).get("labelIds")
    return isinstance(labels, list) and "SENT" in {str(x).upper() for x in labels}


def _auth_parts(value):
    """An Authentication-Results value split at its `;` separators, as RFC 8601 reads it: a `;` inside a quoted string
    or a `(...)` comment (nested, with `\\` escapes) is not a separator. Comments become a space; a quoted string
    becomes `""`, so nothing inside one is ever read as a result. An unterminated quote or comment runs to the end."""
    parts, cur, depth, quoted, i = [], [], 0, False, 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and (quoted or depth):
            i += 2
            continue
        if quoted:
            quoted = ch != '"'
        elif depth:
            depth += {"(": 1, ")": -1}.get(ch, 0)
            if not depth:
                cur.append(" ")
        elif ch == '"':
            quoted = True; cur.append('""')
        elif ch == "(":
            depth = 1
        elif ch == ";":
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
        i += 1
    return parts + ["".join(cur)]


def _auth(results):
    """spf/dkim/dmarc from Gmail's own Authentication-Results, or "none". Gmail adds its line on top of any the
    sender wrote, so only the topmost header counts, and only when its authserv-id is Gmail's own. Each result is read
    only where a resinfo starts (`; dkim=pass`): never from a comment, a quoted string or a property value. Any failing
    DKIM signature makes dkim "fail"."""
    found = {}
    parts = _auth_parts(results[0].lower()[:4000]) if results else [""]
    if parts[0].split()[:1] != ["mx.google.com"]:   # the authserv-id, then an optional version
        return {mech: "none" for mech in ("spf", "dkim", "dmarc")}
    for part in parts[1:]:
        m = re.match(r"\s*(spf|dkim|dmarc)\s*=\s*([a-z]+)(?![a-z0-9.-])", part)
        if m:
            mech, res = m.groups()
            if mech not in found or (mech == "dkim" and res == "fail"):
                found[mech] = res
    return {mech: found.get(mech, "none") for mech in ("spf", "dkim", "dmarc")}


def _pictographic(ch):
    o = ord(ch)
    return 0x1F000 <= o <= 0x1FAFF or 0x2190 <= o <= 0x2BFF or 0x2300 <= o <= 0x23FF or o in (0x00A9, 0x00AE, 0x20E3) \
        or ch.isdigit() or ch in "#*"


def _kept(text, i, ch):
    """Characters that are invisible but part of ordinary writing stay and are not counted: an emoji's variation
    selector (❤️) or a joiner between two emoji (family and flag sequences); a direction mark or ZWNJ between letters
    (Hebrew, Arabic, Persian). Anywhere else, or in a run, they are removed and counted."""
    prev = text[i - 1] if i else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if ch in "\ufe0e\ufe0f":
        return bool(prev) and _pictographic(prev)
    if ch == "\u200d":
        return bool(prev) and bool(nxt) and (_pictographic(prev) or prev == "\ufe0f") and _pictographic(nxt)
    if ch in "\u200c\u200e\u200f":
        return prev.isalpha() and (nxt.isalpha() or nxt in " .,!?") or (prev in " .,!?" and nxt.isalpha())
    return False


LINE_BREAKS = re.compile("[\u2028\u2029\u0085\x1c\x1d\x1e]")


def clean(text, removed):
    # No entity decoding here: the HTML parser already turned entities into what a reader sees, and plain text shows
    # `&#8203;` as those characters, so decoding it again would make text no one saw.
    # Characters a reader or a model may take as a line break (Unicode line and paragraph separators, NEL, the
    # file/group/record separators) become a real one, so the view's `| ` prefix starts every line a reader sees.
    text = LINE_BREAKS.sub("\n", text)
    count = [0]

    def drop(m):
        if _kept(text, m.start(), m.group(0)):
            return m.group(0)
        count[0] += 1
        return ""
    text = INVISIBLE.sub(drop, text)
    if count[0]:
        removed["invisible_characters"] = removed.get("invisible_characters", 0) + count[0]
    for rx in (WRAPPED, HEX_PAIRS):
        hits = rx.findall(text)
        if hits:
            removed["encoded_blobs"] = removed.get("encoded_blobs", 0) + len(hits)
            text = rx.sub("[encoded text removed]\n", text)
    # A link's path (a commit hash, a tracking id) is not a blob; a run inside a URL is cut only when very long.
    pieces = URL.split(text)
    for i, piece in enumerate(pieces):
        # In a link, hash-shaped hex (a commit id, a checksum: 32 to 64 hex digits) is not counted toward a blob.
        # At most two such runs are let off, and a run of 200 or more is a blob whatever it holds.
        is_blob = (lambda m: len(m.group(0)) >= 200 or len(re.sub(r"[0-9a-f]{32,64}", "", m.group(0), count=2)) >= 80) \
            if i % 2 else (lambda m: True)
        hits = [m for m in BLOB.finditer(piece) if is_blob(m)]
        if hits:
            removed["encoded_blobs"] = removed.get("encoded_blobs", 0) + len(hits)
            pieces[i] = BLOB.sub(lambda m: "[encoded text removed]" if is_blob(m) else m.group(0), piece)
    text = "".join(pieces)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


OUTLOOK_QUOTE = re.compile(r"(?im)^\s*from:[^\n]{1,300}\n\s*(?:sent|date):")
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
        body = body[:MAX_MARKUP]
        text, r = (visible_text(body, strip_quotes=sent) if re.search(r"<!--|</?(?:html|body|head|div|p|br|span|table|td|tr|font|style|img|b|i|u|a\s)\b", body, re.I) else (body, {}))
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
            "text": text[:MAX_TEXT], "removed": removed, "truncated": truncated, "quoted_reply_removed": quoted,
            "bulk": bulk_or_automatic(message)}


SAVE_HEADERS = ("from", "to", "cc", "date", "subject", "message-id")
CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")   # C0/C1 controls and the Unicode line and paragraph separators


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
