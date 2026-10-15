# Setup

Local: install gog on PATH, run gog auth login for the intended account, then verify `gog auth list --json` read-only. Install requires --allow-network; this grants the check access to your existing HOME login. If setup is blocked, fix the login and rerun setup.

Claude, ChatGPT and Grok: connect read-only access to gmail.read. Confirm: “I can read gmail.read for this automation without writing source data.” Run setup --runtime <runtime>, then setup --confirm gmail.read. Setup never enables an automation.
