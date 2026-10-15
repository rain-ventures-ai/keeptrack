# Setup

Local: use a board clone with readable board/tasks.json. No external connection required.

Claude, ChatGPT and Grok: connect read-only access to board.read. Confirm: “I can read board.read for this automation without writing source data.” Run setup --runtime <runtime>, then setup --confirm board.read. Setup never enables an automation.
