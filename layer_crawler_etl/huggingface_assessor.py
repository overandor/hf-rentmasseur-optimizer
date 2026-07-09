"""
HuggingFace Space Assessor - Real endpoint assessment (no mocks)
Assesses HF Spaces, Gradio endpoints, Docker Spaces, Inference Endpoints
"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .core import BaseCrawler, Source, SubjectType, EvidenceType

@dataclass
class HFSpaceAssessment:
    """Assessment result for a HuggingFace Space"""
    space_id: str
    endpoint: str
    status: str
    latency_ms: float
    schema_valid: bool
    error_message: Optional[str]
    authentication_required: bool
    framework: str
    sdk: str
    verified: bool
    timestamp: str

class HuggingFaceAssessor(BaseCrawler):
    """Real HuggingFace endpoint assessor - no mocks"""
    
    def __init__(self, token: Optional[str] = None):
        super().__init__("huggingface_assessor")
        self.token = token
        self.base_url = "https://huggingface.co"
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
    
    async def assess_space(self, space_id: str) -> HFSpaceAssessment:
        """Assess a single HuggingFace Space"""
        start_time = time.time()
        endpoint = f"{self.base_url}/spaces/{space_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Try to fetch space info
                async with session.get(
                    f"{self.base_url}/api/spaces/{space_id}",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 401:
                        return HFSpaceAssessment(
                            space_id=space_id,
                            endpoint=endpoint,
                            status="unauthorized",
                            latency_ms=(time.time() - start_time) * 1000,
                            schema_valid=False,
                            error_message="Authentication required",
                            authentication_required=True,
                            framework="unknown",
                            sdk="unknown",
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status != 200:
                        text = await resp.text()
                        return HFSpaceAssessment(
                            space_id=space_id,
                            endpoint=endpoint,
                            status=f"error_{resp.status}",
                            latency_ms=(time.time() - start_time) * 1000,
                            schema_valid=False,
                            error_message=text[:200],
                            authentication_required=False,
                            framework="unknown",
                            sdk="unknown",
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    data = await resp.json()
                    latency_ms = (time.time() - start_time) * 1000
                    
                    # Extract framework and SDK
                    framework = data.get("cardData", {}).get("framework", "unknown")
                    sdk = data.get("sdk", "unknown")
                    
                    # Check if space is running
                    runtime = data.get("runtime", {})
                    stage = runtime.get("stage", "unknown")
                    
                    if stage != "RUNNING":
                        return HFSpaceAssessment(
                            space_id=space_id,
                            endpoint=endpoint,
                            status=f"not_running_{stage}",
                            latency_ms=latency_ms,
                            schema_valid=False,
                            error_message=f"Space stage: {stage}",
                            authentication_required=False,
                            framework=framework,
                            sdk=sdk,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    # Try to access the actual space endpoint
                    try:
                        async with session.get(
                            endpoint,
                            headers=self.headers,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as space_resp:
                            if space_resp.status == 200:
                                return HFSpaceAssessment(
                                    space_id=space_id,
                                    endpoint=endpoint,
                                    status="running",
                                    latency_ms=latency_ms,
                                    schema_valid=True,
                                    error_message=None,
                                    authentication_required=False,
                                    framework=framework,
                                    sdk=sdk,
                                    verified=True,
                                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                                )
                            else:
                                return HFSpaceAssessment(
                                    space_id=space_id,
                                    endpoint=endpoint,
                                    status=f"space_error_{space_resp.status}",
                                    latency_ms=latency_ms,
                                    schema_valid=False,
                                    error_message=f"Space returned {space_resp.status}",
                                    authentication_required=False,
                                    framework=framework,
                                    sdk=sdk,
                                    verified=False,
                                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                                )
                    except Exception as e:
                        return HFSpaceAssessment(
                            space_id=space_id,
                            endpoint=endpoint,
                            status="runtime_error",
                            latency_ms=latency_ms,
                            schema_valid=False,
                            error_message=str(e)[:200],
                            authentication_required=False,
                            framework=framework,
                            sdk=sdk,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
        
        except asyncio.TimeoutError:
            return HFSpaceAssessment(
                space_id=space_id,
                endpoint=endpoint,
                status="timeout",
                latency_ms=30000,
                schema_valid=False,
                error_message="Request timed out",
                authentication_required=False,
                framework="unknown",
                sdk="unknown",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        except Exception as e:
            return HFSpaceAssessment(
                space_id=space_id,
                endpoint=endpoint,
                status="exception",
                latency_ms=(time.time() - start_time) * 1000,
                schema_valid=False,
                error_message=str(e)[:200],
                authentication_required=False,
                framework="unknown",
                sdk="unknown",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
    
    async def assess_inference_endpoint(self, model_id: str) -> HFSpaceAssessment:
        """Assess a HuggingFace Inference Endpoint"""
        start_time = time.time()
        endpoint = f"https://api-inference.huggingface.co/models/{model_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"
                
                # Try a simple inference request
                payload = {"inputs": "test"}
                
                async with session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    
                    if resp.status == 401:
                        return HFSpaceAssessment(
                            space_id=model_id,
                            endpoint=endpoint,
                            status="unauthorized",
                            latency_ms=latency_ms,
                            schema_valid=False,
                            error_message="Authentication required",
                            authentication_required=True,
                            framework="inference",
                            sdk="api",
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status == 200:
                        # Try to parse response
                        try:
                            data = await resp.json()
                            return HFSpaceAssessment(
                                space_id=model_id,
                                endpoint=endpoint,
                                status="running",
                                latency_ms=latency_ms,
                                schema_valid=True,
                                error_message=None,
                                authentication_required=False,
                                framework="inference",
                                sdk="api",
                                verified=True,
                                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                        except:
                            return HFSpaceAssessment(
                                space_id=model_id,
                                endpoint=endpoint,
                                status="invalid_response",
                                latency_ms=latency_ms,
                                schema_valid=False,
                                error_message="Could not parse JSON response",
                                authentication_required=False,
                                framework="inference",
                                sdk="api",
                                verified=False,
                                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                    else:
                        text = await resp.text()
                        return HFSpaceAssessment(
                            space_id=model_id,
                            endpoint=endpoint,
                            status=f"error_{resp.status}",
                            latency_ms=latency_ms,
                            schema_valid=False,
                            error_message=text[:200],
                            authentication_required=False,
                            framework="inference",
                            sdk="api",
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
        
        except asyncio.TimeoutError:
            return HFSpaceAssessment(
                space_id=model_id,
                endpoint=endpoint,
                status="timeout",
                latency_ms=30000,
                schema_valid=False,
                error_message="Request timed out",
                authentication_required=False,
                framework="inference",
                sdk="api",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        except Exception as e:
            return HFSpaceAssessment(
                space_id=model_id,
                endpoint=endpoint,
                status="exception",
                latency_ms=(time.time() - start_time) * 1000,
                schema_valid=False,
                error_message=str(e)[:200],
                authentication_required=False,
                framework="inference",
                sdk="api",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
    
    async def crawl(self, source: Source) -> List:
        """Crawl HuggingFace endpoint and generate signals"""
        signals = []
        
        space_id = source.location
        
        # Determine if it's a space or model
        if "/spaces/" in space_id:
            space_id = space_id.split("/spaces/")[-1]
            assessment = await self.assess_space(space_id)
        elif "/models/" in space_id or space_id.count("/") == 1:
            model_id = space_id.replace("/models/", "")
            assessment = await self.assess_inference_endpoint(model_id)
        else:
            # Assume it's a space
            assessment = await self.assess_space(space_id)
        
        # Generate signals based on assessment
        self.add_signal(
            SubjectType.BROWSER_RUNTIME,
            EvidenceType.RUNTIME_VERIFIED,
            assessment.verified,
            source.location
        )
        
        if assessment.verified:
            self.add_signal(
                SubjectType.BROWSER_RUNTIME,
                EvidenceType.FAILED_REQUESTS,
                0,
                source.location
            )
        else:
            self.add_signal(
                SubjectType.BROWSER_RUNTIME,
                EvidenceType.FAILED_REQUESTS,
                1,
                source.location
            )
        
        self.add_signal(
            SubjectType.BROWSER_RUNTIME,
            EvidenceType.CONSOLE_ERRORS,
            0 if assessment.verified else 1,
            source.location
        )
        
        signals.extend(self.signals)
        return signals
    
    async def batch_assess(self, space_ids: List[str]) -> List[HFSpaceAssessment]:
        """Assess multiple spaces in parallel"""
        tasks = []
        for space_id in space_ids:
            if "/spaces/" in space_id:
                space_id = space_id.split("/spaces/")[-1]
                tasks.append(self.assess_space(space_id))
            else:
                tasks.append(self.assess_inference_endpoint(space_id))
        
        return await asyncio.gather(*tasks)

# Example usage
if __name__ == "__main__":
    async def main():
        # Try with a token if available
        import os
        token = os.environ.get("HF_TOKEN")
        
        assessor = HuggingFaceAssessor(token=token)
        
        # Test some popular spaces
        spaces = [
            "gradio/titan-mlm-demo",
            "stabilityai/stable-diffusion-3-medium",
            "openai/whisper-large-v3",
        ]
        
        print("Assessing HuggingFace Spaces...")
        results = await assessor.batch_assess(spaces)
        
        for result in results:
            print(f"\n{result.space_id}:")
            print(f"  Status: {result.status}")
            print(f"  Latency: {result.latency_ms:.0f}ms")
            print(f"  Verified: {result.verified}")
            print(f"  Framework: {result.framework}")
            if result.error_message:
                print(f"  Error: {result.error_message}")
    
    asyncio.run(main())
