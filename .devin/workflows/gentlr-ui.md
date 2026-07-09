---
description: Build, install, and run gentlr with HF sync and research agenda
---

## gentlr — Build, Install, Research, HF Sync

### Prerequisites
- macOS arm64
- Homebrew (for libomp)
- Python 3.11+

### Install

```sh
curl -L -o gentlr.zip https://github.com/overandor/gentlr/releases/latest/download/gentlr-v0.1.0-macos-arm64.zip
unzip gentlr.zip
cd gentlr
chmod +x install.sh bootstrap.sh build-ui.sh
codesign --force --sign - GentlrWidget
codesign --force --sign - gentlr-ui
codesign --force --sign - gentlr-dry
codesign --force --sign - gentlr-apply-gentle
./install.sh
```

### Run UI

```sh
./gentlr-ui
```

### Dry Run ML Scan

```sh
./.venv/bin/python gentlr.py
```

### Apply (Real Kills)

```sh
./.venv/bin/python gentlr.py --apply --threshold 0.92 --max-kill 2
```

### Research Agenda

```sh
./.venv/bin/python gentlr.py --research
```

Writes `RESEARCH_AGENDA.md` and prints current research snapshot (model state, sample count, active questions).

### Hugging Face Sync

```sh
export HF_TOKEN="hf_your_token"
export HF_REPO="overandor/gentlr"
./.venv/bin/python gentlr.py --hf-sync
```

Pushes to HF:
- `gentlr-model.joblib` — trained ML pipeline
- `gentlr-events.ndjson` — event log
- `gentlr-policies.json` — per-app policies
- `research/snapshot.json` — research state snapshot

### Supervisor Mode

```sh
./.venv/bin/python gentlr.py --supervise --interval 30
```

### Train New Model

```sh
./.venv/bin/python gentlr.py --train
```
