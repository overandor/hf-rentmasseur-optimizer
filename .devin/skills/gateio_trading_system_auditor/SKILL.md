---
name: gateio_trading_system_auditor
description: Audit Gate.io trading systems for safety, live-trading risk, persistence, walk-forward validation, execution logs, and monetizable artifacts.
---

# Gate.io Trading System Auditor

## Trigger
Use when a Gate.io bot, hedging strategy, ensemble, or market-data daemon appears in a chat export or repo file.

## Core job
Audit Gate.io trading systems for safety, live-trading risk, persistence, walk-forward validation, execution logs, and monetizable artifacts.

## Operating workflow
1. Identify the object being transformed: chat, code, repo, receipt, memo, machine state, or trading workflow.
2. Extract only reusable signal: decisions, artifacts, assumptions, metrics, risks, and next actions.
3. Separate measured facts from inference and speculation.
4. Convert the signal into a durable output: audit, memo, valuation input, risk screen, receipt design, or implementation plan.
5. State what the artifact newly enables and what it still does not prove.

## Discipline rules
- Do not confuse a story with evidence.
- Do not call simulation profit.
- Do not treat token display as financial value.
- Do not count recoverable state unless restore success and receipt verification are defined.
- Keep live-trading, lending, and collateral claims conservative unless independent evidence exists.

## Default output
A plain-English audit with: what it is, what it enables, novelty, evidence quality, risk, missing proof, and the next concrete build step.

## Local source pattern
Derived from the Membra Company OS ChatGPT export folder and its recurring pipeline: conversation to compression to artifact to receipt to valuation to underwriting.
