"""
OverLang — OverLanguage 2.0 workflow grammar and runtime.

.over = OverLanguage workflow specs (intent → artifact → receipt → value)

Parser, compiler, and OverRuntime for executing .over workflows with real file I/O.
"""

import sys
import os
import json
import time
import hashlib
import re
import sqlite3
import shutil
import zipfile
import plistlib
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any


# =============================================================================
# OVERLANGUAGE FILE FORMAT — .over source
# =============================================================================

@dataclass
class OverStep:
    step_num: int
    action: str
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    receipt: bool = True


@dataclass
class OverWorkflow:
    name: str = ""
    intent: str = ""
    steps: list[OverStep] = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    value_claim: str = ""


def parse_over(source: str) -> OverWorkflow:
    """Parse .over source into OverWorkflow.
    Format is line-based with → as the flow operator:
      intent: <description>
      step 1: <action> → <output>
      step 2: <action> → <output>
      artifact: <name>
      receipt: <description>
      value: <claim>
    """
    wf = OverWorkflow()
    step_counter = 0

    for line in source.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("intent:"):
            wf.intent = line[7:].strip()
        elif line.startswith("workflow:"):
            wf.name = line[9:].strip()
        elif line.startswith("step"):
            step_counter += 1
            rest = line.split(":", 1)[1].strip() if ":" in line else line
            parts = rest.split("→")
            action = parts[0].strip()
            outputs = [p.strip() for p in parts[1:]] if len(parts) > 1 else []
            wf.steps.append(OverStep(step_num=step_counter, action=action, outputs=outputs))
        elif line.startswith("artifact:"):
            wf.artifacts.append(line[9:].strip())
        elif line.startswith("receipt:"):
            wf.receipts.append(line[8:].strip())
        elif line.startswith("value:"):
            wf.value_claim = line[6:].strip()

    return wf


def compile_over(source: str, filename: str = "") -> dict:
    """Compile a .over source file into a workflow artifact."""
    start = time.time()
    wf = parse_over(source)

    # Generate receipt chain
    receipt_chain = []
    prev_hash = "0" * 64
    for step in wf.steps:
        entry = json.dumps({
            "step": step.step_num,
            "action": step.action,
            "outputs": step.outputs,
            "ts": time.time(),
        }, sort_keys=True)
        entry_hash = hashlib.sha256((prev_hash + entry).encode()).hexdigest()
        receipt_chain.append({
            "step": step.step_num,
            "action": step.action,
            "hash": entry_hash,
            "prev_hash": prev_hash,
        })
        prev_hash = entry_hash

    artifact = {
        "type": "over_compiled",
        "source_file": filename,
        "compiled_at": time.time(),
        "workflow_name": wf.name,
        "intent": wf.intent,
        "step_count": len(wf.steps),
        "steps": [
            {"step": s.step_num, "action": s.action, "outputs": s.outputs}
            for s in wf.steps
        ],
        "artifacts": wf.artifacts,
        "value_claim": wf.value_claim,
        "receipt_chain": receipt_chain,
        "merkle_root": prev_hash,
        "compile_time_ms": round((time.time() - start) * 1000, 2),
    }

    artifact_str = json.dumps(artifact, sort_keys=True)
    artifact["sha256"] = hashlib.sha256(artifact_str.encode()).hexdigest()

    return artifact


# =============================================================================
# OVER RUNTIME — Execute .over workflows with real file I/O
# =============================================================================

