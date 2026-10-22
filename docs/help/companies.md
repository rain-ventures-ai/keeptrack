# Companies

**Companies** lists every client on your board and every company your people work at, once each. A company appears as soon as a person's **Client** or a task's client names it; you never have to create it first.

A client with no people, no company record (no stage, owner, domain, notes or north star), no files and no projects, such as a "General" bucket for tasks, is left out of Companies and the company pipeline. It is still a client: tasks keep it and the client pills show it. Give it any of those, or add a person, and it appears.

Each row shows:

- the company's **stage**;
- how many **people** you know there and how many **open tasks** it has;
- the **next step**: the earliest next step among its people, with its date and whose it is;
- the **last contact** with any of its people.

Rows are sorted by stage, then by the most recent contact. The **Sort** menu also sorts by **recently contacted**, **recently updated** (the newest change to any of its people, tasks or projects; the row then shows when) or **name**. The contact menu shows only companies **contacted in the last 30 days**, with **no contact for 30+ days**, or **never contacted**. Your sort and contact filter are remembered on this device. Search finds a company by its name, domain or notes, or by the name or role of anyone who works there. The stage list and the client pills filter it, as they do People.

## Links to a company, person or project

Each company, person and project has its own address. When you open one, the address bar changes to it (for example `…#company=Acme`, `…#person=p_x1y2`, `…#project=pr_a1b2`), so you can bookmark it, and Back closes it. **Copy link** in the record's ⋯ menu copies it to share. Opening the link opens the board and then the record. Only people who can open the board can open the record. A company's link contains the company's name, so anyone who sees the link can read it: share it only where the name may be seen.

## The company record

Click a company (or a company name anywhere on the board: in a person row, on a pipeline card, or the arrow next to **Client** in a person's card) to open its record:

- **Stage**, **Owner** (a board member), **Domain** and **Value**. Value is the sum of its people's values; you cannot type it.
- **Notes** about the company.
- **People**: everyone at the company, with their role, stage and last contact. Click one to open them.
- **Activity**: the contact log of all its people in one list, newest first, each entry labelled with the person. The first ten show; **Show more** shows older ones. An entry with a source link shows **Open in Gmail** (or **Open original**), which opens the original email thread in a new tab.
- **Open tasks**: the tasks whose client is this company.
- The **north star**, **projects** and **files and folders**, as before.

## The company's stage

Until you set a stage on the company, it shows the most advanced stage among its people, in the order of your stages (a person who is **Lost** never outranks one who is still live). The stage then looks outlined, and the record says "(from its people)".

Set the stage in the record, or drag the company in the pipeline. To go back to the stage worked out from its people, choose **Use people's stage** in the record's ⋯ menu, or the first option of the Stage list.

The company's own stage does not change its people's stages.

## Board member companies

A company that a board member says is their own (Settings → Board → Members) is marked **Your company** or **Board member company**. It is listed first and stays out of the pipeline, as members' own person records do.

## From the terminal

```
python3 board/keeptrack.py clients
python3 board/keeptrack.py client-set "Acme" --stage Proposal --owner alex --domain acme.com --notes "Key account"
python3 board/keeptrack.py client-set "Acme" --stage ""      # use its people's stage again
```

An empty value (`""`) clears a field. The stage must be one of your stages and the owner a board member.
