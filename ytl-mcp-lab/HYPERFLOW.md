# YTL-MCP Research Lab — HYPERFLOW

## Purpose

This repository is a YouTube Automation Research Lab. Its purpose is to perform compliant content research, production assistance, analytics measurement, and experiment tracking.

## Hard Constraints

It MUST NOT:
- Generate fake engagement
- Impersonate users
- Bypass platform protections
- Mass-comment, mass-like, mass-subscribe
- Scrape private data
- Reupload copyrighted material
- Perform deceptive automation

## Rules

1. All upload-affecting actions require explicit authorization.
2. Every generated artifact must be traceable to source inputs, prompt/config hashes, and receipt logs.
3. Every experiment must define its hypothesis, variable, metric, baseline, and measurement window before publication.
4. Every factual claim in a script must be marked: verified, inferred, speculative, or blocked.
5. Every generated video packet must include transcript, script, metadata, risk report, source notes, and receipt hashes.
6. Credentials must stay in .env, never in code.
7. Upload defaults to private or unlisted.
8. Receipts are append-only and immutable.

## Agent Roles

### ChatGPT (Command Brain)
May call MCP tools, inspect receipts, generate specs, create scripts, evaluate experiments, route work to Windsurf.
Must NOT request prohibited platform manipulation, copyright theft, credential extraction, or evasion.

### Windsurf (Operator Bay)
May edit code, run local commands, inspect logs, start MCP server.
Must follow HYPERFLOW.md, keep changes small, run `make verify`, write receipts.

### MCP Server (Tool Interface)
Expose only bounded, auditable tools. Validate all inputs. Require confirmation for upload-affecting operations. Write receipts before and after every external API call. Never expose raw secrets. Never execute arbitrary shell commands from model input.

## Verification

```bash
make verify
```

This runs tests, lint, and receipt validation. No task is complete without verification.
