# Write a good card

A card is a note to a person who was not there. That person can be a teammate, an agent, or you in three weeks. They
open the card with no other context. A good card lets them understand the work and start it without asking anyone.

Agents: read this before you add a card, change a card, propose a card in the Review Inbox, or import tasks. People:
use it as a checklist when a card feels thin.

## The five tests

A good card passes all five. A bad card fails one or more.

1. **The title says the outcome in plain words.** A reader who sees only the title knows what changes when the card
   is done. Start with a verb. Do not use internal codes, ids or abbreviations that need a lookup ("AT-56",
   "cap-o2004d", "C239") as the main words. You can put them later in the details.
2. **The details say what, why and what "done" means.** One short paragraph: the current state, why it matters, and
   the decision or result that finishes the card. Write full sentences. Explain each term that a newcomer does not
   know, or link to a page that explains it.
3. **Each to-do is one step that a person can do and tick.** Write it as an action ("Choose A or B for the meeting
   notes rule"), not as a code or a label. If a step needs a decision, give the options.
4. **Every source is in the card's links.** When the card talks about a pull request, an issue, a document, a design,
   a file, a folder, a meeting note or a web page, add that item to the card's **links** section with a clear title.
   A number in the text ("see #2296") is not a link. The links section is what people click, what the Pull requests
   panel reads, and what `keeptrack-search` and `links` search.
5. **Nothing secret is in the card.** Link to where confidential material lives. Do not copy it into the card.

## Links: what goes in the links section

Add a link each time the card names or depends on one of these:

| The card mentions | Link it like this |
|---|---|
| A pull request | `link '#12' https://github.com/acme/app/pull/481 --title "PR #481: recap posts no tasks"` |
| An issue or ticket | `link '#12' https://github.com/acme/app/issues/77 --title "Issue #77: duplicate tasks"` |
| A document, spec or design | `link '#12' https://github.com/acme/app/blob/main/docs/spec.md --title "Spec: meeting tasks"` |
| A Drive, Dropbox or OneDrive file or folder | `link '#12' <share url> --title "Proposal draft (Drive)"` |
| A web page or outside documentation | `link '#12' https://example.com/api-docs --title "Vendor API docs"` |
| A local folder on one computer | `link '#12' ~/work/acme/notes --title "Notes folder (Sam's laptop)"` |
| Another card | `relate '#12' '#31'` (or `--after '#31'` when this card must wait for it) |

Rules:
- Use the full URL, not a short reference. `#2296` means a card number on the board, not a pull request.
- Give each link a title that says what it is and why it matters ("PR #481: the change that raised these questions").
- Add the link when you write the text that mentions it, not later.
- When you open a pull request for a card, link it at once (`link '#N' <PR url> --title "PR"`).
- When a link stops being useful (a closed draft, a moved file), remove it with `unlink`, or say in its title that it is
  old.

## Example: a bad card

```text
#58  Decide three map questions from app #2296                    (no links)

Details: From the cap-o2004 reconcile (app #2296, merged 13 Oct).
Recommendations: AT-56, change the Then to match #2146; AT-59, move it to
request/response altitude; AT-8, a time-anchored link, kept as not built.

To-dos:
  [ ] cap-o2004d AT-56: match #2146 (smart notes feed task drafts) or reverse #2146
  [ ] cap-o2004g AT-59: fix the altitude mismatch
  [ ] cap-o2004b AT-8: decide what 'moment in the transcript' means
  [ ] Update the three rows to match the answers
```

Why it is bad:
- The title says "three map questions" but not what the questions are about.
- "AT-56", "the Then", "altitude" and "cap-o2004d" are internal terms. A newcomer cannot read them.
- It names two pull requests (#2296 and #2146) but has no links. A reader cannot open them, and `#2146` looks like a
  board card.
- It does not say what "done" is, who decides, or where the answers go.

## Example: the same card, written well

```text
#58  Decide 3 open questions about tasks made from meeting notes

Details:
A test review of the "tasks from meetings" feature (PR #2296, merged 13 Oct)
found three places where the written spec and the shipped product disagree.
The review did not change the spec, because each one needs a product decision
from the owner. This card is done when each question has an answer and the
three spec entries match it.

Background: the spec is a list of acceptance tests ("AT-" numbers). Each test
says what the product must do. "Altitude" means where a test checks the
product: in the data, in a server reply, or on screen in a browser.

To-dos:
  [ ] Meeting notes: Gemini's notes now feed the task draft (PR #2146). Keep
      that and update test AT-56, or remove it again?
  [ ] Quick review: the review screen changed to one row at a time (PR #2292).
      Agree the new wording for test AT-59, and say if it is checked on screen
      or in the server reply.
  [ ] Task source link: should a task link to the exact moment in the meeting
      recording (needs a new time field), or to the whole transcript (works
      today)? This decides test AT-8.
  [ ] Update the three spec entries to match the answers.

Links:
  PR #2296: the review that raised these questions
  PR #2146: meeting notes feed the task draft
  PR #2292: new one-row-at-a-time review screen
  Spec entry for AT-56 (cap-o2004d.md)
  Spec entry for AT-59 (cap-o2004g.md)
  Spec entry for AT-8 (cap-o2004b.md)
```

Why it is good:
- The title says what the decision is about, in words the owner uses.
- The details give the current state, why it matters, and what "done" means.
- The background explains the two internal terms once.
- Each to-do is a question with its options.
- Every pull request and document that the card mentions is in the links section.

## More short examples

| Bad | Good |
|---|---|
| `Fix bug` | `Stop the recap sending the same task twice when a meeting syncs again` |
| `Acme stuff` | `Send Acme the revised proposal (pricing page changed)`, with the Drive link to the draft |
| `Follow up on PR` | `Answer the review comments on PR #481`, with the PR in links |
| `Check C239` | `Check if the export change in PR #1701 still needs a decision`, with the PR in links |
| `Look at docs` | `Read the vendor's rate-limit docs and set our retry limits`, with the docs page in links |

## For agents

- Before you `add` or `propose` a card, check it against the five tests above.
- When you change a card (`task-set`, `todo-add`, `comment`) and your text names a PR, issue, document or page, add the
  link in the same run.
- When you find a card that fails a test while you work on it, fix the card if it is yours to change, or say so in a
  comment.
- Keep the card short. Put long content in a document and link it.
