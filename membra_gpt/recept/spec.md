# RECEPT Language Specification

## What Is RECEPT?

RECEPT (Receipt-Embedded Concurrent Execution Programming Technology) is a programming language designed from scratch for LLM agents. Every operation produces a receipt. OS-level primitives (capture, type, endpoint, workflow) are first-class. Terminal safety is enforced at compile time, not runtime.

## Design Principles

1. **Line-oriented** — LLMs generate best line by line. No nested brackets.
2. **Receipt-native** — Every `execute` block auto-generates a receipt with SHA-256.
3. **Safe by construction** — Destructive ops require `@approved` annotation or compile fails.
4. **Capsule is the unit** — Every file compiles to a capsule (artifact + manifest + receipt).
5. **Endpoints are first-class** — `endpoint` keyword declares HTTP routes inline.
6. **Workflows are first-class** — `workflow` keyword declares multi-step procedures.
7. **No pointers, no manual memory** — Safe by construction.
8. **Observe → Decide → Execute** — The agent loop is the language structure.

## Syntax

### Capsule Declaration
```
capsule <name>
```
Every `.recept` file starts with a capsule declaration. This becomes the capsule directory name.

### Observe Block
```
observe:
    <statements>
```
Read-only operations. Screen capture, OCR, file reads, web fetches. No mutations. No receipts.

### Decide Block
```
decide:
    <statements>
```
Conditionals and variable assignment. No side effects. Pure logic.

### Execute Block
```
execute:
    <statements>
```
Side-effect operations. Every execute block generates a receipt automatically.
This is where typing, file writes, subprocess calls happen.

### Endpoint Declaration
```
endpoint <METHOD> <path>:
    <statements>
    return <value>
```
Declares an HTTP endpoint. Compiled to a FastAPI route.

### Workflow Declaration
```
workflow <name>:
    step <n>: <action>
    step <n>: <action>
```
Multi-step procedure. Each step generates a receipt. Steps chain via `previous_receipt`.

### Function Declaration
```
fn <name>(<params>) -> <type>:
    <statements>
    return <value>
```

### Safety Annotations
```
@approved
fn destructive_op():
    rm("/tmp/old")
```
Without `@approved`, destructive operations fail at compile time.

### Types

| Type | Description |
|------|-------------|
| `text` | String |
| `int` | Integer |
| `bool` | Boolean |
| `artifact` | File path with hash |
| `receipt` | Receipt object |
| `endpoint` | HTTP endpoint handle |
| `none` | Null/void |

### Built-in Functions

| Function | Description | Safe? |
|----------|-------------|-------|
| `capture_screen()` | Screenshot | Yes |
| `ocr(image)` | Text extraction | Yes |
| `type_into(text, window)` | Type into window | Yes |
| `fetch(url)` | HTTP GET | Yes |
| `search(query)` | Web search | Yes |
| `read_file(path)` | File read | Yes |
| `write_file(path, content)` | File write | Yes |
| `run(cmd)` | Subprocess | @approved |
| `rm(path)` | Delete file | @approved |
| `rmdir(path)` | Delete dir | @approved |
| `receipt(text)` | Manual receipt | Yes |
| `hash(data)` | SHA-256 | Yes |
| `now()` | Timestamp | Yes |

### Example Program

```
capsule bug_reviewer

observe:
    screenshot = capture_screen()
    code_text = ocr(screenshot)

decide:
    if code_text.contains("error") or code_text.contains("bug"):
        bug = extract_issue(code_text)
        should_fix = true
    else:
        should_fix = false

execute:
    if should_fix:
        fix = "Fix: " + bug
        type_into(fix, window=2)
        receipt "reviewed and fixed: " + bug
    else:
        receipt "no issues found"

endpoint GET /status:
    return { capsule: "bug_reviewer", active: true }

workflow daily_review:
    step 1: observe screen
    step 2: decide if bug exists
    step 3: execute fix if needed
    step 4: receipt summary
```

## Compilation

RECEPT compiles to:
1. A capsule directory with `manifest.json`
2. Python source files (transpiled)
3. A FastAPI app if endpoints are declared
4. A receipt for the compilation itself

## File Extension

`.recept`
