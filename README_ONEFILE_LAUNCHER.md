# ONEFILE ML Token Launcher

## What This Is
A single-file, runnable MVP that combines ML scoring, token-launch readiness,
proof receipts, API endpoints, and a local web UI.

## How to Run
```bash
python onefile_ml_token_launcher.py --demo          # Demo mode
python onefile_ml_token_launcher.py --serve          # API server on port 7860
python onefile_ml_token_launcher.py --serve --port 8080  # Custom port
python onefile_ml_token_launcher.py --score token.json   # Score a JSON file
```

## Endpoints
- GET /health
- GET /
- GET /openapi.json (FastAPI only)
- POST /v1/score
- POST /v1/launch/simulate
- POST /v1/token/spec
- POST /v1/ml/evaluate
- POST /v1/proof/receipt
- POST /v1/risk/check
- POST /v1/launch/packet
- GET /v1/receipts
- GET /api/help
- GET /v1/export/hf-files

## Safety Model
- Defaults to SIMULATION mode
- Blocks mainnet unless ALLOW_MAINNET=YES_I_UNDERSTAND_RISK env var is set
- Never requests private keys
- Never signs transactions
- Never promises profit
- All generated contracts/plans are specs, not execution
- Every output includes risk warnings and proof status

## Environment Variables
- ALLOW_MAINNET: Set to YES_I_UNDERSTAND_RISK to allow mainnet instruction generation (never signs)
- No private keys are ever requested or stored

## Hugging Face Spaces Deployment
1. Create a new Docker Space on Hugging Face
2. Copy onefile_ml_token_launcher.py into the Space
3. GET /v1/export/hf-files returns Dockerfile, requirements.txt, and README.md
4. Copy those files into the Space repo
5. The app will start on port 7860

### Disk Persistence on HF Spaces
Non-persistent disk is lost on restart. For persistent receipts:
- Attach a persistent storage volume
- Or use an external database (Supabase, PlanetScale, etc.)
- The tool uses SQLite by default, falling back to JSONL

## What Is Still Simulation-Only
- All token contract specs are text only, not deployed
- All Solana mint plans are JSON specs, not executed
- No chain transactions are performed
- No private keys are handled
- Mainnet is blocked by default

This is not legal, financial, or investment advice. This tool produces proof and launch-readiness artifacts, not investment guarantees.
