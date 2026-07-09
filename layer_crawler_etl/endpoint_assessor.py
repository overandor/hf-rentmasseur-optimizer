"""
General Endpoint Assessor - Real endpoint assessment (no mocks)
Assesses REST APIs, GraphQL APIs, FastAPI, Express, Flask, cloud endpoints
"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from .core import BaseCrawler, Source, SubjectType, EvidenceType

class EndpointType(Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    FASTAPI = "fastapi"
    EXPRESS = "express"
    FLASK = "flask"
    CLOUD_RUN = "cloud_run"
    LAMBDA = "lambda"
    AZURE_FUNCTION = "azure_function"
    CLOUD_FUNCTIONS = "cloud_functions"
    VERCEL = "vercel"
    NETLIFY = "netlify"
    UNKNOWN = "unknown"

@dataclass
class EndpointAssessment:
    """Assessment result for an endpoint"""
    url: str
    endpoint_type: EndpointType
    status: str
    latency_ms: float
    http_status: int
    schema_valid: bool
    error_message: Optional[str]
    authentication_required: bool
    authentication_type: Optional[str]
    response_size_bytes: int
    content_type: Optional[str]
    verified: bool
    timestamp: str

class EndpointAssessor(BaseCrawler):
    """Real endpoint assessor - no mocks"""
    
    def __init__(self, auth_token: Optional[str] = None, timeout: int = 30):
        super().__init__("endpoint_assessor")
        self.auth_token = auth_token
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LayerCrawler/1.0)"
        }
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
    
    def detect_endpoint_type(self, url: str, response_headers: Dict[str, str]) -> EndpointType:
        """Detect endpoint type from URL and headers"""
        url_lower = url.lower()
        
        # Check URL patterns
        if "cloudfunctions.net" in url_lower:
            return EndpointType.CLOUD_FUNCTIONS
        elif "cloud.run" in url_lower:
            return EndpointType.CLOUD_RUN
        elif "vercel.app" in url_lower:
            return EndpointType.VERCEL
        elif "netlify.app" in url_lower:
            return EndpointType.NETLIFY
        elif "azurewebsites.net" in url_lower:
            return EndpointType.AZURE_FUNCTION
        elif "amazonaws.com" in url_lower and "lambda" in url_lower:
            return EndpointType.LAMBDA
        
        # Check headers
        server = response_headers.get("Server", "").lower()
        x_powered_by = response_headers.get("X-Powered-By", "").lower()
        
        if "fastapi" in x_powered_by or "uvicorn" in server:
            return EndpointType.FASTAPI
        elif "express" in x_powered_by:
            return EndpointType.EXPRESS
        elif "flask" in x_powered_by:
            return EndpointType.FLASK
        
        # Check for GraphQL
        if "/graphql" in url_lower:
            return EndpointType.GRAPHQL
        
        return EndpointType.REST
    
    async def assess_rest_endpoint(self, url: str) -> EndpointAssessment:
        """Assess a REST endpoint"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    content_type = resp.headers.get("Content-Type", "")
                    response_size = 0
                    
                    try:
                        content = await resp.read()
                        response_size = len(content)
                    except:
                        pass
                    
                    # Detect endpoint type
                    endpoint_type = self.detect_endpoint_type(url, dict(resp.headers))
                    
                    if resp.status == 401:
                        auth_type = resp.headers.get("WWW-Authenticate", "Bearer")
                        return EndpointAssessment(
                            url=url,
                            endpoint_type=endpoint_type,
                            status="unauthorized",
                            latency_ms=latency_ms,
                            http_status=resp.status,
                            schema_valid=False,
                            error_message="Authentication required",
                            authentication_required=True,
                            authentication_type=auth_type,
                            response_size_bytes=response_size,
                            content_type=content_type,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status == 403:
                        return EndpointAssessment(
                            url=url,
                            endpoint_type=endpoint_type,
                            status="forbidden",
                            latency_ms=latency_ms,
                            http_status=resp.status,
                            schema_valid=False,
                            error_message="Access forbidden",
                            authentication_required=True,
                            authentication_type=None,
                            response_size_bytes=response_size,
                            content_type=content_type,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status >= 500:
                        return EndpointAssessment(
                            url=url,
                            endpoint_type=endpoint_type,
                            status=f"server_error_{resp.status}",
                            latency_ms=latency_ms,
                            http_status=resp.status,
                            schema_valid=False,
                            error_message=f"Server error: {resp.status}",
                            authentication_required=False,
                            authentication_type=None,
                            response_size_bytes=response_size,
                            content_type=content_type,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status >= 400:
                        return EndpointAssessment(
                            url=url,
                            endpoint_type=endpoint_type,
                            status=f"client_error_{resp.status}",
                            latency_ms=latency_ms,
                            http_status=resp.status,
                            schema_valid=False,
                            error_message=f"Client error: {resp.status}",
                            authentication_required=False,
                            authentication_type=None,
                            response_size_bytes=response_size,
                            content_type=content_type,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    # Status 200-299
                    schema_valid = True
                    
                    # Try to validate JSON schema
                    if "application/json" in content_type:
                        try:
                            await resp.json()
                        except:
                            schema_valid = False
                    
                    return EndpointAssessment(
                        url=url,
                        endpoint_type=endpoint_type,
                        status="success",
                        latency_ms=latency_ms,
                        http_status=resp.status,
                        schema_valid=schema_valid,
                        error_message=None,
                        authentication_required=False,
                        authentication_type=None,
                        response_size_bytes=response_size,
                        content_type=content_type,
                        verified=True,
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
        
        except asyncio.TimeoutError:
            return EndpointAssessment(
                url=url,
                endpoint_type=EndpointType.UNKNOWN,
                status="timeout",
                latency_ms=self.timeout * 1000,
                http_status=0,
                schema_valid=False,
                error_message="Request timed out",
                authentication_required=False,
                authentication_type=None,
                response_size_bytes=0,
                content_type=None,
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        except aiohttp.ClientError as e:
            return EndpointAssessment(
                url=url,
                endpoint_type=EndpointType.UNKNOWN,
                status="client_error",
                latency_ms=(time.time() - start_time) * 1000,
                http_status=0,
                schema_valid=False,
                error_message=str(e)[:200],
                authentication_required=False,
                authentication_type=None,
                response_size_bytes=0,
                content_type=None,
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        except Exception as e:
            return EndpointAssessment(
                url=url,
                endpoint_type=EndpointType.UNKNOWN,
                status="exception",
                latency_ms=(time.time() - start_time) * 1000,
                http_status=0,
                schema_valid=False,
                error_message=str(e)[:200],
                authentication_required=False,
                authentication_type=None,
                response_size_bytes=0,
                content_type=None,
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
    
    async def assess_graphql_endpoint(self, url: str) -> EndpointAssessment:
        """Assess a GraphQL endpoint"""
        start_time = time.time()
        
        # Standard GraphQL introspection query
        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"query": query},
                    headers={**self.headers, "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    latency_ms = (time.time() - start_time) * 1000
                    content_type = resp.headers.get("Content-Type", "")
                    
                    if resp.status == 401:
                        return EndpointAssessment(
                            url=url,
                            endpoint_type=EndpointType.GRAPHQL,
                            status="unauthorized",
                            latency_ms=latency_ms,
                            http_status=resp.status,
                            schema_valid=False,
                            error_message="Authentication required",
                            authentication_required=True,
                            authentication_type="Bearer",
                            response_size_bytes=0,
                            content_type=content_type,
                            verified=False,
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                    
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            schema_valid = "data" in data and "__schema" in data.get("data", {})
                            return EndpointAssessment(
                                url=url,
                                endpoint_type=EndpointType.GRAPHQL,
                                status="success",
                                latency_ms=latency_ms,
                                http_status=resp.status,
                                schema_valid=schema_valid,
                                error_message=None,
                                authentication_required=False,
                                authentication_type=None,
                                response_size_bytes=len(json.dumps(data)),
                                content_type=content_type,
                                verified=True,
                                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                        except:
                            return EndpointAssessment(
                                url=url,
                                endpoint_type=EndpointType.GRAPHQL,
                                status="invalid_response",
                                latency_ms=latency_ms,
                                http_status=resp.status,
                                schema_valid=False,
                                error_message="Could not parse GraphQL response",
                                authentication_required=False,
                                authentication_type=None,
                                response_size_bytes=0,
                                content_type=content_type,
                                verified=False,
                                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                    
                    return EndpointAssessment(
                        url=url,
                        endpoint_type=EndpointType.GRAPHQL,
                        status=f"error_{resp.status}",
                        latency_ms=latency_ms,
                        http_status=resp.status,
                        schema_valid=False,
                        error_message=f"HTTP {resp.status}",
                        authentication_required=False,
                        authentication_type=None,
                        response_size_bytes=0,
                        content_type=content_type,
                        verified=False,
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
        
        except Exception as e:
            return EndpointAssessment(
                url=url,
                endpoint_type=EndpointType.GRAPHQL,
                status="exception",
                latency_ms=(time.time() - start_time) * 1000,
                http_status=0,
                schema_valid=False,
                error_message=str(e)[:200],
                authentication_required=False,
                authentication_type=None,
                response_size_bytes=0,
                content_type=None,
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
    
    async def assess(self, url: str, endpoint_type: Optional[EndpointType] = None) -> EndpointAssessment:
        """Assess an endpoint, auto-detecting type if not specified"""
        if endpoint_type == EndpointType.GRAPHQL or "/graphql" in url.lower():
            return await self.assess_graphql_endpoint(url)
        else:
            return await self.assess_rest_endpoint(url)
    
    async def crawl(self, source: Source) -> List:
        """Crawl endpoint and generate signals"""
        signals = []
        
        url = source.location
        endpoint_type = source.metadata.get("endpoint_type")
        
        if endpoint_type:
            endpoint_type = EndpointType(endpoint_type)
        
        assessment = await self.assess(url, endpoint_type)
        
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
    
    async def batch_assess(self, urls: List[str]) -> List[EndpointAssessment]:
        """Assess multiple endpoints in parallel"""
        tasks = [self.assess(url) for url in urls]
        return await asyncio.gather(*tasks)

# Example usage
if __name__ == "__main__":
    async def main():
        assessor = EndpointAssessor()
        
        # Test various endpoints
        endpoints = [
            "https://httpbin.org/get",
            "https://api.github.com",
            "https://jsonplaceholder.typicode.com/posts/1",
        ]
        
        print("Assessing endpoints...")
        results = await assessor.batch_assess(endpoints)
        
        for result in results:
            print(f"\n{result.url}:")
            print(f"  Type: {result.endpoint_type.value}")
            print(f"  Status: {result.status}")
            print(f"  HTTP Status: {result.http_status}")
            print(f"  Latency: {result.latency_ms:.0f}ms")
            print(f"  Verified: {result.verified}")
            print(f"  Schema Valid: {result.schema_valid}")
            if result.error_message:
                print(f"  Error: {result.error_message}")
    
    asyncio.run(main())
