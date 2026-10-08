# Finding clients in email, calendar and invoices

Only if the person agreed. Read headers only: from, to, cc, date, subject. Never store the message text.

## Steps
1. Period: the last 12 months (24 if the person asks).
2. Collect the addresses the OWNER sent to, and the outside people in calendar events. Inbound mail alone is weak: anyone can email you.
3. Group by email domain. Each domain is a possible company. Personal domains (gmail.com, outlook.com, icloud.com, hotmail.com, yahoo.*, btinternet.com and the like) are grouped by person, not by company.
4. Drop: newsletters and no-reply senders, your own domain, suppliers you pay (accounting software, hosting, banks, the accountant), recruiters, and anything the person said to leave out.
5. Score each company:
   - invoice paid by them in the period: +5 (strongest)
   - each calendar meeting with them: +2 (max 10)
   - each email the owner sent: +1 (max 10)
   - last contact in the last 90 days: +2
6. Show the list, highest score first, with the evidence in one line: `Northwind (northwind.com): 14 sent, 3 meetings, invoice March, last contact 2 Sep`. Mark the ones the person already named.
7. The person ticks who is a client, who is a lead and who to leave out. Never add a company because of a score alone.

## The main person at a company
The person at that domain the owner emailed most. Take the name from the email header display name. Role only from a signature line or the calendar, and say where it came from in `evidence`.

## Same person twice?
The same email or the same LinkedIn URL is the same person. A name alone is not enough (two "Sam Lee" can be different people). If you are not sure, ask.

## Batches
Mailboxes are big. Read about 200 messages per batch and save the counts to `onboarding/state.json` after each batch, so a new session can continue.
