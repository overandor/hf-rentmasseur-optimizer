"""
Base client for underwriting API endpoints.
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json


class APIError(Exception):
    """Base exception for API errors."""
    pass


class AuthenticationError(APIError):
    """Authentication failed."""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""
    pass


class ValidationError(APIError):
    """Validation failed."""
    pass


@dataclass
class APIResponse:
    """Standard API response wrapper."""
    success: bool
    data: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status_code: int = 200
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "status_code": self.status_code
        }


class BaseAPIClient:
    """Base client for API interactions."""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> APIResponse:
        """Make HTTP request with retry logic."""
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = {**self._get_headers(), **(headers or {})}
        
        for attempt in range(self.max_retries):
            try:
                async with self.session.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=request_headers
                ) as response:
                    response_data = await response.json() if response.content_type == "application/json" else await response.text()
                    
                    if response.status == 200:
                        return APIResponse(
                            success=True,
                            data=response_data if isinstance(response_data, dict) else {"raw": response_data},
                            status_code=response.status
                        )
                    elif response.status == 401:
                        raise AuthenticationError(f"Authentication failed for {url}")
                    elif response.status == 429:
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        raise RateLimitError(f"Rate limit exceeded for {url}")
                    elif response.status == 400:
                        raise ValidationError(f"Validation error: {response_data}")
                    else:
                        return APIResponse(
                            success=False,
                            errors=[f"HTTP {response.status}: {response_data}"],
                            status_code=response.status
                        )
            
            except aiohttp.ClientError as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return APIResponse(
                    success=False,
                    errors=[f"Request failed: {str(e)}"],
                    status_code=500
                )
        
        return APIResponse(success=False, errors=["Max retries exceeded"])
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> APIResponse:
        """Make GET request."""
        return await self._request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make POST request."""
        return await self._request("POST", endpoint, data=data)
    
    async def put(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make PUT request."""
        return await self._request("PUT", endpoint, data=data)
    
    async def delete(self, endpoint: str) -> APIResponse:
        """Make DELETE request."""
        return await self._request("DELETE", endpoint)
