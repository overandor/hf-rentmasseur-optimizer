"""
Deployment Adapters — Protocols 213-216

Protocol 213: Vercel Deployment Adapter
Protocol 214: Netlify Deployment Adapter
Protocol 215: IPFS Pinning Adapter
Protocol 216: Local Static Export Adapter

All adapters produce DeploymentReceipt records via DeploymentReceiptProtocol.
No fake URLs — if deployment fails, status is "failed" honestly.
"""

import hashlib
import json
import os
import time
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Optional

from .schema import OracleDB
from .receipt_ledger import ReceiptLedger
from .extended_bridges import DeploymentReceiptProtocol


@dataclass
class DeploymentConfig:
    target: str  # vercel, netlify, ipfs, local_static
    project_path: str
    output_dir: str = "dist"
    build_command: str = ""
    env_vars: dict = field(default_factory=dict)
    # API keys read from env, never hardcoded
    api_key_env: str = ""
    api_token_env: str = ""
    # IPFS-specific
    ipfs_api_url: str = "http://localhost:5001/api/v0"
    pin_service_url: str = ""
    pin_service_token_env: str = ""


@dataclass
class AdapterResult:
    success: bool
    url: str
    target: str
    content_hash: str
    error: str = ""
    deployment_id: str = ""
    metadata: dict = field(default_factory=dict)


