"""
ZipToApp — AI-native zip → .app bundle renderer.

16-step pipeline: read zip → validate → extract → analyze binaries →
detect exec → generate plist → classify resources → infer entitlements →
build dependency graph → assemble bundle → set permissions → code sign →
emit AI manifest → self-heal validation → compute hash → write receipts.
"""

import sys
import json
from pathlib import Path
from overlang import parse_over, OverRuntime


def cmd_ziptoapp(args: list[str] | None = None):
    """ZipToApp CLI: render a .zip into a macOS .app bundle via .over workflow."""
    if not args:
        print("ZipToApp — Render zip into .app bundle")
        print()
        print("Usage:")
        print("  python3 forge.py ziptoapp <file.zip> [app_name] [--bundle_id=...] [--version=...]")
        print()
        print("Output: build/<AppName>.app with Info.plist, executable, Resources, ad-hoc signature")
        sys.exit(0)

    zip_path = args[0]
    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found")
        sys.exit(1)

    runtime_args: dict[str, str] = {"zip": zip_path}
    for a in args[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            runtime_args[k.lstrip("--")] = v
        elif not a.startswith("-"):
            runtime_args["app_name"] = a + ".app" if not a.endswith(".app") else a

    wf_path = Path("src/zip_to_app.over")
    if not wf_path.exists():
        print(f"Error: {wf_path} not found")
        sys.exit(1)

    source = wf_path.read_text()
    wf = parse_over(source)

    print(f"ZipToApp — AI-native zip → .app renderer")
    print(f"  Workflow: {wf.name}")
    print(f"  Steps: {len(wf.steps)}")
    print(f"  Args: {runtime_args}")
    print()

    rt = OverRuntime()
    artifact = rt.execute(wf, runtime_args)

    state = artifact.get("state", {})
    print()
    print("  ── AI ANALYSIS ──")

    binary_info = state.get("binary_analysis", {})
    if isinstance(binary_info, dict):
        tc = binary_info.get("type_counts", {})
        print(f"  Binary types: {tc}")
        print(f"  Has Mach-O: {binary_info.get('has_mach_o', False)}")
        print(f"  Has script: {binary_info.get('has_script', False)}")

    exec_info = state.get("exec_entry", {})
    if isinstance(exec_info, dict):
        print(f"  Executable: {exec_info.get('exec_entry', '')} ({exec_info.get('exec_type', '?')}/{exec_info.get('exec_arch', '?')})")
        print(f"  Selection: {exec_info.get('selection_reason', '?')}")

    resource_map = state.get("resource_map", {})
    if isinstance(resource_map, dict):
        cc = resource_map.get("category_counts", {})
        print(f"  Resources: {cc}")

    ent_info = state.get("entitlements", {})
    if isinstance(ent_info, dict):
        print(f"  Entitlements: {ent_info.get('active_count', 0)} active — {ent_info.get('active', [])}")

    dep_info = state.get("dependency_graph", {})
    if isinstance(dep_info, dict):
        print(f"  Dependency graph: {dep_info.get('node_count', 0)} nodes, {dep_info.get('edge_count', 0)} edges")

    heal_info = state.get("heal_report", {})
    if isinstance(heal_info, dict):
        print(f"  Self-heal: {heal_info.get('issue_count', 0)} issues, {heal_info.get('fix_count', 0)} fixes, healthy={heal_info.get('healthy', False)}")

    ai_manifest = state.get("ai_manifest", {})
    if isinstance(ai_manifest, dict):
        manifest = ai_manifest.get("manifest", {})
        if isinstance(manifest, dict):
            print(f"  AI Manifest: {manifest.get('glyph', '')} schema={manifest.get('schema', '')}")
            caps = manifest.get("capabilities", {})
            print(f"  Capabilities: {caps}")

    print()
    bundle_info = state.get("app_bundle", {})
    if isinstance(bundle_info, dict):
        app_bundle = bundle_info.get("app_bundle", "")
        placed = bundle_info.get("placed", {})
        print(f"  Bundle: {app_bundle}")
        if placed:
            print(f"  Placement: {placed}")
    bundle_hash = state.get("bundle_hash", {})
    if isinstance(bundle_hash, dict) and bundle_hash.get("bundle_hash"):
        print(f"  Bundle SHA256: {bundle_hash.get('bundle_hash', '')[:32]}...")
        print(f"  Files hashed: {bundle_hash.get('file_count', 0)}")
    print(f"  Merkle root: {artifact['merkle_root'][:16]}...")
    print(f"  Receipts: {len(artifact['receipt_chain'])}")

    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)
    out_path = build_dir / "zip_to_app_exec.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    print(f"  Output: {out_path}")
