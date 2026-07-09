"""
OFAC Sanctions List API client for KYC/compliance screening.
"""

from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse


class OFACClient(BaseAPIClient):
    """Client for OFAC (Office of Foreign Assets Control) sanctions screening."""
    
    # OFAC data is publicly available via Treasury API
    BASE_URL = "https://api.ofac.treasury.gov"
    
    def __init__(self, api_key: Optional[str] = None):
        # OFAC API is publicly available, but rate-limited
        super().__init__(self.BASE_URL, api_key)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get OFAC-specific headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["api_key"] = self.api_key
        return headers
    
    async def search_sanctions_list(
        self,
        name: str,
        fuzzy_match: bool = True,
        limit: int = 100
    ) -> APIResponse:
        """
        Search OFAC sanctions list by name.
        
        Args:
            name: Name to search (individual or entity)
            fuzzy_match: Enable fuzzy matching
            limit: Maximum number of results
        
        Returns:
            APIResponse with matching sanctions entries
        """
        endpoint = "sdn/search"
        params = {
            "name": name,
            "fuzzyMatch": "true" if fuzzy_match else "false",
            "limit": limit
        }
        
        return await self.get(endpoint, params=params)
    
    async def search_by_address(self, address: str) -> APIResponse:
        """
        Search sanctions list by address.
        
        Args:
            address: Street address
        
        Returns:
            APIResponse with matching entries
        """
        endpoint = "sdn/search"
        params = {
            "address": address
        }
        
        return await self.get(endpoint, params=params)
    
    async def get_sdn_details(self, sdn_id: str) -> APIResponse:
        """
        Get detailed information for a specific SDN (Specially Designated National).
        
        Args:
            sdn_id: SDN entity ID
        
        Returns:
            APIResponse with detailed SDN information
        """
        endpoint = f"sdn/{sdn_id}"
        return await self.get(endpoint)
    
    async def get_list_updates(self, publish_date: Optional[str] = None) -> APIResponse:
        """
        Get list of recent updates to sanctions list.
        
        Args:
            publish_date: Optional date filter (YYYY-MM-DD)
        
        Returns:
            APIResponse with recent updates
        """
        endpoint = "sdn/updates"
        params = {}
        if publish_date:
            params["publishDate"] = publish_date
        
        return await self.get(endpoint, params=params)
    
    def parse_sanctions_result(self, response: APIResponse) -> Dict:
        """
        Parse sanctions search result into underwriting format.
        
        Returns:
            Dict with underwriting-relevant fields:
            - matches: Number of matches found
            - is_sanctioned: Whether the entity is on sanctions list
            - match_details: Details of any matches
            - risk_level: Risk level (none, low, medium, high, critical)
            - underwriting_notes: Underwriting recommendations
        """
        if not response.success:
            return {"error": "Failed to retrieve sanctions data"}
        
        data = response.data
        results = data.get("results", [])
        
        if not results:
            return {
                "matches": 0,
                "is_sanctioned": False,
                "risk_level": "none",
                "underwriting_notes": ["No sanctions matches found"]
            }
        
        # Analyze matches
        exact_matches = [r for r in results if r.get("matchType") == "exact"]
        fuzzy_matches = [r for r in results if r.get("matchType") == "fuzzy"]
        
        is_sanctioned = len(exact_matches) > 0
        
        risk_level = "critical" if is_sanctioned else "high" if fuzzy_matches else "medium"
        
        match_details = []
        for match in results[:10]:  # Limit to top 10 matches
            match_details.append({
                "name": match.get("name"),
                "type": match.get("type"),
                "match_type": match.get("matchType"),
                "score": match.get("score", 0),
                "programs": match.get("programs", []),
                "addresses": match.get("addresses", [])
            })
        
        return {
            "matches": len(results),
            "exact_matches": len(exact_matches),
            "fuzzy_matches": len(fuzzy_matches),
            "is_sanctioned": is_sanctioned,
            "risk_level": risk_level,
            "match_details": match_details,
            "underwriting_notes": self._generate_sanctions_notes(is_sanctioned, len(fuzzy_matches))
        }
    
    def _generate_sanctions_notes(self, is_sanctioned: bool, fuzzy_count: int) -> List[str]:
        """Generate underwriting notes based on sanctions check."""
        notes = []
        
        if is_sanctioned:
            notes.append("CRITICAL: Exact match on sanctions list - BLOCK")
        elif fuzzy_count > 0:
            notes.append(f"HIGH: {fuzzy_count} fuzzy matches on sanctions list - requires manual review")
        else:
            notes.append("CLEAN: No sanctions matches found")
        
        return notes


class SanctionsComplianceEngine:
    """Engine for comprehensive sanctions screening."""
    
    def __init__(self, ofac_client: OFACClient):
        self.ofac_client = ofac_client
    
    async def screen_individual(
        self,
        name: str,
        date_of_birth: Optional[str] = None,
        address: Optional[str] = None
    ) -> Dict:
        """
        Screen an individual against sanctions lists.
        
        Args:
            name: Full name
            date_of_birth: Date of birth (YYYY-MM-DD) for disambiguation
            address: Address for additional screening
        
        Returns:
            Comprehensive screening result
        """
        # Search by name
        name_result = await self.ofac_client.search_sanctions_list(name)
        name_data = self.ofac_client.parse_sanctions_result(name_result)
        
        # Search by address if provided
        address_data = None
        if address:
            address_result = await self.ofac_client.search_by_address(address)
            address_data = self.ofac_client.parse_sanctions_result(address_result)
        
        # Combine results
        return {
            "name_screening": name_data,
            "address_screening": address_data,
            "overall_risk": self._calculate_overall_risk(name_data, address_data),
            "recommendation": self._generate_recommendation(name_data, address_data)
        }
    
    async def screen_business(
        self,
        business_name: str,
        address: Optional[str] = None
    ) -> Dict:
        """
        Screen a business against sanctions lists.
        
        Args:
            business_name: Legal business name
            address: Business address
        
        Returns:
            Comprehensive screening result
        """
        return await self.screen_individual(business_name, address=address)
    
    def _calculate_overall_risk(self, name_data: Dict, address_data: Optional[Dict]) -> str:
        """Calculate overall risk from multiple screenings."""
        if name_data.get("is_sanctioned"):
            return "critical"
        if address_data and address_data.get("is_sanctioned"):
            return "critical"
        if name_data.get("fuzzy_matches", 0) > 0:
            return "high"
        if address_data and address_data.get("fuzzy_matches", 0) > 0:
            return "high"
        return "none"
    
    def _generate_recommendation(self, name_data: Dict, address_data: Optional[Dict]) -> str:
        """Generate underwriting recommendation."""
        overall_risk = self._calculate_overall_risk(name_data, address_data)
        
        if overall_risk == "critical":
            return "BLOCK: Entity matches sanctions list"
        elif overall_risk == "high":
            return "REVIEW: Fuzzy matches require manual review"
        else:
            return "APPROVE: No sanctions concerns"