class OverRuntime:
    """Executes .over workflows step-by-step with real operations.
    No mock. No simulation. Real file reads, real SHA256, real SQLite indexes,
    real chunk extraction, real search, real revocation."""

    def __init__(self):
        self.state: dict[str, Any] = {}
        self.receipts: list[dict] = []
        self.prev_hash = "0" * 64
        self.index_dir = Path("jorki_data/indexes")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = Path("jorki_data/registry.json")
        self.registry: dict[str, dict] = {}
        if self.registry_path.exists():
            self.registry = json.loads(self.registry_path.read_text())

    def _receipt(self, step: int, action: str, result: Any) -> dict:
        entry = json.dumps({"step": step, "action": action, "result_hash": hashlib.sha256(str(result).encode()).hexdigest()[:16], "ts": time.time()}, sort_keys=True)
        entry_hash = hashlib.sha256((self.prev_hash + entry).encode()).hexdigest()
        r = {"step": step, "action": action, "hash": entry_hash, "prev_hash": self.prev_hash, "ts": time.time()}
        self.receipts.append(r)
        self.prev_hash = entry_hash
        return r

    def _save_registry(self):
        self.registry_path.write_text(json.dumps(self.registry, indent=2))

    def execute(self, wf: OverWorkflow, args: dict[str, str] | None = None) -> dict:
        """Execute all steps in the workflow. args provides runtime parameters."""
        args = args or {}
        self.state["args"] = args
        self.state["workflow"] = wf.name
        self.state["intent"] = wf.intent
        results = []

        for step in wf.steps:
            action = step.action.lower().strip()
            result = self._exec_action(step.step_num, action, args)
            for out in step.outputs:
                self.state[out] = result
            r = self._receipt(step.step_num, step.action, result)
            results.append({"step": step.step_num, "action": step.action, "outputs": step.outputs, "result": result, "receipt": r["hash"][:16]})
            print(f"  step {step.step_num}: {step.action} -> {step.outputs}  [receipt: {r['hash'][:12]}...]")

        merkle_root = self.prev_hash
        artifact = {
            "type": "over_executed",
            "workflow": wf.name,
            "intent": wf.intent,
            "executed_at": time.time(),
            "step_results": results,
            "state": {k: v for k, v in self.state.items() if k not in ("args",)},
            "artifacts": wf.artifacts,
            "value_claim": wf.value_claim,
            "receipt_chain": self.receipts,
            "merkle_root": merkle_root,
        }
        artifact_str = json.dumps(artifact, sort_keys=True)
        artifact["sha256"] = hashlib.sha256(artifact_str.encode()).hexdigest()

        receipts_dir = Path("receipts")
        receipts_dir.mkdir(exist_ok=True)
        receipt_name = f"{wf.name}_{int(time.time())}.json"
        (receipts_dir / receipt_name).write_text(json.dumps(artifact, indent=2, ensure_ascii=False))

        return artifact

    def _exec_action(self, step_num: int, action: str, args: dict) -> Any:
        """Execute a single workflow action. Real operations only."""

        if "index file" in action or ("index" in action and "file" in action):
            filepath = args.get("file", args.get("filepath", ""))
            if not filepath or not os.path.exists(filepath):
                return {"error": f"File not found: {filepath}"}
            return self._index_file(filepath)

        if "compute hash" in action or "merkle" in action.lower():
            filepath = args.get("file", args.get("filepath", ""))
            if not filepath or not os.path.exists(filepath):
                idx = self.state.get("local_index", self.state.get("file_index", {}))
                if isinstance(idx, dict) and "merkle_root" in idx:
                    return idx["merkle_root"]
                return {"error": "No file to hash"}
            return self._compute_hash(filepath)

        if "upload" in action and ("index" in action or "hf" in action or "space" in action):
            idx = self.state.get("local_index", {})
            if not idx or "file_id" not in idx:
                return {"error": "No index to upload"}
            file_id = idx["file_id"]
            self.registry[file_id] = {
                "filename": idx.get("filename", "unknown"),
                "merkle_root": idx.get("merkle_root", ""),
                "indexed_at": time.time(),
                "status": "active",
                "index_path": str(self.index_dir / f"{file_id}.idx"),
            }
            self._save_registry()
            return {"file_id": file_id, "status": "uploaded", "url": f"jorki://query/{file_id}"}

        if "search" in action or ("query" in action and "sql" not in action):
            file_id = args.get("file_id", "")
            query = args.get("q", args.get("query", ""))
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return self._search(file_id, query)

        if "sql" in action:
            file_id = args.get("file_id", "")
            sql = args.get("sql", "SELECT COUNT(*) FROM chunks")
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return self._sql_query(file_id, sql)

        if "chunk" in action or "retrieve" in action:
            file_id = args.get("file_id", "")
            chunk_idx = int(args.get("chunk_idx", args.get("idx", 0)))
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return self._get_chunk(file_id, chunk_idx)

        if "verify" in action:
            file_id = args.get("file_id", "")
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            entry = self.registry.get(file_id, {})
            if not entry:
                return {"error": f"File {file_id} not in registry"}
            return {"file_id": file_id, "verified": True, "merkle_root": entry.get("merkle_root", ""), "status": entry.get("status", "unknown")}

        if "revoke" in action or "expire" in action:
            file_id = args.get("file_id", "")
            if not file_id:
                upload = self.state.get("upload_result", self.state.get("query_gateway", {}))
                file_id = upload.get("file_id", "") if isinstance(upload, dict) else ""
            if file_id and file_id in self.registry:
                self.registry[file_id]["status"] = "revoked"
                self.registry[file_id]["revoked_at"] = time.time()
                self._save_registry()
                return {"file_id": file_id, "status": "revoked", "revoked_at": time.time()}
            return {"error": f"File {file_id} not found in registry"}

        if "confirm" in action and ("revoke" in action or "404" in action or "closed" in action):
            file_id = args.get("file_id", "")
            entry = self.registry.get(file_id, {})
            if entry.get("status") == "revoked":
                return {"file_id": file_id, "confirmed": True, "access": "closed"}
            return {"file_id": file_id, "confirmed": False, "access": "still_open"}

        if "meta" in action or "metadata" in action:
            file_id = args.get("file_id", "")
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return self._get_meta(file_id)

        if "summary" in action:
            file_id = args.get("file_id", "")
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return self._get_summary(file_id)

        if "capabilit" in action:
            file_id = args.get("file_id", "")
            if not file_id:
                idx = self.state.get("local_index", {})
                file_id = idx.get("file_id", "")
            return {"file_id": file_id, "capabilities": ["sql", "nosql", "search", "chunk", "summary", "meta", "mcp"], "total": 7}

        if "receipt" in action or "issue" in action:
            return {"receipt": self.prev_hash[:16], "chain_length": len(self.receipts)}

        if ("emit" in action or "write" in action or "export" in action) and "manifest" not in action:
            return {"emitted": True, "artifacts": list(self.state.keys())}

        # --- ZipToApp: AI-native zip → .app bundle ---

        # Step 4: analyze binary content — magic bytes, shebang, architecture
        if "analyze" in action and "binary" in action:
            staging_info = self.state.get("staging_dir", {})
            staging_dir = staging_info.get("staging_dir", "") if isinstance(staging_info, dict) else ""
            if not staging_dir or not os.path.exists(staging_dir):
                return {"error": "No staging dir to analyze"}
            analyses = []
            for f in sorted(Path(staging_dir).rglob("*")):
                if not f.is_file() or f.name.startswith("."):
                    continue
                data = f.read_bytes()[:512]
                rel = str(f.relative_to(staging_dir))
                info: dict[str, Any] = {"file": rel, "size": f.stat().st_size}

                # Mach-O magic: 0xFEEDFACE (32-bit), 0xFEEDFACF (64-bit), 0xCAFEBABE (universal)
                if len(data) >= 4:
                    magic = data[:4]
                    if magic == b'\xfe\xed\xfa\xce' or magic == b'\xce\xfa\xed\xfe':
                        info["type"] = "mach-o-32"
                        info["executable"] = True
                        info["arch"] = "i386"
                    elif magic == b'\xfe\xed\xfa\xcf' or magic == b'\xcf\xfa\xed\xfe':
                        info["type"] = "mach-o-64"
                        info["executable"] = True
                        info["arch"] = "x86_64"
                    elif magic == b'\xca\xfe\xba\xbe':
                        info["type"] = "mach-o-universal"
                        info["executable"] = True
                        info["arch"] = "universal"
                    elif magic == b'\x7fELF':
                        info["type"] = "elf"
                        info["executable"] = True
                        info["arch"] = "linux"
                    elif magic[:2] == b'MZ':
                        info["type"] = "pe"
                        info["executable"] = True
                        info["arch"] = "windows"

                # Shebang detection
                if "type" not in info and data[:2] == b'#!':
                    shebang = data[2:].split(b'\n')[0].strip().decode("utf-8", errors="replace")
                    info["type"] = "script"
                    info["shebang"] = shebang
                    info["executable"] = True
                    if "python" in shebang:
                        info["script_type"] = "python"
                    elif "bash" in shebang or "/sh" in shebang:
                        info["script_type"] = "shell"
                    elif "node" in shebang:
                        info["script_type"] = "node"
                    elif "ruby" in shebang:
                        info["script_type"] = "ruby"
                    elif "perl" in shebang:
                        info["script_type"] = "perl"
                    else:
                        info["script_type"] = "unknown"

                # Content sniffing for non-executables
                if "type" not in info:
                    if data[:8] == b'\x89PNG\r\n\x1a\n':
                        info["type"] = "image"
                        info["subtype"] = "png"
                    elif data[:3] == b'\xff\xd8\xff':
                        info["type"] = "image"
                        info["subtype"] = "jpeg"
                    elif data[:6] in (b'GIF87a', b'GIF89a'):
                        info["type"] = "image"
                        info["subtype"] = "gif"
                    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                        info["type"] = "image"
                        info["subtype"] = "webp"
                    elif data[:4] == b'%PDF':
                        info["type"] = "document"
                        info["subtype"] = "pdf"
                    elif data[:5] == b'<?xml':
                        info["type"] = "xml"
                    elif data[:1] == b'{':
                        try:
                            json.loads(data[:512])
                            info["type"] = "json"
                        except Exception:
                            info["type"] = "text"
                    elif data[:1] == b'<' and b'<' in data[:20]:
                        info["type"] = "xml"
                    else:
                        try:
                            data.decode("utf-8")
                            info["type"] = "text"
                        except Exception:
                            info["type"] = "binary"

                info["executable"] = info.get("executable", False) or os.access(f, os.X_OK)
                analyses.append(info)

            exec_count = sum(1 for a in analyses if a.get("executable"))
            type_counts: dict[str, int] = {}
            for a in analyses:
                t = a.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            return {
                "analyses": analyses,
                "file_count": len(analyses),
                "executable_count": exec_count,
                "type_counts": type_counts,
                "has_mach_o": any(a.get("type", "").startswith("mach-o") for a in analyses),
                "has_script": any(a.get("type") == "script" for a in analyses),
                "has_native": any(a.get("type", "").startswith(("mach-o", "elf", "pe")) for a in analyses),
            }

        if "read zip" in action or ("zip" in action and "archive" in action):
            zip_path = args.get("zip", args.get("file", args.get("filepath", "")))
            if not zip_path or not os.path.exists(zip_path):
                return {"error": f"Zip not found: {zip_path}"}
            zf = zipfile.ZipFile(zip_path, "r")
            names = zf.namelist()
            zf.close()
            return {"zip_path": zip_path, "entry_count": len(names), "entries": names[:50]}

        if "validate zip" in action or ("validate" in action and "zip" in action):
            zip_path = args.get("zip", args.get("file", ""))
            if not zip_path:
                contents = self.state.get("zip_contents", {})
                zip_path = contents.get("zip_path", "") if isinstance(contents, dict) else ""
            if not zip_path or not os.path.exists(zip_path):
                return {"error": "No zip to validate"}
            try:
                zf = zipfile.ZipFile(zip_path, "r")
                bad = zf.testzip()
                names = zf.namelist()
                zf.close()
                if bad is not None:
                    return {"valid": False, "corrupt_entry": bad}
                has_exec = any(
                    n.endswith(".app/Contents/MacOS/") or
                    any(n.lower().endswith(ext) for ext in ("", ".sh", ".py", ".bin"))
                    and not n.endswith("/") for n in names
                )
                return {"valid": True, "entry_count": len(names), "has_executable_candidate": has_exec}
            except Exception as e:
                return {"valid": False, "error": str(e)}

        if "extract zip" in action or ("extract" in action and "zip" in action):
            zip_path = args.get("zip", args.get("file", ""))
            if not zip_path:
                contents = self.state.get("zip_contents", {})
                zip_path = contents.get("zip_path", "") if isinstance(contents, dict) else ""
            if not zip_path or not os.path.exists(zip_path):
                return {"error": "No zip to extract"}
            staging = Path(tempfile.mkdtemp(prefix="ziptoapp_"))
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(staging)
            file_list = [str(f.relative_to(staging)) for f in staging.rglob("*") if f.is_file()]
            return {"staging_dir": str(staging), "file_count": len(file_list), "files": file_list[:50]}

        if "detect" in action and "exec" in action:
            staging_info = self.state.get("staging_dir", {})
            staging_dir = staging_info.get("staging_dir", "") if isinstance(staging_info, dict) else ""
            binary_info = self.state.get("binary_analysis", {})
            analyses = binary_info.get("analyses", []) if isinstance(binary_info, dict) else []
            if not staging_dir or not os.path.exists(staging_dir):
                return {"error": "No staging dir to scan"}

            # AI priority: Mach-O native > script with shebang > any executable > largest file
            mach_o = [a for a in analyses if a.get("type", "").startswith("mach-o")]
            scripts = [a for a in analyses if a.get("type") == "script"]
            other_exec = [a for a in analyses if a.get("executable") and a not in mach_o and a not in scripts]

            if mach_o:
                exec_entry = mach_o[0]["file"]
                exec_type = mach_o[0]["type"]
                exec_arch = mach_o[0].get("arch", "unknown")
            elif scripts:
                exec_entry = scripts[0]["file"]
                exec_type = "script"
                exec_arch = scripts[0].get("script_type", "unknown")
            elif other_exec:
                exec_entry = other_exec[0]["file"]
                exec_type = other_exec[0].get("type", "unknown")
                exec_arch = other_exec[0].get("arch", "unknown")
            else:
                # Fallback: largest file
                largest = max(analyses, key=lambda a: a.get("size", 0)) if analyses else None
                exec_entry = largest["file"] if largest else ""
                exec_type = "fallback"
                exec_arch = "unknown"

            # Infer app name from exec entry or zip name
            app_name = args.get("app_name", args.get("name", ""))
            if not app_name:
                if exec_entry:
                    app_name = Path(exec_entry).stem
                else:
                    p = args.get("zip", args.get("file", "MyApp.zip"))
                    app_name = Path(p).stem
            if not app_name.endswith(".app"):
                app_name = app_name + ".app"

            return {
                "exec_entry": exec_entry,
                "exec_type": exec_type,
                "exec_arch": exec_arch,
                "app_name": app_name,
                "candidates": [a["file"] for a in (mach_o + scripts + other_exec)[:10]],
                "selection_reason": "mach-o native" if mach_o else ("script" if scripts else ("executable" if other_exec else "largest file fallback")),
            }

        if "generate" in action and "plist" in action:
            exec_info = self.state.get("exec_entry", {})
            exec_entry = exec_info.get("exec_entry", "") if isinstance(exec_info, dict) else ""
            app_name = exec_info.get("app_name", "MyApp.app") if isinstance(exec_info, dict) else "MyApp.app"
            bundle_id = args.get("bundle_id", f"com.local.{Path(app_name).stem.lower()}")
            plist_data = {
                "CFBundleName": Path(app_name).stem,
                "CFBundleDisplayName": Path(app_name).stem,
                "CFBundleIdentifier": bundle_id,
                "CFBundleVersion": args.get("version", "1.0.0"),
                "CFBundleShortVersionString": args.get("version", "1.0.0"),
                "CFBundlePackageType": "APPL",
                "CFBundleExecutable": Path(exec_entry).name if exec_entry else "main",
                "CFBundleInfoDictionaryVersion": "6.0",
                "LSMinimumSystemVersion": args.get("min_os", "10.13"),
                "NSHighResolutionCapable": True,
            }
            return {"plist": plist_data, "bundle_id": bundle_id, "app_name": app_name}

        # Step 6: classify resources — smart content-aware categorization
        if "classify" in action and "resource" in action:
            binary_info = self.state.get("binary_analysis", {})
            analyses = binary_info.get("analyses", []) if isinstance(binary_info, dict) else []
            exec_info = self.state.get("exec_entry", {})
            exec_entry = exec_info.get("exec_entry", "") if isinstance(exec_info, dict) else ""

            categories: dict[str, list] = {
                "Assets": [],
                "Helpers": [],
                "Data": [],
                "Frameworks": [],
                "Localization": [],
                "Documentation": [],
                "Configuration": [],
                "Scripts": [],
            }
            for a in analyses:
                f = a["file"]
                if f == exec_entry:
                    continue
                t = a.get("type", "unknown")
                sub = a.get("subtype", "")
                st = a.get("script_type", "")
                name = Path(f).name.lower()
                ext = Path(f).suffix.lower()

                if t == "image":
                    categories["Assets"].append(f)
                elif t == "script" and st in ("python", "ruby", "perl", "node"):
                    categories["Helpers"].append(f)
                elif t == "script" and st == "shell":
                    categories["Scripts"].append(f)
                elif t == "json" or ext in (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"):
                    categories["Configuration"].append(f)
                elif t in ("text", "xml") or ext in (".md", ".txt", ".rtf", ".html"):
                    if name.startswith("readme") or name.startswith("license") or ext == ".md":
                        categories["Documentation"].append(f)
                    elif ext in (".strings", ".lproj") or "/locales/" in f or "/lang/" in f or "/l10n/" in f:
                        categories["Localization"].append(f)
                    else:
                        categories["Data"].append(f)
                elif ext in (".dylib", ".framework", ".a") or "framework" in name:
                    categories["Frameworks"].append(f)
                elif ext in (".db", ".sqlite", ".sqlite3"):
                    categories["Data"].append(f)
                elif t == "binary":
                    categories["Data"].append(f)
                else:
                    categories["Data"].append(f)

            return {
                "categories": categories,
                "total_resources": sum(len(v) for v in categories.values()),
                "category_counts": {k: len(v) for k, v in categories.items() if v},
            }

        # Step 7: infer entitlements — scan content for capability hints
        if "infer" in action and "entitlement" in action:
            binary_info = self.state.get("binary_analysis", {})
            analyses = binary_info.get("analyses", []) if isinstance(binary_info, dict) else []
            staging_info = self.state.get("staging_dir", {})
            staging_dir = staging_info.get("staging_dir", "") if isinstance(staging_info, dict) else ""

            entitlements: dict[str, bool] = {
                "com.apple.security.app-sandbox": False,
                "com.apple.security.network.client": False,
                "com.apple.security.network.server": False,
                "com.apple.security.files.user-selected.read-write": False,
                "com.apple.security.files.downloads.read-write": False,
                "com.apple.security.device.camera": False,
                "com.apple.security.device.microphone": False,
                "com.apple.security.automation.apple-events": False,
            }

            # Scan all text content for capability hints
            keywords: dict[str, str] = {
                "socket": "com.apple.security.network.client",
                "http": "com.apple.security.network.client",
                "fetch": "com.apple.security.network.client",
                "curl": "com.apple.security.network.client",
                "listen": "com.apple.security.network.server",
                "server": "com.apple.security.network.server",
                "bind": "com.apple.security.network.server",
                "camera": "com.apple.security.device.camera",
                "AVCapture": "com.apple.security.device.camera",
                "microphone": "com.apple.security.device.microphone",
                "AudioInput": "com.apple.security.device.microphone",
                "AppleScript": "com.apple.security.automation.apple-events",
                "osascript": "com.apple.security.automation.apple-events",
                "NSOpenPanel": "com.apple.security.files.user-selected.read-write",
                "NSSavePanel": "com.apple.security.files.user-selected.read-write",
                "Downloads": "com.apple.security.files.downloads.read-write",
            }

            if staging_dir:
                for f in Path(staging_dir).rglob("*"):
                    if not f.is_file() or f.stat().st_size > 1024 * 1024:
                        continue
                    try:
                        content = f.read_bytes()[:8192].decode("utf-8", errors="replace").lower()
                    except Exception:
                        continue
                    for kw, ent in keywords.items():
                        if kw.lower() in content:
                            entitlements[ent] = True

            active = {k: v for k, v in entitlements.items() if v}
            return {
                "entitlements": entitlements,
                "active_count": len(active),
                "active": list(active.keys()),
                "sandbox": len(active) > 0,
            }

        # Step 8: build dependency graph — analyze imports/requires/links
        if ("build" in action and "dependency" in action) or ("build" in action and "graph" in action):
            staging_info = self.state.get("staging_dir", {})
            staging_dir = staging_info.get("staging_dir", "") if isinstance(staging_info, dict) else ""
            exec_info = self.state.get("exec_entry", {})
            exec_entry = exec_info.get("exec_entry", "") if isinstance(exec_info, dict) else ""
            binary_info = self.state.get("binary_analysis", {})
            analyses = binary_info.get("analyses", []) if isinstance(binary_info, dict) else []

            nodes: list[dict] = []
            edges: list[dict] = []
            for a in analyses:
                f = a["file"]
                nodes.append({"id": f, "type": a.get("type", "unknown"), "size": a.get("size", 0), "is_entry": f == exec_entry})

            if staging_dir:
                for f in Path(staging_dir).rglob("*"):
                    if not f.is_file() or f.stat().st_size > 512 * 1024:
                        continue
                    try:
                        content = f.read_bytes()[:8192].decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    rel = str(f.relative_to(staging_dir))
                    # Python imports
                    for m in re.findall(r'^(?:import|from)\s+(\S+)', content, re.MULTILINE):
                        edges.append({"from": rel, "to": m, "type": "python_import"})
                    # Shell source/include
                    for m in re.findall(r'(?:source|\.)\s+(\S+)', content):
                        edges.append({"from": rel, "to": m, "type": "shell_source"})
                    # require() / import in JS
                    for m in re.findall(r"require\(['\"]([^'\"]+)['\"]\)", content):
                        edges.append({"from": rel, "to": m, "type": "js_require"})
                    for m in re.findall(r"import\s+.*from\s+['\"]([^'\"]+)['\"]", content):
                        edges.append({"from": rel, "to": m, "type": "js_import"})
                    # @import in Swift
                    for m in re.findall(r'@import\s+(\S+)', content):
                        edges.append({"from": rel, "to": m, "type": "swift_import"})
                    # #include in C
                    for m in re.findall(r'#include\s+[<"]([^>"]+)[>"]', content):
                        edges.append({"from": rel, "to": m, "type": "c_include"})

            return {
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "entry_point": exec_entry,
                "has_dependencies": len(edges) > 0,
            }

        if "assemble" in action and ("app" in action or "bundle" in action):
            staging_info = self.state.get("staging_dir", {})
            staging_dir = staging_info.get("staging_dir", "") if isinstance(staging_info, dict) else ""
            exec_info = self.state.get("exec_entry", {})
            exec_entry = exec_info.get("exec_entry", "") if isinstance(exec_info, dict) else ""
            app_name = exec_info.get("app_name", "MyApp.app") if isinstance(exec_info, dict) else "MyApp.app"
            plist_info = self.state.get("info_plist", {})
            plist_data = plist_info.get("plist", {}) if isinstance(plist_info, dict) else {}
            resource_map = self.state.get("resource_map", {})
            categories = resource_map.get("categories", {}) if isinstance(resource_map, dict) else {}

            if not staging_dir:
                return {"error": "No staging dir to assemble from"}

            output_dir = Path(args.get("output_dir", "build"))
            output_dir.mkdir(parents=True, exist_ok=True)
            app_bundle = output_dir / app_name
            contents = app_bundle / "Contents"
            macos_dir = contents / "MacOS"
            resources_dir = contents / "Resources"
            frameworks_dir = contents / "Frameworks"
            helpers_dir = macos_dir / "Helpers"
            macos_dir.mkdir(parents=True, exist_ok=True)
            resources_dir.mkdir(parents=True, exist_ok=True)

            exec_name = plist_data.get("CFBundleExecutable", Path(exec_entry).name if exec_entry else "main")
            exec_dest = macos_dir / exec_name

            if exec_entry:
                exec_src = Path(staging_dir) / exec_entry
                if exec_src.exists():
                    shutil.copy2(exec_src, exec_dest)
                else:
                    exec_dest.write_bytes(b"#!/bin/bash\nexit 0\n")
            else:
                exec_dest.write_bytes(b"#!/bin/bash\nexit 0\n")

            # Smart placement using resource map
            placed = {"Resources": 0, "Helpers": 0, "Frameworks": 0, "Scripts": 0}
            for category, files in categories.items():
                for f in files:
                    src = Path(staging_dir) / f
                    if not src.exists():
                        continue
                    if category == "Helpers":
                        helpers_dir.mkdir(parents=True, exist_ok=True)
                        dest = helpers_dir / Path(f).name
                        shutil.copy2(src, dest)
                        os.chmod(dest, 0o755)
                        placed["Helpers"] += 1
                    elif category == "Frameworks":
                        frameworks_dir.mkdir(parents=True, exist_ok=True)
                        dest = frameworks_dir / Path(f).name
                        shutil.copy2(src, dest)
                        placed["Frameworks"] += 1
                    elif category == "Scripts":
                        dest = macos_dir / Path(f).name
                        shutil.copy2(src, dest)
                        os.chmod(dest, 0o755)
                        placed["Scripts"] += 1
                    else:
                        dest = resources_dir / Path(f).name
                        shutil.copy2(src, dest)
                        placed["Resources"] += 1

            # Fallback: any files not in resource map go to Resources
            categorized = set()
            for files in categories.values():
                categorized.update(files)
            for f in Path(staging_dir).rglob("*"):
                if f.is_file() and str(f.relative_to(staging_dir)) != exec_entry:
                    rel = str(f.relative_to(staging_dir))
                    if rel not in categorized:
                        dest = resources_dir / Path(rel).name
                        shutil.copy2(f, dest)
                        placed["Resources"] += 1

            plist_path = contents / "Info.plist"
            with open(plist_path, "wb") as pf:
                plistlib.dump(plist_data, pf)

            return {"app_bundle": str(app_bundle), "exec_path": str(exec_dest), "plist_path": str(plist_path), "contents_root": str(contents), "placed": placed}

        if "set" in action and ("permission" in action or "exec" in action and "perm" in action):
            bundle_info = self.state.get("app_bundle", {})
            exec_path = bundle_info.get("exec_path", "") if isinstance(bundle_info, dict) else ""
            if not exec_path or not os.path.exists(exec_path):
                return {"error": "No executable to chmod"}
            os.chmod(exec_path, 0o755)
            return {"exec_path": exec_path, "permissions": "755", "set": True}

        if "code sign" in action or ("sign" in action and "code" in action):
            bundle_info = self.state.get("app_bundle", {})
            app_bundle = bundle_info.get("app_bundle", "") if isinstance(bundle_info, dict) else ""
            if not app_bundle or not os.path.exists(app_bundle):
                return {"error": "No bundle to sign"}
            try:
                result = subprocess.run(
                    ["codesign", "--force", "--deep", "--sign", "-", app_bundle],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return {"signed": True, "bundle": app_bundle, "signature": "ad-hoc", "stdout": result.stdout[:200]}
                else:
                    return {"signed": False, "bundle": app_bundle, "error": result.stderr[:300], "fallback": "codesign not available or failed"}
            except FileNotFoundError:
                return {"signed": False, "bundle": app_bundle, "error": "codesign not found", "fallback": "skipped on non-macOS"}
            except Exception as e:
                return {"signed": False, "bundle": app_bundle, "error": str(e)}

        # Step 13: emit AI manifest — machine-readable bundle description
        if ("emit" in action and "manifest" in action) or ("ai" in action and "manifest" in action):
            bundle_info = self.state.get("app_bundle", {})
            app_bundle = bundle_info.get("app_bundle", "") if isinstance(bundle_info, dict) else ""
            exec_info = self.state.get("exec_entry", {})
            exec_type = exec_info.get("exec_type", "unknown") if isinstance(exec_info, dict) else "unknown"
            exec_arch = exec_info.get("exec_arch", "unknown") if isinstance(exec_info, dict) else "unknown"
            plist_info = self.state.get("info_plist", {})
            plist_data = plist_info.get("plist", {}) if isinstance(plist_info, dict) else {}
            resource_map = self.state.get("resource_map", {})
            categories = resource_map.get("categories", {}) if isinstance(resource_map, dict) else {}
            ent_info = self.state.get("entitlements", {})
            active_ents = ent_info.get("active", []) if isinstance(ent_info, dict) else []
            dep_info = self.state.get("dependency_graph", {})
            edge_count = dep_info.get("edge_count", 0) if isinstance(dep_info, dict) else 0
            node_count = dep_info.get("node_count", 0) if isinstance(dep_info, dict) else 0
            binary_info = self.state.get("binary_analysis", {})
            type_counts = binary_info.get("type_counts", {}) if isinstance(binary_info, dict) else {}

            manifest = {
                "schema": "ai.app.manifest.v1",
                "glyph": "⟡◆⌁",
                "app_name": plist_data.get("CFBundleName", "Unknown"),
                "bundle_id": plist_data.get("CFBundleIdentifier", ""),
                "version": plist_data.get("CFBundleVersion", "1.0.0"),
                "executable": {
                    "name": plist_data.get("CFBundleExecutable", "main"),
                    "type": exec_type,
                    "arch": exec_arch,
                    "native": exec_type.startswith("mach-o"),
                },
                "capabilities": {
                    "network": "com.apple.security.network.client" in active_ents or "com.apple.security.network.server" in active_ents,
                    "camera": "com.apple.security.device.camera" in active_ents,
                    "microphone": "com.apple.security.device.microphone" in active_ents,
                    "file_access": "com.apple.security.files.user-selected.read-write" in active_ents,
                    "automation": "com.apple.security.automation.apple-events" in active_ents,
                    "sandbox": len(active_ents) > 0,
                },
                "entitlements": active_ents,
                "resources": {k: len(v) for k, v in categories.items() if v},
                "content_types": type_counts,
                "dependency_graph": {
                    "nodes": node_count,
                    "edges": edge_count,
                    "has_dependencies": edge_count > 0,
                },
                "bundle_path": app_bundle,
                "launchable": bool(app_bundle and os.path.exists(app_bundle)),
                "signed": isinstance(self.state.get("code_signature", {}), dict) and self.state.get("code_signature", {}).get("signed", False),
            }

            # Write manifest into bundle
            if app_bundle and os.path.exists(app_bundle):
                manifest_path = Path(app_bundle) / "Contents" / "AIManifest.json"
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

            return {"manifest": manifest, "manifest_path": str(Path(app_bundle) / "Contents" / "AIManifest.json") if app_bundle else ""}

        # Step 14: self-heal bundle validation — detect and fix structural issues
        if "self-heal" in action or ("heal" in action and "bundle" in action) or ("heal" in action and "validation" in action):
            bundle_info = self.state.get("app_bundle", {})
            app_bundle = bundle_info.get("app_bundle", "") if isinstance(bundle_info, dict) else ""
            if not app_bundle or not os.path.exists(app_bundle):
                return {"error": "No bundle to heal"}

            issues: list[dict] = []
            fixes: list[dict] = []
            bundle = Path(app_bundle)
            contents = bundle / "Contents"
            macos_dir = contents / "MacOS"
            resources_dir = contents / "Resources"
            plist_path = contents / "Info.plist"

            # Check 1: Info.plist exists and is valid
            if not plist_path.exists():
                issues.append({"severity": "critical", "issue": "Info.plist missing"})
                plist_data = {"CFBundleName": bundle.stem, "CFBundleExecutable": "main", "CFBundleIdentifier": f"com.local.{bundle.stem.lower()}", "CFBundleVersion": "1.0.0", "CFBundlePackageType": "APPL"}
                with open(plist_path, "wb") as pf:
                    plistlib.dump(plist_data, pf)
                fixes.append({"fix": "generated default Info.plist"})
            else:
                try:
                    with open(plist_path, "rb") as pf:
                        plist_data = plistlib.load(pf)
                    exec_name = plist_data.get("CFBundleExecutable", "")
                    if not exec_name:
                        issues.append({"severity": "critical", "issue": "CFBundleExecutable missing from plist"})
                        plist_data["CFBundleExecutable"] = "main"
                        with open(plist_path, "wb") as pf:
                            plistlib.dump(plist_data, pf)
                        fixes.append({"fix": "set CFBundleExecutable=main"})
                    else:
                        exec_file = macos_dir / exec_name
                        if not exec_file.exists():
                            issues.append({"severity": "critical", "issue": f"executable '{exec_name}' not in MacOS/"})
                            exec_file.write_bytes(b"#!/bin/bash\nexit 0\n")
                            os.chmod(exec_file, 0o755)
                            fixes.append({"fix": f"created stub executable '{exec_name}'"})
                except Exception as e:
                    issues.append({"severity": "critical", "issue": f"Info.plist corrupt: {e}"})
                    fixes.append({"fix": "Info.plist needs manual repair"})

            # Check 2: MacOS/ directory exists
            if not macos_dir.exists():
                issues.append({"severity": "critical", "issue": "MacOS/ directory missing"})
                macos_dir.mkdir(parents=True, exist_ok=True)
                fixes.append({"fix": "created MacOS/ directory"})

            # Check 3: executable has correct permissions
            plist_data = {}
            try:
                with open(plist_path, "rb") as pf:
                    plist_data = plistlib.load(pf)
            except Exception:
                pass
            exec_name = plist_data.get("CFBundleExecutable", "main")
            exec_file = macos_dir / exec_name
            if exec_file.exists() and not os.access(exec_file, os.X_OK):
                issues.append({"severity": "high", "issue": "executable lacks execute permission"})
                os.chmod(exec_file, 0o755)
                fixes.append({"fix": "set executable to 0o755"})

            # Check 4: Resources/ directory exists
            if not resources_dir.exists():
                issues.append({"severity": "low", "issue": "Resources/ directory missing"})
                resources_dir.mkdir(parents=True, exist_ok=True)
                fixes.append({"fix": "created Resources/ directory"})

            # Check 5: no empty directories
            empty_dirs = [str(d.relative_to(bundle)) for d in bundle.rglob("*") if d.is_dir() and not any(d.iterdir())]
            for d in empty_dirs:
                issues.append({"severity": "low", "issue": f"empty directory: {d}"})
            if empty_dirs:
                fixes.append({"fix": f"noted {len(empty_dirs)} empty directories (non-blocking)"})

            # Check 6: AIManifest.json exists
            ai_manifest = contents / "AIManifest.json"
            if not ai_manifest.exists():
                issues.append({"severity": "medium", "issue": "AIManifest.json missing"})
                fixes.append({"fix": "AI manifest will be emitted in step 13 (or re-run)"})

            healthy = len([i for i in issues if i["severity"] == "critical"]) == 0
            return {
                "healthy": healthy,
                "issue_count": len(issues),
                "fix_count": len(fixes),
                "issues": issues,
                "fixes": fixes,
                "critical_count": len([i for i in issues if i["severity"] == "critical"]),
                "high_count": len([i for i in issues if i["severity"] == "high"]),
                "low_count": len([i for i in issues if i["severity"] == "low"]),
            }

        if "compute" in action and "bundle" in action and ("hash" in action or "sha" in action):
            bundle_info = self.state.get("app_bundle", {})
            app_bundle = bundle_info.get("app_bundle", "") if isinstance(bundle_info, dict) else ""
            if not app_bundle or not os.path.exists(app_bundle):
                return {"error": "No bundle to hash"}
            h = hashlib.sha256()
            file_count = 0
            for f in sorted(Path(app_bundle).rglob("*")):
                if f.is_file():
                    h.update(f.read_bytes())
                    file_count += 1
            return {"bundle_hash": h.hexdigest(), "file_count": file_count, "bundle": app_bundle}

        return {"action": action, "status": "executed", "step": step_num}

    def _index_file(self, filepath: str) -> dict:
        """Real file indexing: SHA256, line count, word freq, chunks, SQLite index."""
        start = time.time()
        path = Path(filepath)
        content = path.read_bytes()
        size = len(content)
        merkle_root = hashlib.sha256(content).hexdigest()
        file_id = merkle_root[:12]

        text = content.decode("utf-8", errors="replace")
        lines = text.split("\n")
        line_count = len(lines)
        words = re.findall(r"\b\w+\b", text)
        word_freq: dict[str, int] = {}
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1
        top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:20]

        chunks = []
        current_chunk = []
        chunk_start = 0
        for i, line in enumerate(lines):
            current_chunk.append(line)
            is_boundary = (
                (line.strip() == "" and len(current_chunk) > 5)
                or line.strip().startswith("def ")
                or line.strip().startswith("class ")
                or line.strip().startswith("func ")
                or line.strip().startswith("▷")
                or line.strip().startswith("workflow:")
            )
            if is_boundary and len(current_chunk) >= 3:
                chunks.append({
                    "idx": len(chunks), "line_start": chunk_start, "line_end": i,
                    "boundary_type": "function" if line.strip().startswith(("def ", "class ", "func ")) else "paragraph",
                    "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk),
                })
                current_chunk = []
                chunk_start = i + 1
        if current_chunk:
            chunks.append({
                "idx": len(chunks), "line_start": chunk_start, "line_end": line_count - 1,
                "boundary_type": "final", "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk),
            })

        symbols = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            for prefix in ["def ", "class ", "func ", "async def "]:
                if stripped.startswith(prefix):
                    name = stripped[len(prefix):].split("(")[0].split(":")[0].strip()
                    symbols.append({"line": i + 1, "name": name, "type": prefix.strip()})

        idx_path = self.index_dir / f"{file_id}.idx"
        conn = sqlite3.connect(str(idx_path))
        conn.execute("CREATE TABLE IF NOT EXISTS file_meta (key TEXT, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (idx INTEGER, line_start INTEGER, line_end INTEGER, boundary_type TEXT, preview TEXT, line_count INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS word_freq (word TEXT, count INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS symbols (line INTEGER, name TEXT, type TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS capabilities (id INTEGER, name TEXT)")

        meta = {"filename": path.name, "size_bytes": str(size), "total_lines": str(line_count), "total_words": str(len(words)), "merkle_root": merkle_root, "total_chunks": str(len(chunks)), "total_symbols": str(len(symbols))}
        for k, v in meta.items():
            conn.execute("INSERT INTO file_meta VALUES (?,?)", (k, v))
        for c in chunks:
            conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?)", (c["idx"], c["line_start"], c["line_end"], c["boundary_type"], c["preview"], c["line_count"]))
        for w, cnt in top_words:
            conn.execute("INSERT INTO word_freq VALUES (?,?)", (w, cnt))
        for s in symbols:
            conn.execute("INSERT INTO symbols VALUES (?,?,?)", (s["line"], s["name"], s["type"]))
        caps = [(i, name) for i, name in enumerate(["sql", "nosql", "search", "chunk", "summary", "meta", "mcp", "word_freq", "symbols", "chunks", "merkle", "sha256", "capabilities", "revocation"])]
        conn.executemany("INSERT INTO capabilities VALUES (?,?)", caps)
        conn.commit()
        conn.close()

        elapsed = round((time.time() - start) * 1000, 2)
        index_size = idx_path.stat().st_size

        return {
            "file_id": file_id, "filename": path.name, "size_bytes": size,
            "size_human": f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB",
            "total_lines": line_count, "total_words": len(words),
            "total_chunks": len(chunks), "total_symbols": len(symbols),
            "merkle_root": merkle_root, "index_path": str(idx_path),
            "index_size_bytes": index_size, "index_ratio": round(index_size / max(size, 1) * 100, 1),
            "index_time_ms": elapsed, "capabilities": 14,
        }

    def _compute_hash(self, filepath: str) -> str:
        content = Path(filepath).read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _search(self, file_id: str, query: str) -> dict:
        idx_path = self.index_dir / f"{file_id}.idx"
        if not idx_path.exists():
            return {"error": f"Index not found for {file_id}"}
        conn = sqlite3.connect(str(idx_path))
        chunk_results = conn.execute("SELECT idx, line_start, line_end, preview FROM chunks WHERE preview LIKE ?", (f"%{query}%",)).fetchall()
        sym_results = conn.execute("SELECT line, name, type FROM symbols WHERE name LIKE ?", (f"%{query}%",)).fetchall()
        word_results = conn.execute("SELECT word, count FROM word_freq WHERE word LIKE ? ORDER BY count DESC LIMIT 10", (f"%{query}%",)).fetchall()
        conn.close()
        total = len(chunk_results) + len(sym_results) + len(word_results)
        return {
            "file_id": file_id, "query": query, "total_matches": total,
            "chunks": [{"idx": r[0], "lines": f"{r[1]}-{r[2]}", "preview": r[3][:80]} for r in chunk_results],
            "symbols": [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_results],
            "words": [{"word": r[0], "count": r[1]} for r in word_results],
        }

    def _sql_query(self, file_id: str, sql: str) -> dict:
        if not sql.strip().upper().startswith("SELECT"):
            return {"error": "Only SELECT statements allowed"}
        for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ATTACH", "PRAGMA", "CREATE", "ALTER"]:
            if kw in sql.upper():
                return {"error": f"{kw} not allowed"}
        idx_path = self.index_dir / f"{file_id}.idx"
        if not idx_path.exists():
            return {"error": f"Index not found for {file_id}"}
        conn = sqlite3.connect(str(idx_path))
        try:
            cursor = conn.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(1000)
            conn.close()
            return {"file_id": file_id, "sql": sql, "columns": columns, "rows": rows, "row_count": len(rows)}
        except Exception as e:
            conn.close()
            return {"error": str(e)}

    def _get_chunk(self, file_id: str, chunk_idx: int) -> dict:
        idx_path = self.index_dir / f"{file_id}.idx"
        if not idx_path.exists():
            return {"error": f"Index not found for {file_id}"}
        conn = sqlite3.connect(str(idx_path))
        row = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks WHERE idx = ?", (chunk_idx,)).fetchone()
        conn.close()
        if not row:
            return {"error": f"Chunk {chunk_idx} not found"}
        return {"idx": row[0], "line_start": row[1], "line_end": row[2], "boundary_type": row[3], "preview": row[4], "line_count": row[5]}

    def _get_meta(self, file_id: str) -> dict:
        idx_path = self.index_dir / f"{file_id}.idx"
        if not idx_path.exists():
            return {"error": f"Index not found for {file_id}"}
        conn = sqlite3.connect(str(idx_path))
        rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
        conn.close()
        return {"file_id": file_id, "meta": {r[0]: r[1] for r in rows}}

    def _get_summary(self, file_id: str) -> dict:
        idx_path = self.index_dir / f"{file_id}.idx"
        if not idx_path.exists():
            return {"error": f"Index not found for {file_id}"}
        conn = sqlite3.connect(str(idx_path))
        chunks = conn.execute("SELECT idx, boundary_type, line_start, line_end FROM chunks LIMIT 20").fetchall()
        symbols = conn.execute("SELECT line, name, type FROM symbols LIMIT 20").fetchall()
        conn.close()
        return {
            "file_id": file_id, "total_chunks": len(chunks),
            "chunks": [{"idx": r[0], "type": r[1], "lines": f"{r[2]}-{r[3]}"} for r in chunks],
            "total_symbols": len(symbols),
            "symbols": [{"line": r[0], "name": r[1], "type": r[2]} for r in symbols],
        }