class BaseDeploymentAdapter:
    """Base class for all deployment adapters."""

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger, deployment_protocol: DeploymentReceiptProtocol):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.deployment_protocol = deployment_protocol

    def _compute_content_hash(self, path: str) -> str:
        """Compute SHA-256 hash of all files in a directory."""
        hasher = hashlib.sha256()
        if os.path.isfile(path):
            with open(path, "rb") as f:
                hasher.update(f.read())
        else:
            for root, dirs, files in os.walk(path):
                dirs.sort()
                files.sort()
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if not os.path.isfile(fpath):
                        continue
                    rel = os.path.relpath(fpath, path)
                    hasher.update(rel.encode())
                    with open(fpath, "rb") as f:
                        hasher.update(f.read())
        return f"sha256:{hasher.hexdigest()[:16]}"

    def _run_build(self, config: DeploymentConfig) -> tuple[bool, str]:
        """Run build command if specified. Returns (success, output_path)."""
        output_path = os.path.join(config.project_path, config.output_dir)
        if config.build_command:
            try:
                result = subprocess.run(
                    config.build_command,
                    shell=True,
                    cwd=config.project_path,
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    return False, ""
                return True, output_path
            except Exception:
                return False, ""
        return True, output_path

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> AdapterResult:
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════
# Protocol 213: Vercel Deployment Adapter
# ═══════════════════════════════════════════════════════════════════

class VercelAdapter(BaseDeploymentAdapter):
    """
    Deploys to Vercel via CLI or API.

    Requires VERCEL_TOKEN env var.
    Falls back to honest failure if token is missing or CLI unavailable.
    """

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> AdapterResult:
        token = os.environ.get(config.api_token_env or "VERCEL_TOKEN", "")
        if not token:
            return AdapterResult(
                success=False, url="", target="vercel",
                content_hash="", error=f"No token in env var {config.api_token_env or 'VERCEL_TOKEN'}",
            )

        build_ok, output_path = self._run_build(config)
        if not build_ok:
            return AdapterResult(
                success=False, url="", target="vercel",
                content_hash="", error="Build failed",
            )

        content_hash = self._compute_content_hash(output_path)

        try:
            # Try Vercel CLI
            result = subprocess.run(
                f"vercel --token {token} --yes --prod",
                shell=True,
                cwd=config.project_path,
                capture_output=True,
                timeout=180,
            )
            if result.returncode == 0:
                url = result.stdout.decode().strip().split("\n")[-1].strip()
                if not url.startswith("http"):
                    url = f"https://{url}"
                return AdapterResult(
                    success=True, url=url, target="vercel",
                    content_hash=content_hash,
                    metadata={"method": "cli"},
                )
            else:
                return AdapterResult(
                    success=False, url="", target="vercel",
                    content_hash=content_hash,
                    error=f"Vercel CLI failed: {result.stderr.decode()[:200]}",
                )
        except FileNotFoundError:
            return AdapterResult(
                success=False, url="", target="vercel",
                content_hash=content_hash,
                error="Vercel CLI not installed",
            )
        except Exception as e:
            return AdapterResult(
                success=False, url="", target="vercel",
                content_hash=content_hash,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════════════
# Protocol 214: Netlify Deployment Adapter
# ═══════════════════════════════════════════════════════════════════

class NetlifyAdapter(BaseDeploymentAdapter):
    """
    Deploys to Netlify via CLI or API.

    Requires NETLIFY_AUTH_TOKEN env var.
    Falls back to honest failure if token is missing or CLI unavailable.
    """

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> AdapterResult:
        token = os.environ.get(config.api_token_env or "NETLIFY_AUTH_TOKEN", "")
        if not token:
            return AdapterResult(
                success=False, url="", target="netlify",
                content_hash="", error=f"No token in env var {config.api_token_env or 'NETLIFY_AUTH_TOKEN'}",
            )

        build_ok, output_path = self._run_build(config)
        if not build_ok:
            return AdapterResult(
                success=False, url="", target="netlify",
                content_hash="", error="Build failed",
            )

        content_hash = self._compute_content_hash(output_path)

        try:
            result = subprocess.run(
                f"netlify deploy --prod --auth {token} --dir {config.output_dir}",
                shell=True,
                cwd=config.project_path,
                capture_output=True,
                timeout=180,
            )
            if result.returncode == 0:
                output = result.stdout.decode()
                # Parse URL from output
                url = ""
                for line in output.split("\n"):
                    if "https://" in line and "netlify.app" in line:
                        parts = line.split()
                        for p in parts:
                            if p.startswith("https://"):
                                url = p
                                break
                if url:
                    return AdapterResult(
                        success=True, url=url, target="netlify",
                        content_hash=content_hash,
                        metadata={"method": "cli"},
                    )
                return AdapterResult(
                    success=True, url="(url in CLI output)", target="netlify",
                    content_hash=content_hash,
                    metadata={"method": "cli", "raw_output": output[:500]},
                )
            else:
                return AdapterResult(
                    success=False, url="", target="netlify",
                    content_hash=content_hash,
                    error=f"Netlify CLI failed: {result.stderr.decode()[:200]}",
                )
        except FileNotFoundError:
            return AdapterResult(
                success=False, url="", target="netlify",
                content_hash=content_hash,
                error="Netlify CLI not installed",
            )
        except Exception as e:
            return AdapterResult(
                success=False, url="", target="netlify",
                content_hash=content_hash,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════════════
# Protocol 215: IPFS Pinning Adapter
# ═══════════════════════════════════════════════════════════════════

class IPFSAdapter(BaseDeploymentAdapter):
    """
    Pins content to IPFS via local node or pinning service.

    Requires either:
      - Local IPFS node at ipfs_api_url (default localhost:5001)
      - Pinning service token in env var pin_service_token_env
    """

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> AdapterResult:
        build_ok, output_path = self._run_build(config)
        if not build_ok:
            return AdapterResult(
                success=False, url="", target="ipfs",
                content_hash="", error="Build failed",
            )

        content_hash = self._compute_content_hash(output_path)

        # Try local IPFS node first
        try:
            # Add to IPFS
            result = subprocess.run(
                ["ipfs", "add", "-r", "--quiet", output_path],
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                lines = result.stdout.decode().strip().split("\n")
                root_cid = lines[-1].strip() if lines else ""
                if root_cid:
                    # Try pinning
                    subprocess.run(
                        ["ipfs", "pin", "add", root_cid],
                        capture_output=True,
                        timeout=60,
                    )
                    url = f"ipfs://{root_cid}"
                    gateway_url = f"https://ipfs.io/ipfs/{root_cid}"

                    # Try pinning service if configured
                    pin_token = os.environ.get(config.pin_service_token_env, "")
                    if pin_token and config.pin_service_url:
                        self._pin_to_service(root_cid, config.pin_service_url, pin_token)

                    return AdapterResult(
                        success=True, url=gateway_url, target="ipfs",
                        content_hash=content_hash,
                        metadata={"cid": root_cid, "ipfs_url": url, "method": "local_node"},
                    )
            return AdapterResult(
                success=False, url="", target="ipfs",
                content_hash=content_hash,
                error="IPFS add failed — is ipfs daemon running?",
            )
        except FileNotFoundError:
            return AdapterResult(
                success=False, url="", target="ipfs",
                content_hash=content_hash,
                error="IPFS CLI not installed",
            )
        except Exception as e:
            return AdapterResult(
                success=False, url="", target="ipfs",
                content_hash=content_hash,
                error=str(e),
            )

    def _pin_to_service(self, cid: str, service_url: str, token: str) -> bool:
        try:
            payload = json.dumps({"cid": cid}).encode()
            req = urllib.request.Request(
                f"{service_url}/pins",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════
# Protocol 216: Local Static Export Adapter
# ═══════════════════════════════════════════════════════════════════

class LocalStaticAdapter(BaseDeploymentAdapter):
    """
    Exports build output to a local directory with index.html.

    This is the fallback adapter — always succeeds if the source files exist.
    Produces a file:// URL pointing to the exported content.
    """

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> AdapterResult:
        build_ok, output_path = self._run_build(config)
        if not build_ok:
            return AdapterResult(
                success=False, url="", target="local_static",
                content_hash="", error="Build failed",
            )

        if not os.path.isdir(output_path):
            return AdapterResult(
                success=False, url="", target="local_static",
                content_hash="", error=f"Output directory not found: {output_path}",
            )

        content_hash = self._compute_content_hash(output_path)

        # Copy to a stable export location
        export_dir = os.path.join(
            tempfile.gettempdir(),
            f"oracle_export_{artifact_id}_{int(time.time())}",
        )
        shutil.copytree(output_path, export_dir)

        index_path = os.path.join(export_dir, "index.html")
        if not os.path.exists(index_path):
            # Create a minimal index.html if none exists
            with open(index_path, "w") as f:
                f.write(f"<!-- Oracle Local Export -->\n<h1>Artifact {artifact_id}</h1>\n")

        url = f"file://{index_path}"

        return AdapterResult(
            success=True, url=url, target="local_static",
            content_hash=content_hash,
            metadata={
                "export_dir": export_dir,
                "file_count": sum(len(files) for _, _, files in os.walk(export_dir)),
            },
        )


# ═══════════════════════════════════════════════════════════════════
# Unified Deployment Manager
# ═══════════════════════════════════════════════════════════════════

class DeploymentManager:
    """
    Routes deployments to the correct adapter based on target.
    Records every deployment via DeploymentReceiptProtocol.
    """

    ADAPTERS = {
        "vercel": VercelAdapter,
        "netlify": NetlifyAdapter,
        "ipfs": IPFSAdapter,
        "local_static": LocalStaticAdapter,
    }

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.deployment_protocol = DeploymentReceiptProtocol(db, receipt_ledger)
        self._adapters: dict[str, BaseDeploymentAdapter] = {}

    def _get_adapter(self, target: str) -> Optional[BaseDeploymentAdapter]:
        if target not in self._adapters:
            cls = self.ADAPTERS.get(target)
            if not cls:
                return None
            self._adapters[target] = cls(self.db, self.receipt_ledger, self.deployment_protocol)
        return self._adapters[target]

    def deploy(self, artifact_id: str, config: DeploymentConfig) -> dict:
        adapter = self._get_adapter(config.target)
        if not adapter:
            return {
                "success": False,
                "error": f"Unknown target: {config.target}",
                "url": "",
            }

        result = adapter.deploy(artifact_id, config)

        # Record via deployment receipt protocol
        receipt = self.deployment_protocol.record_deployment(
            artifact_id=artifact_id,
            target=config.target,
            url=result.url,
            content_hash=result.content_hash,
            health_check_passed=result.success,
        )

        return {
            "success": result.success,
            "url": result.url,
            "target": result.target,
            "content_hash": result.content_hash,
            "error": result.error,
            "deployment_id": receipt.deployment_id,
            "receipt_hash": receipt.receipt_hash,
            "metadata": result.metadata,
        }

    def list_targets(self) -> list:
        return [
            {"target": t, "adapter": cls.__name__}
            for t, cls in self.ADAPTERS.items()
        ]
