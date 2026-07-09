"""
Property and address normalization API clients for underwriting.
"""

from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse


class SmartyClient(BaseAPIClient):
    """Client for Smarty (formerly SmartyStreets) address validation and geocoding."""
    
    BASE_URL = "https://us-street.api.smartystreets.com/street-address"
    
    def __init__(self, auth_id: str, auth_token: str):
        """
        Initialize Smarty client.
        
        Args:
            auth_id: Smarty auth ID
            auth_token: Smarty auth token
        """
        super().__init__(self.BASE_URL)
        self.auth_id = auth_id
        self.auth_token = auth_token
    
    def _get_headers(self) -> Dict[str, str]:
        """Smarty uses query params for auth, not headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def validate_address(
        self,
        street: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> APIResponse:
        """
        Validate and standardize a US address.
        
        Args:
            street: Street address
            city: City name
            state: State abbreviation
            zipcode: ZIP code
        
        Returns:
            APIResponse with validated address and geocoding data
        """
        params = {
            "auth-id": self.auth_id,
            "auth-token": self.auth_token,
            "street": street
        }
        
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if zipcode:
            params["zipcode"] = zipcode
        
        return await self.get("", params=params)
    
    async def geocode_address(
        self,
        street: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> APIResponse:
        """
        Geocode an address to get coordinates.
        
        Args:
            street: Street address
            city: City name
            state: State abbreviation
            zipcode: ZIP code
        
        Returns:
            APIResponse with latitude and longitude
        """
        # Smarty includes coordinates in address validation response
        return await self.validate_address(street, city, state, zipcode)


class USPSClient(BaseAPIClient):
    """Client for USPS Address Validation API."""
    
    BASE_URL = "https://secure.shippingapis.com/ShippingAPI.dll"
    
    def __init__(self, user_id: str):
        """
        Initialize USPS client.
        
        Args:
            user_id: USPS Web Tools user ID
        """
        super().__init__(self.BASE_URL)
        self.user_id = user_id
    
    async def validate_address(
        self,
        address1: Optional[str] = None,
        address2: str = "",
        city: str,
        state: str,
        zip5: str,
        zip4: Optional[str] = None
    ) -> APIResponse:
        """
        Validate address using USPS API.
        
        Args:
            address1: Apartment, suite, unit, etc.
            address2: Street address
            city: City name
            state: State abbreviation
            zip5: 5-digit ZIP code
            zip4: 4-digit ZIP extension
        
        Returns:
            APIResponse with validated address
        """
        params = {
            "API": "Verify",
            "XML": f"""<AddressValidateRequest USERID="{self.user_id}">
                <Revision>1</Revision>
                <Address ID="0">
                    <Address1>{address1 or ""}</Address1>
                    <Address2>{address2}</Address2>
                    <City>{city}</City>
                    <State>{state}</State>
                    <Zip5>{zip5}</Zip5>
                    <Zip4>{zip4 or ""}</Zip4>
                </Address>
            </AddressValidateRequest>"""
        }
        
        return await self.get("", params=params)


class GoogleGeocodingClient(BaseAPIClient):
    """Client for Google Geocoding API."""
    
    BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    
    def __init__(self, api_key: str):
        """
        Initialize Google Geocoding client.
        
        Args:
            api_key: Google Maps API key
        """
        super().__init__(self.BASE_URL)
        self.api_key = api_key
    
    async def geocode_address(self, address: str) -> APIResponse:
        """
        Geocode an address to get coordinates.
        
        Args:
            address: Full address string
        
        Returns:
            APIResponse with latitude, longitude, and formatted address
        """
        params = {
            "address": address,
            "key": self.api_key
        }
        
        return await self.get("", params=params)
    
    async def reverse_geocode(self, lat: float, lng: float) -> APIResponse:
        """
        Reverse geocode coordinates to get address.
        
        Args:
            lat: Latitude
            lng: Longitude
        
        Returns:
            APIResponse with address components
        """
        params = {
            "latlng": f"{lat},{lng}",
            "key": self.api_key
        }
        
        return await self.get("", params=params)


class FirstStreetClient(BaseAPIClient):
    """Client for First Street Foundation climate risk data."""
    
    BASE_URL = "https://api.firststreet.org"
    
    def __init__(self, api_key: str):
        """
        Initialize First Street client.
        
        Args:
            api_key: First Street API key
        """
        super().__init__(self.BASE_URL, api_key)
    
    async def get_property_risk(self, fsid: str) -> APIResponse:
        """
        Get climate risk data for a property by FSID.
        
        Args:
            fsid: First Street property ID
        
        Returns:
            APIResponse with flood, fire, and heat risk data
        """
        endpoint = f"property/{fsid}"
        return await self.get(endpoint)
    
    async def search_property(
        self,
        address: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> APIResponse:
        """
        Search for a property to get FSID.
        
        Args:
            address: Street address
            city: City name
            state: State abbreviation
            zipcode: ZIP code
        
        Returns:
            APIResponse with property FSID
        """
        endpoint = "property/search"
        params = {
            "address": address
        }
        
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if zipcode:
            params["zipcode"] = zipcode
        
        return await self.get(endpoint, params=params)
    
    async def get_flood_risk(self, fsid: str) -> APIResponse:
        """Get detailed flood risk for a property."""
        endpoint = f"property/{fsid}/flood"
        return await self.get(endpoint)
    
    async def get_fire_risk(self, fsid: str) -> APIResponse:
        """Get detailed fire risk for a property."""
        endpoint = f"property/{fsid}/fire"
        return await self.get(endpoint)
    
    async def get_heat_risk(self, fsid: str) -> APIResponse:
        """Get detailed heat risk for a property."""
        endpoint = f"property/{fsid}/heat"
        return await self.get(endpoint)
    
    def parse_climate_risk(self, response: APIResponse) -> Dict:
        """
        Parse climate risk data for underwriting.
        
        Returns:
            Dict with underwriting-relevant fields
        """
        if not response.success:
            return {"error": "Failed to retrieve climate risk data"}
        
        data = response.data
        
        return {
            "property_id": data.get("fsid"),
            "address": data.get("address"),
            "flood_risk": {
                "risk_score": data.get("flood", {}).get("riskScore", 0),
                "risk_level": data.get("flood", {}).get("riskLevel", "unknown"),
                "depth_100_year": data.get("flood", {}).get("depth100Year", 0),
                "depth_500_year": data.get("flood", {}).get("depth500Year", 0)
            },
            "fire_risk": {
                "risk_score": data.get("fire", {}).get("riskScore", 0),
                "risk_level": data.get("fire", {}).get("riskLevel", "unknown"),
                "burn_probability": data.get("fire", {}).get("burnProbability", 0)
            },
            "heat_risk": {
                "risk_score": data.get("heat", {}).get("riskScore", 0),
                "risk_level": data.get("heat", {}).get("riskLevel", "unknown"),
                "max_temperature_increase": data.get("heat", {}).get("maxTempIncrease", 0)
            },
            "underwriting_notes": self._generate_climate_notes(data)
        }
    
    def _generate_climate_notes(self, data: Dict) -> List[str]:
        """Generate underwriting notes based on climate risk."""
        notes = []
        
        # Flood risk
        flood_score = data.get("flood", {}).get("riskScore", 0)
        if flood_score > 80:
            notes.append("CRITICAL: Very high flood risk - requires flood insurance")
        elif flood_score > 50:
            notes.append("HIGH: Elevated flood risk")
        
        # Fire risk
        fire_score = data.get("fire", {}).get("riskScore", 0)
        if fire_score > 80:
            notes.append("CRITICAL: Very high wildfire risk")
        elif fire_score > 50:
            notes.append("HIGH: Elevated wildfire risk")
        
        # Heat risk
        heat_score = data.get("heat", {}).get("riskScore", 0)
        if heat_score > 80:
            notes.append("HIGH: Extreme heat risk may impact property value")
        
        return notes
