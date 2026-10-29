# Inbound items: forms, bookings and webhooks

Your website's contact form, a booking page or a webhook can put work on your board without being able to run
Keeptrack itself. Each one saves a small file in your board repo's `board/inbound/` folder. A scheduled run (or you)
then turns those files into board work and removes them.

## What happens to an item

Each source (for example `rainshift-contact` for a contact form) has one of two modes:

- **Review** (the default): the item becomes suggestions in your [Review Inbox](review-inbox.md): a new task, and a new
  person when the sender is not on the board yet. Nothing reaches the board until you accept it. Use this for anything
  you do not fully trust, such as a public form that anyone can fill in.
- **Card**: the card and the person are made straight away. Use this only for a source you trust.

The same item never makes two cards or two suggestions, even when the form sends it twice.

Text in an item comes from outside your board. Keeptrack shows it as plain text, and your assistants are told to treat
it as information, never as instructions.

## Switch a source between review and card

Ask your assistant, or run in the board repo:

```
python3 board/keeptrack.py inbound-source rainshift-contact --mode card     # make cards straight away
python3 board/keeptrack.py inbound-source rainshift-contact --mode review   # back to the Review Inbox
python3 board/keeptrack.py inbound --status                                 # see the sources and what is waiting
```

Card mode can also assign the card, add labels and a checklist, and set the new person's stage:
`--assign JezHub --label enquiry --todo "Reply within one working day" --stage New`. Only a person can switch a source
to card mode; an assistant running on a schedule cannot.

## When something is stuck

An item that cannot be handled stays in `board/inbound/` with the reason saved, and the others go on. The web board
shows a strip under the header when an item failed, or has waited longer than two hours
(`settings.inbound_alert_minutes`), and `keeptrack.py list --attention` lists them. Ask your assistant to run
`keeptrack.py inbound --status` to see why.

## What runs it

Something has to run `keeptrack.py inbound` regularly: a scheduled Claude task (hourly), a scheduled job on your own
computer, or GitHub Actions where your account can use them. Setup steps for each, and the file format for whoever
builds the form: [`board/INBOUND.md`](../../board/kit/INBOUND.md).