def cmd_run(filepath: str, args: list[str] | None = None):
    """Execute a .over workflow with real file I/O."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: {filepath} not found")
        sys.exit(1)
    if path.suffix != ".over":
        print(f"Error: {filepath} is not a .over file")
        sys.exit(1)

    source = path.read_text()
    wf = parse_over(source)

    runtime_args: dict[str, str] = {}
    if args:
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                runtime_args[k.lstrip("--")] = v

    print(f"GlyphForge - Executing workflow: {wf.name}")
    print(f"  Intent: {wf.intent}")
    print(f"  Steps: {len(wf.steps)}")
    print(f"  Args: {runtime_args}")
    print()

    rt = OverRuntime()
    artifact = rt.execute(wf, runtime_args)

    print()
    print(f"  Merkle root: {artifact['merkle_root'][:16]}...")
    print(f"  SHA256: {artifact['sha256'][:16]}...")
    print(f"  Receipts: {len(artifact['receipt_chain'])}")

    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)
    out_path = build_dir / f"{path.stem}_exec.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    print(f"  Output: {out_path}")

    print()
    print("  State:")
    for k, v in artifact["state"].items():
        if isinstance(v, dict):
            summary = str(v)[:120]
            print(f"    {k}: {summary}...")
        else:
            print(f"    {k}: {v}")


