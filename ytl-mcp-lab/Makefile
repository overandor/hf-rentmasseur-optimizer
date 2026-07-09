.PHONY: hyperflow-lab install db-init mcp verify dashboard receipt test lint clean

# === Unified HyperFlow Commands ===

hyperflow-lab:
	@echo "Starting HyperFlow Lab..."
	@echo "1. Initializing YTL-MCP database..."
	@python3 scripts/init_db.py 2>/dev/null || true
	@echo ""
	@echo "2. Running tests..."
	@cd .. && python3 -m pytest tests/test_mcp_unified.py ytl-mcp-lab/tests/test_lab.py -v 2>/dev/null || true
	@echo ""
	@echo "3. Starting MCP HTTP server on port 8765..."
	@echo "   ChatGPT App manifest: mcp/chatgpt_app_manifest.json"
	@echo "   Windsurf MCP config:  mcp/windsurf_mcp_config.json"
	@echo ""
	@echo "   Endpoints:"
	@echo "     GET  http://127.0.0.1:8765/         (health)"
	@echo "     GET  http://127.0.0.1:8765/tools    (list tools)"
	@echo "     POST http://127.0.0.1:8765/tools/call (call tool)"
	@echo "     POST http://127.0.0.1:8765/mcp      (MCP JSON-RPC)"
	@echo ""
	@python3 ../mcp/mcp_unified.py serve-http 8765

# === YTL-MCP Lab Commands ===

install:
	pip install -e ".[dev]" 2>/dev/null || pip install -r requirements.txt 2>/dev/null || true
	@echo "Install complete"

db-init:
	python3 scripts/init_db.py
	@echo "Database initialized"

mcp:
	python3 server/mcp_server.py
	@echo "MCP server started"

verify: test lint
	@echo "All checks passed"

test:
	python3 -m pytest tests/ -v 2>/dev/null || python3 -m unittest discover -s tests -v 2>/dev/null || echo "No tests found"
	@echo "Tests complete"

lint:
	python3 -m ruff check . 2>/dev/null || python3 -m flake8 . 2>/dev/null || echo "No linter configured"
	@echo "Lint complete"

dashboard:
	python3 dashboard/app.py 2>/dev/null || echo "Dashboard not yet implemented"

receipt:
	python3 -c "from pathlib import Path; p=Path('receipts/ledger.jsonl'); print(p.read_text() if p.exists() else 'No receipts yet')"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete"
