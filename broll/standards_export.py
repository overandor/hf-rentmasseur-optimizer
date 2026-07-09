"""
Standards Export — Schema.org VideoObject + C2PA Content Provenance.

Turns VideoLake/MCRV/BMMA artifacts into standards-compliant metadata
that external systems can parse, index, and trust.

Schema.org VideoObject: https://schema.org/VideoObject
    Machine-readable video metadata: caption, transcript, contentUrl,
    duration, thumbnailUrl, uploadDate, description, creator, license.

C2PA (Coalition for Content Provenance and Authenticity):
    Content provenance assertions: manifest, claim, assertion,
    digital signature, ingredient list, action history.

Usage:
    from broll.standards_export import StandardsExporter
    exporter = StandardsExporter()

    # Schema.org VideoObject JSON-LD
    video_object = exporter.to_schema_org_videoobject(
        question="What does the Hubble tension reveal?",
        duration_seconds=180,
        transcript="...",
        claims=[...],
        evidence=[...],
        rights_label="safe",
        creator="Membra EvidenceOS",
        manifest_hash="sha256:...",
        content_url="https://example.com/video.mp4",
    )

    # C2PA manifest
    c2pa_manifest = exporter.to_c2pa_manifest(
        title="Hubble Tension Investigation",
        creator="Membra EvidenceOS",
        manifest_hash="sha256:...",
        claims=[...],
        evidence=[...],
        rights_label="safe",
        ingredients=[...],
        actions=[...],
    )
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class C2PAAssertion:
    """A single C2PA provenance assertion."""
    label: str
    value: str
    assertion_type: str = "text"  # text, url, hash, signature

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "value": self.value,
            "type": self.assertion_type,
        }


@dataclass
class C2PAIngredient:
    """A C2PA ingredient — an input that contributed to the output."""
    title: str
    document_id: str
    relationship: str = "componentOf"  # componentOf, basedOn, derivedFrom
    hash: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "document_id": self.document_id,
            "relationship": self.relationship,
            "hash": self.hash,
        }


@dataclass
class C2PAAction:
    """A C2PA action — a transformation applied to produce the output."""
    action: str  # created, edited, rendered, compiled, filtered
    when: float = 0.0
    actor: str = ""
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "when": self.when,
            "actor": self.actor,
            "parameters": self.parameters,
        }


@dataclass
class C2PAClaim:
    """A C2PA claim — a signed statement about the content's provenance."""
    claim_id: str
    assertions: list[C2PAAssertion] = field(default_factory=list)
    ingredients: list[C2PAIngredient] = field(default_factory=list)
    actions: list[C2PAAction] = field(default_factory=list)
    signature_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "assertions": [a.to_dict() for a in self.assertions],
            "ingredients": [i.to_dict() for i in self.ingredients],
            "actions": [a.to_dict() for a in self.actions],
            "signature_hash": self.signature_hash,
        }


@dataclass
class C2PAManifest:
    """A C2PA manifest — the top-level provenance container."""
    manifest_id: str
    title: str
    creator: str = ""
    created_at: float = 0.0
    claim: Optional[C2PAClaim] = None
    claim_hash: str = ""
    manifest_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "title": self.title,
            "creator": self.creator,
            "created_at": self.created_at,
            "claim": self.claim.to_dict() if self.claim else None,
            "claim_hash": self.claim_hash,
            "manifest_hash": self.manifest_hash,
            "schema": "c2pa_manifest_v1",
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def compute_hash(self) -> str:
        data = json.dumps({
            "manifest_id": self.manifest_id,
            "title": self.title,
            "creator": self.creator,
            "claim_hash": self.claim_hash,
        }, sort_keys=True)
        self.manifest_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.manifest_hash


