# Workflow: create-receipt

> **Generate a signed receipt for the last artifact or action.**

## Prerequisites

- An action was performed (build, verify, inspect, search, review, etc.)
- At least one artifact was produced (or failure was recorded)

## Steps

1. **Gather action context**
   - Agent name
   - Action type
   - Timestamp (ISO 8601)
   - Commands run (list of strings)
   - Result status: success | failure | partial

2. **Identify artifact**
   - Primary artifact path (absolute)
   - If artifact exists: compute SHA-256 hash
     - `shasum -a 256 <artifact_path>` → parse hash
   - If no artifact: set path and hash to null, result must be "failure"

3. **Build receipt JSON**
   ```json
   {
     "receipt_id": "<uuid4>",
     "timestamp": "<ISO 8601>",
     "agent": "<agent_name>",
     "action": "<action_type>",
     "artifact_path": "<absolute_path_or_null>",
     "artifact_hash": "<sha256_or_null>",
     "commands_run": ["<cmd1>", "<cmd2>"],
     "result": "<success|failure|partial>",
     "details": {},
     "previous_receipt": "<receipt_id_or_null>"
   }
   ```

4. **Link to previous receipt**
   - If this action is a continuation of a prior action, set `previous_receipt` to the prior receipt's ID
   - Otherwise set to null

5. **Write receipt**
   - Filename: `receipts/{timestamp}_{agent}_{action}.json`
   - Write JSON with `json.dump(indent=2)`
   - Verify file exists after write

6. **Log**
   - `logger.info(f"[Receipt] Written: {filepath} hash={hash[:16]}...")`

## Validation

- After writing, re-read the file and verify `artifact_hash` matches actual file hash
- If mismatch → log `RECEIPT_INVALID` but do not delete (audit trail)

## Sacred Rule

> No receipt = artifact doesn't exist.
