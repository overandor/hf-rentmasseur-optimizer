"""
Experian Business API client for business identity and credit underwriting.
"""

from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse


class ExperianClient(BaseAPIClient):
    """Client for Experian Business API."""
    
    BASE_URL = "https://api.experian.com/business-information"
    
    def __init__(self, api_key: str, environment: str = "sandbox"):
        """
        Initialize Experian client.
        
        Args:
            api_key: Experian API key
            environment: 'sandbox' or 'production'
        """
        base_url = self.BASE_URL
        if environment == "sandbox":
            base_url = "https://sandbox-api.experian.com/business-information"
        
        super().__init__(base_url, api_key)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get Experian-specific headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def get_business_profile(
        self,
        business_name: Optional[str] = None,
        ein: Optional[str] = None,
        address: Optional[str] = None
    ) -> APIResponse:
        """
        Retrieve business profile information.
        
        Args:
            business_name: Legal business name
            ein: Employer Identification Number
            address: Business address
        
        Returns:
            APIResponse with business profile data
        """
        endpoint = "business/profile"
        data = {}
        
        if business_name:
            data["businessName"] = business_name
        if ein:
            data["ein"] = ein
        if address:
            data["address"] = address
        
        if not data:
            return APIResponse(
                success=False,
                errors=["Must provide at least one of: business_name, ein, or address"]
            )
        
        return await self.post(endpoint, data)
    
    async def get_credit_score(self, business_id: str) -> APIResponse:
        """
        Retrieve business credit score.
        
        Args:
            business_id: Experian business ID
        
        Returns:
            APIResponse with credit score data
        """
        endpoint = f"credit-score/{business_id}"
        return await self.get(endpoint)
    
    async def get_fraud_indicator(self, business_id: str) -> APIResponse:
        """
        Retrieve fraud risk indicators.
        
        Args:
            business_id: Experian business ID
        
        Returns:
            APIResponse with fraud risk data
        """
        endpoint = f"fraud/{business_id}"
        return await self.get(endpoint)
    
    async def search_businesses(
        self,
        query: str,
        limit: int = 10
    ) -> APIResponse:
        """
        Search for businesses by name or other criteria.
        
        Args:
            query: Search query (business name, address, etc.)
            limit: Maximum number of results
        
        Returns:
            APIResponse with search results
        """
        endpoint = "business/search"
        data = {
            "query": query,
            "limit": limit
        }
        
        return await self.post(endpoint, data)
    
    def parse_business_credit_data(self, profile_response: APIResponse, credit_response: APIResponse) -> Dict:
        """
        Parse Experian data into underwriting format.
        
        Returns:
            Dict with underwriting-relevant fields:
            - business_name: Legal business name
            - ein: Employer Identification Number
            - credit_score: Business credit score
            - credit_rating: Credit rating category
            - years_in_business: Number of years in operation
            - fraud_risk: Fraud risk level
            - payment_history: Payment history summary
            - underwriting_notes: Underwriting recommendations
        """
        if not profile_response.success:
            return {"error": "Failed to retrieve business profile"}
        
        profile_data = profile_response.data
        credit_data = credit_response.data if credit_response.success else {}
        
        return {
            "business_name": profile_data.get("businessName"),
            "ein": profile_data.get("ein"),
            "address": profile_data.get("address"),
            "credit_score": credit_data.get("creditScore"),
            "credit_rating": credit_data.get("creditRating"),
            "years_in_business": profile_data.get("yearsInBusiness"),
            "fraud_risk": credit_data.get("fraudRisk", "unknown"),
            "payment_history": self._extract_payment_history(credit_data),
            "underwriting_notes": self._generate_business_notes(profile_data, credit_data)
        }
    
    def _extract_payment_history(self, credit_data: Dict) -> Dict:
        """Extract payment history summary."""
        return {
            "on_time_payments": credit_data.get("onTimePayments", 0),
            "late_payments": credit_data.get("latePayments", 0),
            "delinquencies": credit_data.get("delinquencies", 0),
            "payment_trend": credit_data.get("paymentTrend", "unknown")
        }
    
    def _generate_business_notes(self, profile_data: Dict, credit_data: Dict) -> List[str]:
        """Generate underwriting notes."""
        notes = []
        
        credit_score = credit_data.get("creditScore", 0)
        if credit_score >= 80:
            notes.append("EXCELLENT: High credit score")
        elif credit_score >= 60:
            notes.append("GOOD: Acceptable credit score")
        elif credit_score >= 40:
            notes.append("FAIR: Moderate credit risk")
        else:
            notes.append("POOR: High credit risk")
        
        years_in_business = profile_data.get("yearsInBusiness", 0)
        if years_in_business < 1:
            notes.append("HIGH RISK: New business (< 1 year)")
        elif years_in_business < 3:
            notes.append("MODERATE: Young business (1-3 years)")
        else:
            notes.append("LOW RISK: Established business (3+ years)")
        
        fraud_risk = credit_data.get("fraudRisk", "low")
        if fraud_risk == "high":
            notes.append("CRITICAL: High fraud risk indicator")
        
        return notes


class ExperianConsumerClient(BaseAPIClient):
    """Client for Experian Consumer API (for personal underwriting)."""
    
    BASE_URL = "https://api.experian.com/consumer-information"
    
    def __init__(self, api_key: str, environment: str = "sandbox"):
        base_url = self.BASE_URL
        if environment == "sandbox":
            base_url = "https://sandbox-api.experian.com/consumer-information"
        
        super().__init__(base_url, api_key)
    
    async def get_credit_report(
        self,
        first_name: str,
        last_name: str,
        ssn_last_four: str,
        address: str,
        zip_code: str
    ) -> APIResponse:
        """
        Retrieve consumer credit report (requires proper consent and compliance).
        
        Args:
            first_name: First name
            last_name: Last name
            ssn_last_four: Last 4 digits of SSN
            address: Street address
            zip_code: ZIP code
        
        Returns:
            APIResponse with credit report data
        
        Note: Requires proper user consent and compliance with FCRA.
        """
        endpoint = "credit-report"
        data = {
            "firstName": first_name,
            "lastName": last_name,
            "ssnLastFour": ssn_last_four,
            "address": address,
            "zipCode": zip_code
        }
        
        return await self.post(endpoint, data)
