"""RECEPT Interpreter — executes RECEPT programs with receipt generation."""

import os
import json
import hashlib
import subprocess
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .parser import (
    parse, Node, CapsuleDecl, ObserveBlock, DecideBlock, ExecuteBlock,
    EndpointDecl, WorkflowDecl, StepDecl, FnDecl, IfStmt, ReturnStmt,
    AssignStmt, CallExpr, MethodCall, BinaryOp, StringLit, NumberLit,
    BoolLit, NoneLit, IdentRef, ReceiptStmt, DictLit,
)


class ReceptRuntimeError(Exception):
    pass


class ReceptSafetyError(Exception):
    """Raised when a destructive operation is attempted without @approved."""
    pass


class Interpreter:
    """Executes a RECEPT program.

    Every execute block auto-generates a receipt with SHA-256.
    Destructive operations require @approved annotation or raise ReceptSafetyError.
    """

    DESTRUCTIVE_FUNCS = {'rm', 'rmdir', 'kill', 'chmod', 'chown'}

    def __init__(self, receipts_dir: str = None):
        self.receipts_dir = receipts_dir or os.path.join(os.getcwd(), 'receipts')
        os.makedirs(self.receipts_dir, exist_ok=True)
        self.env: Dict[str, Any] = {}
        self.functions: Dict[str, FnDecl] = {}
        self.endpoints: Dict[str, EndpointDecl] = {}
        self.workflows: Dict[str, WorkflowDecl] = {}
        self.capsule_name: str = "unnamed"
        self.last_receipt_id: Optional[str] = None
        self.approved_context: bool = False
        self.output_log: List[str] = []

    def log(self, msg: str):
        self.output_log.append(f"[RECEPT] {msg}")
        print(f"[RECEPT] {msg}")

    def run(self, source: str) -> Dict:
        """Parse and execute a RECEPT program. Returns execution summary."""
        ast = parse(source)
        self.log(f"Parsed {len(ast)} declarations")

        results = {
            'capsule': None,
            'observations': [],
            'decisions': [],
            'executions': [],
            'endpoints': [],
            'workflows': [],
            'functions': [],
            'receipts': [],
            'errors': [],
        }

        for node in ast:
            try:
                if isinstance(node, CapsuleDecl):
                    self.capsule_name = node.name
                    results['capsule'] = node.name
                    self.log(f"Capsule: {node.name}")

                elif isinstance(node, ObserveBlock):
                    self.log("Observing...")
                    for stmt in node.statements:
                        result = self.exec_stmt(stmt)
                        if result is not None:
                            results['observations'].append(str(result))

                elif isinstance(node, DecideBlock):
                    self.log("Deciding...")
                    for stmt in node.statements:
                        result = self.exec_stmt(stmt)
                        if result is not None:
                            results['decisions'].append(str(result))

                elif isinstance(node, ExecuteBlock):
                    self.log("Executing...")
                    exec_results = []
                    for stmt in node.statements:
                        result = self.exec_stmt(stmt)
                        if result is not None:
                            exec_results.append(result)

                    # Auto-generate receipt for execute block
                    receipt = self.write_receipt('execute', {
                        'capsule': self.capsule_name,
                        'results': [str(r) for r in exec_results],
                    })
                    results['executions'].append({
                        'results': [str(r) for r in exec_results],
                        'receipt': receipt['receipt_id'],
                    })
                    results['receipts'].append(receipt)

                elif isinstance(node, EndpointDecl):
                    self.endpoints[f"{node.method} {node.path}"] = node
                    results['endpoints'].append({
                        'method': node.method,
                        'path': node.path,
                    })
                    self.log(f"Endpoint: {node.method} {node.path}")

                elif isinstance(node, WorkflowDecl):
                    self.workflows[node.name] = node
                    results['workflows'].append({
                        'name': node.name,
                        'steps': len(node.steps),
                    })
                    self.log(f"Workflow: {node.name} ({len(node.steps)} steps)")

                elif isinstance(node, FnDecl):
                    self.functions[node.name] = node
                    results['functions'].append({
                        'name': node.name,
                        'approved': node.approved,
                        'params': len(node.params),
                    })
                    self.log(f"Function: {node.name} (approved={node.approved})")

            except Exception as e:
                self.log(f"ERROR: {e}")
                results['errors'].append(str(e))

        return results

    def exec_stmt(self, stmt: Any) -> Any:
        """Execute a single statement."""
        if isinstance(stmt, AssignStmt):
            value = self.eval_expr(stmt.value)
            self.env[stmt.target] = value
            return value

        elif isinstance(stmt, CallExpr):
            return self.call_function(stmt.func, [self.eval_expr(a) for a in stmt.args])

        elif isinstance(stmt, MethodCall):
            obj = self.env.get(stmt.obj)
            if obj is None:
                raise ReceptRuntimeError(f"Undefined variable: {stmt.obj}")
            return self.call_method(obj, stmt.method, [self.eval_expr(a) for a in stmt.args])

        elif isinstance(stmt, IfStmt):
            cond = self.eval_expr(stmt.condition)
            if cond:
                for s in stmt.then_body:
                    self.exec_stmt(s)
            else:
                for s in stmt.else_body:
                    self.exec_stmt(s)
            return None

        elif isinstance(stmt, ReturnStmt):
            return self.eval_expr(stmt.value) if stmt.value else None

        elif isinstance(stmt, ReceiptStmt):
            text = self.eval_expr(stmt.text)
            receipt = self.write_receipt('manual', {'text': str(text)})
            return receipt

        elif isinstance(stmt, IdentRef):
            return self.env.get(stmt.name)

        else:
            raise ReceptRuntimeError(f"Unknown statement type: {type(stmt).__name__}")

    def eval_expr(self, expr: Any) -> Any:
        """Evaluate an expression to a Python value."""
        if isinstance(expr, StringLit):
            return expr.value
        elif isinstance(expr, NumberLit):
            return expr.value
        elif isinstance(expr, BoolLit):
            return expr.value
        elif isinstance(expr, NoneLit):
            return None
        elif isinstance(expr, IdentRef):
            return self.env.get(expr.name)
        elif isinstance(expr, BinaryOp):
            left = self.eval_expr(expr.left)
            right = self.eval_expr(expr.right)
            return self.eval_binary(expr.op, left, right)
        elif isinstance(expr, CallExpr):
            return self.call_function(expr.func, [self.eval_expr(a) for a in expr.args])
        elif isinstance(expr, MethodCall):
            obj = self.env.get(expr.obj)
            return self.call_method(obj, expr.method, [self.eval_expr(a) for a in expr.args])
        elif isinstance(expr, DictLit):
            return {k: self.eval_expr(v) for k, v in expr.pairs}
        else:
            raise ReceptRuntimeError(f"Unknown expression type: {type(expr).__name__}")

    def eval_binary(self, op: str, left: Any, right: Any) -> Any:
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right if right != 0 else None
        elif op == '==':
            return left == right
        elif op == '!=':
            return left != right
        elif op == '<':
            return left < right
        elif op == '>':
            return left > right
        elif op == '<=':
            return left <= right
        elif op == '>=':
            return left >= right
        elif op == 'and':
            return left and right
        elif op == 'or':
            return left or right
        else:
            raise ReceptRuntimeError(f"Unknown operator: {op}")

    def call_function(self, name: str, args: List[Any]) -> Any:
        """Call a built-in or user-defined function."""
        # Check user-defined functions
        if name in self.functions:
            fn = self.functions[name]
            if name in self.DESTRUCTIVE_FUNCS and not fn.approved:
                raise ReceptSafetyError(
                    f"Function '{name}' is destructive but not @approved. "
                    f"Add @approved annotation to allow execution."
                )

            # Bind params
            old_env = self.env.copy()
            for i, (pname, ptype) in enumerate(fn.params):
                self.env[pname] = args[i] if i < len(args) else None

            old_approved = self.approved_context
            self.approved_context = fn.approved

            result = None
            for stmt in fn.body:
                result = self.exec_stmt(stmt)
                if isinstance(stmt, ReturnStmt):
                    break

            self.env = old_env
            self.approved_context = old_approved
            return result

        # Built-in functions
        return self.call_builtin(name, args)

    def call_builtin(self, name: str, args: List[Any]) -> Any:
        """Built-in RECEPT functions."""
        if name == 'capture_screen':
            path = f"/tmp/recept_capture_{int(time.time())}.png"
            subprocess.run(['screencapture', '-x', path], capture_output=True, timeout=10)
            return path

        elif name == 'ocr':
            # Use macOS Vision if available, else return empty
            try:
                import Vision
                VNRecognizeTextRequest = Vision.VNRecognizeTextRequest
                # Simplified — real implementation in agent_controller
                return f"[OCR of {args[0]}]"
            except ImportError:
                return f"[OCR not available for {args[0]}]"

        elif name == 'type_into':
            text = args[0] if args else ""
            window = args[1] if len(args) > 1 else 0
            self.log(f"Typing into window {window}: {str(text)[:60]}")
            return f"typed: {str(text)[:60]}"

        elif name == 'fetch':
            import urllib.request
            url = args[0] if args else ""
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'RECEPT/1.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.read().decode('utf-8', errors='ignore')[:5000]
            except Exception as e:
                return f"fetch error: {e}"

        elif name == 'search':
            query = args[0] if args else ""
            self.log(f"Search: {query}")
            return f"[search results for: {query}]"

        elif name == 'read_file':
            path = args[0] if args else ""
            try:
                with open(path) as f:
                    return f.read()
            except Exception as e:
                return f"read error: {e}"

        elif name == 'write_file':
            path = args[0] if args else ""
            content = args[1] if len(args) > 1 else ""
            try:
                with open(path, 'w') as f:
                    f.write(content)
                return f"wrote {len(content)} bytes to {path}"
            except Exception as e:
                return f"write error: {e}"

        elif name == 'run':
            cmd = args[0] if args else ""
            if not self.approved_context:
                raise ReceptSafetyError(f"run() requires @approved annotation. Command: {cmd}")
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return r.stdout[:1000]
            except Exception as e:
                return f"run error: {e}"

        elif name == 'rm':
            path = args[0] if args else ""
            if not self.approved_context:
                raise ReceptSafetyError(f"rm() requires @approved annotation. Path: {path}")
            try:
                os.remove(path)
                return f"removed: {path}"
            except Exception as e:
                return f"rm error: {e}"

        elif name == 'rmdir':
            path = args[0] if args else ""
            if not self.approved_context:
                raise ReceptSafetyError(f"rmdir() requires @approved annotation. Path: {path}")
            try:
                os.rmdir(path)
                return f"removed dir: {path}"
            except Exception as e:
                return f"rmdir error: {e}"

        elif name == 'hash':
            data = args[0] if args else ""
            return hashlib.sha256(str(data).encode()).hexdigest()

        elif name == 'now':
            return datetime.now().isoformat()

        elif name == 'extract_issue':
            text = args[0] if args else ""
            # Simple extraction — look for error-like patterns
            lines = text.split('\n')
            for line in lines:
                if 'error' in line.lower() or 'bug' in line.lower() or 'fail' in line.lower():
                    return line.strip()
            return text[:100] if text else "unknown"

        elif name == 'generate_fix':
            bug = args[0] if args else ""
            return f"Fix: {bug}"

        elif name == 'len':
            return len(args[0]) if args else 0

        elif name == 'str':
            return str(args[0]) if args else ""

        elif name == 'int':
            return int(args[0]) if args else 0

        else:
            raise ReceptRuntimeError(f"Unknown function: {name}")

    def call_method(self, obj: Any, method: str, args: List[Any]) -> Any:
        """Call a method on an object."""
        if method == 'contains':
            return str(args[0]) in str(obj) if obj else False
        elif method == 'upper':
            return str(obj).upper() if obj else ""
        elif method == 'lower':
            return str(obj).lower() if obj else ""
        elif method == 'strip':
            return str(obj).strip() if obj else ""
        elif method == 'split':
            return str(obj).split(args[0] if args else ' ') if obj else []
        elif method == 'replace':
            return str(obj).replace(args[0], args[1]) if obj and len(args) >= 2 else obj
        else:
            raise ReceptRuntimeError(f"Unknown method: .{method}()")

    def write_receipt(self, action: str, details: Dict) -> Dict:
        """Write a receipt for this execution."""
        receipt_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        content = json.dumps(details, sort_keys=True)
        artifact_hash = hashlib.sha256(content.encode()).hexdigest()

        receipt = {
            'receipt_id': receipt_id,
            'timestamp': timestamp,
            'capsule': self.capsule_name,
            'action': action,
            'artifact_hash': artifact_hash,
            'details': details,
            'previous_receipt': self.last_receipt_id,
        }

        filename = f"{timestamp.replace(':', '-').replace('.', '_')}_{self.capsule_name}_{action}.json"
        filepath = os.path.join(self.receipts_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(receipt, f, indent=2)

        self.last_receipt_id = receipt_id
        self.log(f"Receipt: {filename} hash={artifact_hash[:16]}...")
        return receipt


def run_file(filepath: str, receipts_dir: str = None) -> Dict:
    """Run a .recept file."""
    with open(filepath) as f:
        source = f.read()
    interp = Interpreter(receipts_dir=receipts_dir)
    return interp.run(source)


def run_source(source: str, receipts_dir: str = None) -> Dict:
    """Run RECEPT source code directly."""
    interp = Interpreter(receipts_dir=receipts_dir)
    return interp.run(source)
