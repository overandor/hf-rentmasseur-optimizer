"""RECEPT Transpiler — compiles .recept to Python source + FastAPI app."""

import os
import json
from typing import List, Any

from .parser import (
    parse, Node, CapsuleDecl, ObserveBlock, DecideBlock, ExecuteBlock,
    EndpointDecl, WorkflowDecl, StepDecl, FnDecl, IfStmt, ReturnStmt,
    AssignStmt, CallExpr, MethodCall, BinaryOp, StringLit, NumberLit,
    BoolLit, NoneLit, IdentRef, ReceiptStmt, DictLit,
)


class Transpiler:
    """Compiles RECEPT AST into Python source files.

    - Capsule → directory with manifest.json
    - Endpoints → FastAPI app.py
    - Functions → Python functions
    - Workflows → Python functions with step receipts
    """

    def __init__(self, output_dir: str = "capsules"):
        self.output_dir = output_dir

    def transpile(self, source: str, capsule_name: str = None) -> str:
        """Transpile RECEPT source to a capsule directory with Python files.
        Returns the capsule directory path."""
        ast = parse(source)

        # Extract capsule name
        for node in ast:
            if isinstance(node, CapsuleDecl):
                capsule_name = capsule_name or node.name
                break

        if not capsule_name:
            capsule_name = "unnamed_capsule"

        # Create capsule directory
        capsule_dir = os.path.join(self.output_dir, capsule_name)
        os.makedirs(capsule_dir, exist_ok=True)

        # Generate Python code
        has_endpoints = any(isinstance(n, EndpointDecl) for n in ast)
        code_lines = self._generate_module(ast, has_endpoints)

        # Write main module
        main_path = os.path.join(capsule_dir, "app.py")
        with open(main_path, 'w') as f:
            f.write('\n'.join(code_lines))

        # Write manifest
        manifest = {
            'capsule_name': capsule_name,
            'source_language': 'RECEPT',
            'transpiled_to': 'Python',
            'has_endpoints': has_endpoints,
            'files': [os.path.basename(main_path)],
        }
        manifest_path = os.path.join(capsule_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        return capsule_dir

    def _generate_module(self, ast: List[Node], has_endpoints: bool) -> List[str]:
        """Generate Python source lines from AST."""
        lines = [
            '"""Auto-generated from RECEPT source. Do not edit manually."""',
            '',
            'import os',
            'import json',
            'import hashlib',
            'import subprocess',
            'import time',
            'import uuid',
            'from datetime import datetime',
            '',
        ]

        if has_endpoints:
            lines += [
                'from fastapi import FastAPI',
                '',
                'app = FastAPI(title="RECEPT Capsule")',
                '',
            ]

        # Add receipt helper
        lines += [
            'RECEIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "receipts")',
            'os.makedirs(RECEIPTS_DIR, exist_ok=True)',
            '_last_receipt = None',
            '',
            'def _receipt(action, details):',
            '    global _last_receipt',
            '    rid = str(uuid.uuid4())',
            '    ts = datetime.now().isoformat()',
            '    content = json.dumps(details, sort_keys=True)',
            '    h = hashlib.sha256(content.encode()).hexdigest()',
            '    r = {"receipt_id": rid, "timestamp": ts, "action": action,',
            '         "artifact_hash": h, "details": details, "previous_receipt": _last_receipt}',
            '    fn = f"{ts.replace(\":\", \"-\").replace(\".\", \"_\")}_{action}.json"',
            '    with open(os.path.join(RECEIPTS_DIR, fn), "w") as f:',
            '        json.dump(r, f, indent=2)',
            '    _last_receipt = rid',
            '    return r',
            '',
        ]

        # Add built-in functions
        lines += self._generate_builtins()

        # Process declarations
        for node in ast:
            if isinstance(node, CapsuleDecl):
                continue  # Already handled
            elif isinstance(node, ObserveBlock):
                lines.append('# --- observe ---')
                for stmt in node.statements:
                    lines.append(self._gen_stmt(stmt, indent=0))
                lines.append('')
            elif isinstance(node, DecideBlock):
                lines.append('# --- decide ---')
                for stmt in node.statements:
                    lines.append(self._gen_stmt(stmt, indent=0))
                lines.append('')
            elif isinstance(node, ExecuteBlock):
                lines.append('# --- execute ---')
                lines.append('def execute():')
                for stmt in node.statements:
                    lines.append(self._gen_stmt(stmt, indent=4))
                lines.append('    _receipt("execute", {"capsule": "' + self._capsule_name(ast) + '"})')
                lines.append('    return "ok"')
                lines.append('')
            elif isinstance(node, EndpointDecl):
                lines.append(self._gen_endpoint(node))
                lines.append('')
            elif isinstance(node, WorkflowDecl):
                lines.append(self._gen_workflow(node))
                lines.append('')
            elif isinstance(node, FnDecl):
                lines.append(self._gen_fn(node))
                lines.append('')

        # Add main block
        lines.append('if __name__ == "__main__":')
        lines.append('    # Run observe → decide → execute')
        lines.append('    print("RECEPT capsule running...")')
        lines.append('    try:')
        lines.append('        execute()')
        lines.append('    except NameError:')
        lines.append('        pass  # No execute block')
        lines.append('    print("Done.")')

        return lines

    def _capsule_name(self, ast: List[Node]) -> str:
        for node in ast:
            if isinstance(node, CapsuleDecl):
                return node.name
        return "unnamed"

    def _generate_builtins(self) -> List[str]:
        return [
            'def capture_screen():',
            '    path = f"/tmp/recept_{int(time.time())}.png"',
            '    subprocess.run(["screencapture", "-x", path], capture_output=True, timeout=10)',
            '    return path',
            '',
            'def ocr(image_path):',
            '    return f"[OCR of {image_path}]"',
            '',
            'def type_into(text, window=0):',
            '    print(f"[type_into] window={window}: {text[:60]}")',
            '    return text',
            '',
            'def fetch(url):',
            '    import urllib.request',
            '    try:',
            '        req = urllib.request.Request(url, headers={"User-Agent": "RECEPT/1.0"})',
            '        with urllib.request.urlopen(req, timeout=10) as resp:',
            '            return resp.read().decode("utf-8", errors="ignore")[:5000]',
            '    except Exception as e:',
            '        return f"error: {e}"',
            '',
            'def search(query):',
            '    print(f"[search] {query}")',
            '    return f"[results for: {query}]"',
            '',
            'def read_file(path):',
            '    with open(path) as f: return f.read()',
            '',
            'def write_file(path, content):',
            '    with open(path, "w") as f: f.write(content)',
            '    return f"wrote {len(content)} bytes"',
            '',
            'def _hash(data):',
            '    return hashlib.sha256(str(data).encode()).hexdigest()',
            '',
            'def _now():',
            '    return datetime.now().isoformat()',
            '',
        ]

    def _gen_stmt(self, stmt: Any, indent: int = 0) -> str:
        pad = '    ' * (indent // 4)
        if isinstance(stmt, AssignStmt):
            return f"{pad}{stmt.target} = {self._gen_expr(stmt.value)}"
        elif isinstance(stmt, CallExpr):
            return f"{pad}{self._gen_expr(stmt)}"
        elif isinstance(stmt, MethodCall):
            return f"{pad}{self._gen_expr(stmt)}"
        elif isinstance(stmt, IfStmt):
            lines = [f"{pad}if {self._gen_expr(stmt.condition)}:"]
            if stmt.then_body:
                for s in stmt.then_body:
                    lines.append(self._gen_stmt(s, indent + 4))
            else:
                lines.append(f"{pad}    pass")
            if stmt.else_body:
                lines.append(f"{pad}else:")
                for s in stmt.else_body:
                    lines.append(self._gen_stmt(s, indent + 4))
            return '\n'.join(lines)
        elif isinstance(stmt, ReturnStmt):
            return f"{pad}return {self._gen_expr(stmt.value)}" if stmt.value else f"{pad}return None"
        elif isinstance(stmt, ReceiptStmt):
            return f'{pad}_receipt("manual", {{"text": {self._gen_expr(stmt.text)}}})'
        elif isinstance(stmt, IdentRef):
            return f"{pad}{stmt.name}"
        else:
            return f"{pad}# unhandled: {type(stmt).__name__}"

    def _gen_expr(self, expr: Any) -> str:
        if isinstance(expr, StringLit):
            return f'"{expr.value}"'
        elif isinstance(expr, NumberLit):
            return str(expr.value)
        elif isinstance(expr, BoolLit):
            return str(expr.value)
        elif isinstance(expr, NoneLit):
            return 'None'
        elif isinstance(expr, IdentRef):
            return expr.name
        elif isinstance(expr, BinaryOp):
            return f"({self._gen_expr(expr.left)} {expr.op} {self._gen_expr(expr.right)})"
        elif isinstance(expr, CallExpr):
            args = ', '.join(self._gen_expr(a) for a in expr.args)
            return f"{expr.func}({args})"
        elif isinstance(expr, MethodCall):
            args = ', '.join(self._gen_expr(a) for a in expr.args)
            return f"{expr.obj}.{expr.method}({args})"
        elif isinstance(expr, DictLit):
            pairs = ', '.join(f'"{k}": {self._gen_expr(v)}' for k, v in expr.pairs)
            return f'{{{pairs}}}'
        else:
            return f"None  # unhandled expr: {type(expr).__name__}"

    def _gen_endpoint(self, node: EndpointDecl) -> str:
        lines = [f'@app.{node.method.lower()}("{node.path}")']
        lines.append(f'def {node.method.lower()}_endpoint():')
        if node.statements:
            for stmt in node.statements:
                lines.append(self._gen_stmt(stmt, indent=4))
        else:
            lines.append('    pass')
        if not any(isinstance(s, ReturnStmt) for s in node.statements):
            lines.append('    return {"status": "ok"}')
        return '\n'.join(lines)

    def _gen_workflow(self, node: WorkflowDecl) -> str:
        lines = [f'def workflow_{node.name}():']
        lines.append(f'    """Workflow: {node.name} — {len(node.steps)} steps."""')
        for step in node.steps:
            lines.append(f'    # Step {step.number}: {step.action}')
            lines.append(f'    _receipt("workflow_step", {{"workflow": "{node.name}", "step": {step.number}, "action": "{step.action}"}})')
        lines.append(f'    _receipt("workflow_complete", {{"workflow": "{node.name}"}})')
        lines.append('    return "done"')
        return '\n'.join(lines)

    def _gen_fn(self, node: FnDecl) -> str:
        params = ', '.join(p[0] for p in node.params)
        lines = [f'def {node.name}({params}):']
        if node.body:
            for stmt in node.body:
                lines.append(self._gen_stmt(stmt, indent=4))
        else:
            lines.append('    pass')
        if not any(isinstance(s, ReturnStmt) for s in node.body):
            lines.append('    return None')
        return '\n'.join(lines)


def transpile_file(filepath: str, output_dir: str = "capsules") -> str:
    """Transpile a .recept file to a Python capsule directory."""
    with open(filepath) as f:
        source = f.read()
    return Transpiler(output_dir).transpile(source)


def transpile_source(source: str, output_dir: str = "capsules") -> str:
    """Transpile RECEPT source code to a Python capsule directory."""
    return Transpiler(output_dir).transpile(source)
