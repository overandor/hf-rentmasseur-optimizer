"""
FEMA National Risk Index API client for natural hazard underwriting.
"""

from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse


class FEMAClient(BaseAPIClient):
    """Client for FEMA National Risk Index API."""
    
    # FEMA NRI API endpoints (using LightBox wrapper or direct FEMA data)
    BASE_URL = "https://www.fema.gov/api/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        # FEMA NRI data is publicly available, no API key required for basic access
        super().__init__(self.BASE_URL, api_key)
    
    async def get_national_risk_index(
        self,
        county_fips: Optional[str] = None,
        state_fips: Optional[str] = None,
        tract_id: Optional[str] = None
    ) -> APIResponse:
        """
        Get National Risk Index data for a location.
        
        Args:
            county_fips: 5-digit county FIPS code
            state_fips: 2-digit state FIPS code
            tract_id: Census tract ID
        
        Returns:
            APIResponse with risk index data including:
            - Overall risk score
            - Expected annual loss
            - Social vulnerability
            - Community resilience
            - Hazard-specific scores (flood, fire, wind, etc.)
        """
        if county_fips:
            endpoint = f"NRI/County/{county_fips}"
        elif state_fips:
            endpoint = f"NRI/State/{state_fips}"
        elif tract_id:
            endpoint = f"NRI/Tract/{tract_id}"
        else:
            return APIResponse(
                success=False,
                errors=["Must provide county_fips, state_fips, or tract_id"]
            )
        
        return await self.get(endpoint)
    
    async def get_hazard_details(
        self,
        hazard_type: str,
        location_id: str
    ) -> APIResponse:
        """
        Get detailed information for a specific hazard type.
        
        Args:
            hazard_type: Type of hazard (e.g., "avalanche", "coldwave", "drought", 
                         "earthquake", "flood", "hail", "heatwave", "hurricane",
                         "ice storm", "landslide", "lightning", "riverine", "tornado",
                         "tsunami", "volcanic", "wildfire", "wind", "winterweather")
            location_id: FIPS code or tract ID
        
        Returns:
            APIResponse with hazard-specific risk data
        """
        endpoint = f"NRI/Hazard/{hazard_type}/{location_id}"
        return await self.get(endpoint)
    
    async def get_risk_rating(
        self,
        location_id: str,
        risk_type: str = "overall"
    ) -> APIResponse:
        """
        Get risk rating classification for a location.
        
        Args:
            location_id: FIPS code or tract ID
            risk_type: Type of risk (overall, or specific hazard)
        
        Returns:
            APIResponse with risk rating (Very Low, Low, Relatively Low, 
            Relatively Moderate, Moderately High, High, Very High)
        """
        endpoint = f"NRI/Rating/{risk_type}/{location_id}"
        return await self.get(endpoint)
    
    def parse_risk_score(self, response: APIResponse) -> Dict:
        """
        Parse risk score from API response into underwriting format.
        
        Returns:
            Dict with underwriting-relevant fields:
            - risk_score: Overall risk score (0-100)
            - risk_rating: Textual rating
            - expected_annual_loss: Economic loss estimate
            - social_vulnerability: Social vulnerability score
            - community_resilience: Community resilience score
            - hazard_breakdown: Individual hazard scores
        """
        if not response.success:
            return {"error": "Failed to retrieve risk data"}
        
        data = response.data
        
        return {
            "risk_score": data.get("NRI_Score", 0),
            "risk_rating": data.get("NRI_Rating", "Unknown"),
            "expected_annual_loss": data.get("EAL_Score", 0),
            "social_vulnerability": data.get("SV_Score", 0),
            "community_resilience": data.get("RPL_Score", 0),
            "hazard_breakdown": self._extract_hazard_scores(data),
            "location_id": data.get("ID", ""),
            "underwriting_notes": self._generate_underwriting_notes(data)
        }
    
    def _extract_hazard_scores(self, data: Dict) -> Dict[str, Dict]:
        """Extract individual hazard scores from response."""
        hazards = [
            "AVLN", "CWAV", "DRGT", "ERQK", "FLD", "HAIL", "HWAV",
            "HRCN", "ISTM", "LNDL", "LTNG", "RFLD", "TRND", "TSUN",
            "VLCN", "WFIR", "WNDW", "WNTW"
        ]
        
        breakdown = {}
        for hazard in hazards:
            if f"{hazard}_Score" in data:
                breakdown[hazard] = {
                    "score": data.get(f"{hazard}_Score", 0),
                    "rating": data.get(f"{hazard}_Rtg", "Unknown")
                }
        
        return breakdown
    
    def _generate_underwriting_notes(self, data: Dict) -> List[str]:
        """Generate underwriting notes based on risk data."""
        notes = []
        
        risk_score = data.get("NRI_Score", 0)
        if risk_score > 80:
            notes.append("CRITICAL: Very high natural hazard risk")
        elif risk_score > 60:
            notes.append("WARNING: High natural hazard risk")
        elif risk_score > 40:
            notes.append("MODERATE: Elevated natural hazard risk")
        
        # Social vulnerability
        sv_score = data.get("SV_Score", 0)
        if sv_score > 70:
            notes.append("High social vulnerability may impact recovery capacity")
        
        # Community resilience
        rpl_score = data.get("RPL_Score", 0)
        if rpl_score < 30:
            notes.append("Low community resilience - consider additional insurance requirements")
        
        return notes


class LightBoxFEMAClient(BaseAPIClient):
    """Client for LightBox FEMA NRI API wrapper (if available)."""
    
    BASE_URL = "https://api.lightboxre.com/v1"
    
    def __init__(self, api_key: str):
        super().__init__(self.BASE_URL, api_key)
    
    async def get_fema_nri_by_address(self, address: str) -> APIResponse:
        """
        Get FEMA NRI data by address using LightBox geocoding.
        
        Args:
            address: Property address
        
        Returns:
            APIResponse with FEMA NRI data for the address
        """
        endpoint = "fema/nri/address"
        return await self.post(endpoint, data={"address": address})
    
    async def get_fema_nri_by_lat_lon(self, lat: float, lon: float) -> APIResponse:
        """
        Get FEMA NRI data by latitude/longitude.
        
        Args:
            lat: Latitude
            lon: Longitude
        
        Returns:
            APIResponse with FEMA NRI data for the location
        """
        endpoint = "fema/nri/latlon"
        return await self.post(endpoint, data={"latitude": lat, "longitude": lon})
