# One owner choice, one linked Inbox question

Use `python3 board/keeptrack.py comment CARD --owner-question FILE_OR_- --json` when an agent asks the owner to
choose on a card. It generates one canonical comment, one scored/recommended Inbox choice and one durable receipt
in a single save. Plain comments stay plain; the tool does not guess intent from prose. Do not combine structured
mode with plain text or a reply. Relay's structured comment tool supplies the same JSON on stdin.

```json
{
  "version": 1,
  "request_id": "original-message-1",
  "question": "Which approach?",
  "waiting": "Implementation waits on a choice.",
  "viewpoints": [
    {"who": "User", "wants": "Predictability"},
    {"who": "Maintainer", "wants": "Simple support"}
  ],
  "options": [
    {"key": "focused", "label": "Focused change", "score": 9, "reason": "Small reversible change", "basis": "judgement"},
    {"key": "wait", "label": "Wait", "score": 5, "reason": "Delays the improvement", "basis": "judgement"}
  ],
  "recommended": "focused",
  "recommendation_reason": "Support cost decides it.",
  "next_step": "Prepare the chosen change for review."
}
```

Use the same stable original request ID and exact payload after an uncertain outcome. The same request and
canonical payload return the original IDs with `created: false`; changing an existing question refuses. Do not
invent a fresh ID merely to bypass that refusal. Pending, answered, ignored, lapsed and full archived questions
retain identity. If an archive has retired the original detail, the command refuses recreation explicitly rather
than claiming it verified content that no longer exists. Receipts survive trimmed comment/history lists.

The canonical board kit owner is the decider. A card assigned solely to another member is outside this path.
Ownership, target scope and actual saved question/comment content are checked again after a save conflict. New
structured writes require schema4 split storage and adopt minimum kit143. Ordinary comments do not raise the floor.
Older writers then refuse rather than discard binding metadata. Hosted phase0 and proposal-only mode refuse this
combined card/Inbox write. No timer, setting or live activation is installed.

The result contains `card_id`, `comment_id`, `proposal_id`, `created`, `comment_url` and `inbox_url`. Remote URLs use
only the configured repository, branch and path. Local `--file` fixtures return null URLs; they do not claim to be
live board data. Exact `#proposal=r_id` links reveal and focus an active Inbox item without answering it. Missing or
archived items offer the original linked card. The reverse link opens the original comment.

Inputs are at most16KiB UTF8 before JSON allocation, depth8,96 containers and512 structural tokens. Leaf symlinks,
FIFOs, directories and blank paths refuse; Linux file reads pin a regular inode, while stdin uses a bounded binary
reader. Fields are nonempty one-line text with control/invisible characters refused. Privacy screening covers
secrets, contacts, addresses, health, money, HR and instruction-shaped text before writing. Link to a private document
instead of putting sensitive detail in the question. Errors never echo the rejected text or request ID.

There must be two-to-three viewpoints and two-to-four options with unique short keys. Scores are integers0–10,
and `recommended` names exactly one option. Each basis is `judgement` or `{ "url": "https://…", "title": "Evidence" }`.
Per-field limits and combined300-character Inbox question/context limits are checked without truncation; shorten
the wording when refused. The generated Markdown comment is limited to4000 characters.

An Inbox answer is data. It does not grant merge/research authority, clear a wait/hold, claim or approve a task,
wake a dispatcher or produce a signed owner action. Protected work keeps its existing separate proof and checks.
