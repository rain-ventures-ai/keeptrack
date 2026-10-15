# Write a good card

A card is a note to a person who was not there. That person can be a teammate, an agent, or you in three weeks. They
open the card with no other context. A good card lets them understand the work and start it without asking anyone.

Agents: read this before you add a card, change a card, propose a card in the Review Inbox, or import tasks. People:
use it as a checklist when a card feels thin.

## The five tests

A good card passes all five. A bad card fails one or more.

1. **The title says the outcome in plain words.** A reader who sees only the title knows what changes when the card
   is done. Start with a verb. Do not use internal codes, ids or abbreviations that need a lookup ("AT-56",
   "SPEC-12", "C239") as the main words. You can put them later in the details.
2. **The details say what, why and what "done" means.** One short paragraph: the current state, why it matters, and
   the decision or result that finishes the card. Write full sentences. Explain each term that a newcomer does not
   know, or link to a page that explains it.
3. **Each to-do is one step that a person can do and tick.** Write it as an action ("Choose A or B for the meeting
   notes rule"), not as a code or a label. If a step needs a decision, give the options.
4. **Every source is in the card's links.** When the card talks about a pull request, an issue, a document, a design,
   a file, a folder, a meeting note or a web page, add that item to the card's **links** section with a clear title.
   A number in the text ("see #481") is not a link. The links section is what people click, what the Pull requests
   panel reads (for PRs), and what `keeptrack-search` and `links` search.
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
| Another card | `relate '#12' '#31'`, or `task-set '#12' --after '#31'` when this card must wait for it |

Rules:
- Use the full URL, not a short reference. `#481` means a card number on the board, not a pull request.
- Give each link a title that says what it is and why it matters ("PR #481: the change that raised these questions").
- Add the link when you write the text that mentions it, not later.
- When you open a pull request for a card, link it at once (`link '#N' <PR url> --title "PR"`). Use the bare PR URL
  (`https://github.com/<owner>/<repo>/pull/<n>`, no `/files`, `#...` or `?...`): the web board's Pull requests panel
  shows only links in that form.
- When a link stops being useful (a closed draft, a moved file), remove it with `unlink`, or say in its title that it is
  old.

## Example: a bad card

```text
#58  Decide three spec questions from app #481                    (no links)

Details: From the SPEC-12 review (app #481, merged last week).
Recommendations: AT-6, change the Then to match #452; AT-9, move it to
request/response altitude; AT-3, an anchored link, kept as not built.

To-dos:
  [ ] SPEC-12 AT-6: match #452 (notes feed the draft) or reverse #452
  [ ] SPEC-12 AT-9: fix the altitude mismatch
  [ ] SPEC-12 AT-3: decide what 'exact place' means
  [ ] Update the three rows to match the answers
```

Why it is bad:
- The title says "three spec questions" but not what the questions are about.
- "AT-6", "the Then", "altitude" and "SPEC-12" are internal terms. A newcomer cannot read them.
- It names two pull requests (#481 and #452) but has no links. A reader cannot open them, and `#452` looks like a
  board card.
- It does not say what "done" is, who decides, or where the answers go.

## Example: the same card, written well

```text
#58  Decide 3 open questions about tasks made from meeting notes

Details:
A test review of the "tasks from meetings" feature (PR #481) found three
places where the written spec and the shipped product disagree. The review
did not change the spec, because each one needs a product decision from the
owner. This card is done when each question has an answer and the three spec
entries match it.

Background: the spec is a list of acceptance tests ("AT-" numbers). Each test
says what the product must do. "Altitude" means where a test checks the
product: in the data, in a server reply, or on screen in a browser.

To-dos:
  [ ] Meeting notes: the shared notes now feed the task draft (PR #452).
      Keep that and update test AT-6, or remove it again?
  [ ] Quick review: the review screen changed to one row at a time (PR #470).
      Agree the new wording for test AT-9, and say if it is checked on screen
      or in the server reply.
  [ ] Task source link: should a task link to the exact place in the meeting
      recording (needs a new time field), or to the whole transcript (works
      today)? This decides test AT-3.
  [ ] Update the three spec entries to match the answers.

Links:
  PR #481: the review that raised these questions
  PR #452: meeting notes feed the task draft
  PR #470: new one-row-at-a-time review screen
  Spec: SPEC-12 (spec/meeting-tasks.md)
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

- Before you `add` a card or `proposal-add` one to the Review Inbox, check it against the five tests above.
- When you change a card (`task-set`, `todo-add`, `comment`) and your text names a PR, issue, document or page, add the
  link in the same run.
- When you find a card that fails a test while you work on it, fix the card if it is yours to change, or say so in a
  comment.
- Keep the card short. Put long content in a document and link it.
- When you name a card (in a reply, comment, done note, PR, brief or hand-off), write its number as a link:
  `keeptrack.py card-link '#58'` prints `[#58](<card link>)`. A person can then tap straight to the card.

## Bare cards and backlog auto-research

A **bare** card fails tests 2, 3 and 4 together: it has no to-dos, no links, and its details are shorter than 120
characters. `keeptrack.py list --column backlog --bare` lists them. The rule is fixed, so people and agents get the
same answer.

When the board setting **Backlog auto-research** is on (`settings.backlog_research`, Settings → Board, off by default),
the relay dispatcher picks a few bare Backlog cards each run and an agent researches each one. The research agent:

- **May** add details with `task-set '#N' --add-details "<text>"` (below what is there, never instead of it), add links
  with `link`, add to-dos with `todo-add`, and post one comment: what it found, what it could not find, and the
  questions only a person can answer (with `@<owner>`).
- **Must** finish with the `researched` label (`task-set '#N' --label researched --unlabel researching`), also when it
  found nothing useful, so the card is not picked again.
- **Never** moves, approves, claims, assigns, archives or deletes the card, and never changes its title, priority, due
  date, client or project. It never replaces text a person wrote, never changes a repo, and sends nothing outside the
  board.

Cards with the label `researched`, `researching`, `no-research`, `needs-human` or `held` are never picked. Put
`no-research` on a card to keep agents off it. Take `researched` off a card to let it be researched again.
