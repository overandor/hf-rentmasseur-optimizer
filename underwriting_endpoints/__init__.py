"""
Underwriting API endpoints for external data sources.
"""

from underwriting_endpoints.base_client import BaseAPIClient, APIResponse, APIError, AuthenticationError, RateLimitError, ValidationError
from underwriting_endpoints.fema_client import FEMAClient, LightBoxFEMAClient
from underwriting_endpoints.plaid_client import PlaidClient
from underwriting_endpoints.experian_client import ExperianClient, ExperianConsumerClient
from underwriting_endpoints.sanctions_client import OFACClient, SanctionsComplianceEngine
from underwriting_endpoints.property_client import (
    SmartyClient,
    USPSClient,
    GoogleGeocodingClient,
    FirstStreetClient
)
from underwriting_endpoints.document_client import (
    AWSTextractClient,
    GoogleDocumentAIClient,
    AzureDocumentIntelligenceClient,
    OCRProcessor
)

__all__ = [
    "BaseAPIClient",
    "APIResponse",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "ValidationError",
    # FEMA
    "FEMAClient",
    "LightBoxFEMAClient",
    # Plaid
    "PlaidClient",
    # Experian
    "ExperianClient",
    "ExperianConsumerClient",
    # Sanctions
    "OFACClient",
    "SanctionsComplianceEngine",
    # Property
    "SmartyClient",
    "USPSClient",
    "GoogleGeocodingClient",
    "FirstStreetClient",
    # Documents
    "AWSTextractClient",
    "GoogleDocumentAIClient",
    "AzureDocumentIntelligenceClient",
    "OCRProcessor",
]
