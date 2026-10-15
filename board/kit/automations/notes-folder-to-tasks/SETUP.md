# Setup

Local: pass --set notes_dir=/path/to/notes at install; ensure this folder exists and is readable.

Claude, ChatGPT and Grok: connect read-only access to files.read. Confirm: “I can read files.read for this automation without writing source data.” Run setup --runtime <runtime>, then setup --confirm files.read. Setup never enables an automation.