class StandardsExporter:
    """
    Exports VideoLake/MCRV/BMMA artifacts as standards-compliant metadata.

    Schema.org VideoObject — for search engines, platforms, and machine indexing.
    C2PA Manifest — for content provenance and authenticity assertions.
    """

    def to_schema_org_videoobject(
        self,
        question: str,
        duration_seconds: float = 0.0,
        transcript: str = "",
        claims: list[dict] | None = None,
        evidence: list[dict] | None = None,
        rights_label: str = "unknown",
        creator: str = "Membra EvidenceOS",
        manifest_hash: str = "",
        content_url: str = "",
        thumbnail_url: str = "",
        upload_date: str = "",
        confidence_score: float = 0.0,
        machine_buyability: float = 0.0,
        bmma_id: str = "",
        grade_claimed: float = 0.0,
        revenue_sources: list[str] | None = None,
    ) -> dict:
        """
        Generate a Schema.org VideoObject JSON-LD document.

        Reference: https://schema.org/VideoObject

        Extends the standard VideoObject with Membra-specific properties:
        - evidenceBacking: claims and evidence behind the video
        - rightsLabel: safety classification of rights
        - machineBuyability: how safely a machine can parse/license
        - bondedGrade: sealed grade bond claim
        - bmmaId: Bonded Machine Media Asset identifier
        - revenueSources: tracked revenue streams
        """
        claims = claims or []
        evidence = evidence or []
        revenue_sources = revenue_sources or []

        if not upload_date:
            upload_date = time.strftime("%Y-%m-%d", time.gmtime())

        description = self._build_description(question, claims, evidence, rights_label)

        video_object = {
            "@context": {
                "@vocab": "https://schema.org/",
                "prov": "https://www.w3.org/ns/prov#",
                "membra": "https://membra.local/vocab#",
            },
            "@type": "VideoObject",
            "name": question,
            "description": description,
            "uploadDate": upload_date,
            "creator": {
                "@type": "Organization",
                "name": creator,
            },
            "duration": self._format_duration(duration_seconds),
            "transcript": transcript[:5000] if transcript else "",
            "contentUrl": content_url,
            "thumbnailUrl": thumbnail_url,
            "license": self._rights_to_license_url(rights_label),
            "isFamilyFriendly": True,
            "genre": "Educational",
            "learningResourceType": "Investigation",
            "educationalUse": "Research",
            # Membra extensions
            "membra:evidenceBacking": {
                "claims_count": len(claims),
                "evidence_count": len(evidence),
                "claims": claims[:20],
                "evidence": evidence[:20],
            },
            "membra:rightsLabel": rights_label,
            "membra:confidenceScore": round(confidence_score, 3),
            "membra:machineBuyability": round(machine_buyability, 3),
            "membra:manifestHash": manifest_hash,
            "membra:bmmaId": bmma_id,
            "membra:bondedGrade": grade_claimed,
            "membra:revenueSources": revenue_sources,
            # Provenance
            "prov:wasGeneratedBy": {
                "@type": "prov:Activity",
                "prov:startedAtTime": upload_date,
            },
        }

        return video_object

    def to_c2pa_manifest(
        self,
        title: str,
        creator: str = "Membra EvidenceOS",
        manifest_hash: str = "",
        claims: list[dict] | None = None,
        evidence: list[dict] | None = None,
        rights_label: str = "unknown",
        ingredients: list[dict] | None = None,
        actions: list[dict] | None = None,
        confidence_score: float = 0.0,
        bmma_id: str = "",
        grade_claimed: float = 0.0,
    ) -> C2PAManifest:
        """
        Generate a C2PA-style content provenance manifest.

        The manifest contains:
        - Assertions about the content's nature (evidence-backed, rights-safe)
        - Ingredients (papers, data, visual sources that contributed)
        - Actions (investigation, compilation, rendering)
        - A signed claim binding the assertions

        This is a C2PA-compatible structure, not a full C2PA SDK implementation.
        It follows the C2PA manifest data model but uses SHA-256 instead of
        full X.509/JWS signing.
        """
        claims = claims or []
        evidence = evidence or []
        ingredients = ingredients or []
        actions = actions or []

        manifest_id = f"c2pa_{hashlib.sha256(f'{title}{time.time()}'.encode()).hexdigest()[:12]}"
        claim_id = f"claim_{hashlib.sha256(f'{manifest_id}{time.time()}'.encode()).hexdigest()[:12]}"

        # Build assertions
        assertions = [
            C2PAAssertion("c2pa.actions", json.dumps([
                {"action": a.get("action", "unknown"), "when": a.get("when", 0)}
                for a in actions
            ]), "text"),
            C2PAAssertion("membra.evidence_backed", "true", "text"),
            C2PAAssertion("membra.claims_count", str(len(claims)), "text"),
            C2PAAssertion("membra.evidence_count", str(len(evidence)), "text"),
            C2PAAssertion("membra.rights_label", rights_label, "text"),
            C2PAAssertion("membra.confidence_score", str(round(confidence_score, 3)), "text"),
            C2PAAssertion("membra.manifest_hash", manifest_hash, "hash"),
        ]

        if bmma_id:
            assertions.append(C2PAAssertion("membra.bmma_id", bmma_id, "text"))
        if grade_claimed > 0:
            assertions.append(C2PAAssertion("membra.bonded_grade", str(grade_claimed), "text"))

        # Build ingredients from evidence
        c2pa_ingredients = []
        for ev in evidence[:20]:
            c2pa_ingredients.append(C2PAIngredient(
                title=ev.get("title", ev.get("paper_id", "unknown")),
                document_id=ev.get("paper_id", ev.get("id", "")),
                relationship="basedOn",
                hash=ev.get("hash", ""),
            ))
        for ing in ingredients:
            c2pa_ingredients.append(C2PAIngredient(
                title=ing.get("title", ""),
                document_id=ing.get("id", ""),
                relationship=ing.get("relationship", "componentOf"),
                hash=ing.get("hash", ""),
            ))

        # Build actions
        c2pa_actions = [
            C2PAAction(
                action="created",
                when=time.time(),
                actor=creator,
                parameters={"tool": "Membra EvidenceOS"},
            ),
            C2PAAction(
                action="compiled",
                when=time.time(),
                actor=creator,
                parameters={"type": "investigation_to_media"},
            ),
        ]
        for a in actions:
            c2pa_actions.append(C2PAAction(
                action=a.get("action", "edited"),
                when=a.get("when", time.time()),
                actor=a.get("actor", creator),
                parameters=a.get("parameters", {}),
            ))

        claim = C2PAClaim(
            claim_id=claim_id,
            assertions=assertions,
            ingredients=c2pa_ingredients,
            actions=c2pa_actions,
        )

        # Sign the claim
        claim_data = json.dumps({
            "claim_id": claim_id,
            "assertions": [a.to_dict() for a in assertions],
            "ingredients_count": len(c2pa_ingredients),
            "actions_count": len(c2pa_actions),
        }, sort_keys=True)
        claim.signature_hash = f"sha256:{hashlib.sha256(claim_data.encode()).hexdigest()[:16]}"
        claim_data_full = json.dumps({"claim_id": claim_id, "signature": claim.signature_hash}, sort_keys=True)
        claim_hash = f"sha256:{hashlib.sha256(claim_data_full.encode()).hexdigest()[:16]}"

        manifest = C2PAManifest(
            manifest_id=manifest_id,
            title=title,
            creator=creator,
            created_at=time.time(),
            claim=claim,
            claim_hash=claim_hash,
        )
        manifest.compute_hash()

        return manifest

    def to_ro_crate(
        self,
        question: str,
        manifest_hash: str = "",
        files: list[dict] | None = None,
        creator: str = "Membra EvidenceOS",
    ) -> dict:
        """
        Generate an RO-Crate 1.1 metadata JSON-LD document.

        Reference: https://w3id.org/ro/crate/1.1
        """
        files = files or []

        graph = [
            {
                "@type": "CreativeWork",
                "@id": "ro-crate-metadata.json",
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                "about": {"@id": "./"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": question,
                "description": f"Evidence-backed research media asset: {question}",
                "author": {"@type": "Organization", "name": creator},
                "hasPart": [{"@id": f.get("name", f)} for f in files],
                "membra:manifestHash": manifest_hash,
            },
        ]

        for f in files:
            graph.append({
                "@id": f.get("name", ""),
                "@type": f.get("type", "File"),
                "name": f.get("name", ""),
                "encodingFormat": f.get("format", "application/json"),
                "contentSize": f.get("size", 0),
            })

        return {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": graph,
        }

    def _build_description(
        self,
        question: str,
        claims: list[dict],
        evidence: list[dict],
        rights_label: str,
    ) -> str:
        """Build a human-readable description from the investigation."""
        parts = [f"Investigation: {question}"]
        if claims:
            parts.append(f"Claims: {len(claims)}")
        if evidence:
            parts.append(f"Evidence sources: {len(evidence)}")
        parts.append(f"Rights status: {rights_label}")
        return " | ".join(parts)

    def _format_duration(self, seconds: float) -> str:
        """Format seconds as ISO 8601 duration."""
        if seconds <= 0:
            return "PT0S"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"PT{mins}M{secs}S"

    def _rights_to_license_url(self, rights_label: str) -> str:
        """Map rights label to a Schema.org license URL."""
        mapping = {
            "safe": "https://creativecommons.org/licenses/by/4.0/",
            "fair_use": "https://en.wikipedia.org/wiki/Fair_use",
            "restricted": "https://www.gnu.org/licenses/gpl-3.0.html",
            "unknown": "https://schema.org/undefined",
        }
        return mapping.get(rights_label, "https://schema.org/undefined")
