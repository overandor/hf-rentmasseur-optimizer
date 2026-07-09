"""
Agent Bridge — Bidirectional 24/7 communication layer between ChatGPT Mac app and Windsurf Cascade.

Architecture:
    SharedQueue (SQLite) ← BridgeServer (FastAPI) ← {ChatGPTPoller, WindsurfClient}

Flow:
    Windsurf → POST /tasks → queue → ChatGPTPoller picks up → types into ChatGPT → captures response → POST /responses → queue → Windsurf reads
    ChatGPT → user types /windsurf <request> → ChatGPTPoller detects → POST /tasks → queue → Windsurf picks up → executes → POST /responses → queue → ChatGPTPoller reads back

Both directions survive restarts. SQLite is the durable backbone.
"""
