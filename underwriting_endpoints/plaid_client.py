"""
Plaid API client for cash-flow underwriting and bank transaction analysis.
"""

from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse, AuthenticationError


class PlaidClient(BaseAPIClient):
    """Client for Plaid API for financial underwriting."""
    
    BASE_URL = "https://sandbox.plaid.com"  # Use sandbox for development
    PRODUCTION_URL = "https://production.plaid.com"
    
    def __init__(self, client_id: str, secret: str, environment: str = "sandbox"):
        """
        Initialize Plaid client.
        
        Args:
            client_id: Plaid client ID
            secret: Plaid secret key
            environment: 'sandbox' or 'production'
        """
        base_url = self.PRODUCTION_URL if environment == "production" else self.BASE_URL
        super().__init__(base_url)
        self.client_id = client_id
        self.secret = secret
        self.environment = environment
    
    def _get_headers(self) -> Dict[str, str]:
        """Get Plaid-specific headers."""
        return {
            "Content-Type": "application/json",
            "PLAID-CLIENT-ID": self.client_id,
            "PLAID-SECRET": self.secret
        }
    
    async def create_link_token(
        self,
        user: Optional[Dict] = None,
        products: Optional[List[str]] = None,
        country_codes: Optional[List[str]] = None
    ) -> APIResponse:
        """
        Create a link token for Plaid Link frontend integration.
        
        Args:
            user: User information (client_user_id required)
            products: List of products (auth, transactions, identity, income, assets)
            country_codes: List of country codes (e.g., ['US'])
        
        Returns:
            APIResponse with link_token
        """
        if products is None:
            products = ["auth", "transactions"]
        
        if country_codes is None:
            country_codes = ["US"]
        
        if user is None:
            user = {"client_user_id": "user-temp-id"}
        
        endpoint = "link/token/create"
        data = {
            "user": user,
            "client_name": "Underwriting Service",
            "products": products,
            "country_codes": country_codes,
            "language": "en"
        }
        
        return await self.post(endpoint, data)
    
    async def exchange_public_token(self, public_token: str) -> APIResponse:
        """
        Exchange a public_token from Plaid Link for an access_token.
        
        Args:
            public_token: Public token from Plaid Link
        
        Returns:
            APIResponse with access_token and item_id
        """
        endpoint = "item/public_token/exchange"
        data = {
            "public_token": public_token
        }
        
        return await self.post(endpoint, data)
    
    async def get_auth(self, access_token: str) -> APIResponse:
        """
        Retrieve authentication data for an Item.
        
        Args:
            access_token: Access token for the Item
        
        Returns:
            APIResponse with account numbers and routing numbers
        """
        endpoint = "auth/get"
        data = {
            "access_token": access_token
        }
        
        return await self.post(endpoint, data)
    
    async def get_transactions(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        count: int = 100,
        offset: int = 0
    ) -> APIResponse:
        """
        Retrieve transactions for an Item.
        
        Args:
            access_token: Access token for the Item
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            count: Number of transactions to retrieve
            offset: Offset for pagination
        
        Returns:
            APIResponse with transactions data
        """
        endpoint = "transactions/get"
        data = {
            "access_token": access_token,
            "start_date": start_date,
            "end_date": end_date,
            "options": {
                "count": count,
                "offset": offset
            }
        }
        
        return await self.post(endpoint, data)
    
    async def get_identity(self, access_token: str) -> APIResponse:
        """
        Retrieve Identity information for an Item.
        
        Args:
            access_token: Access token for the Item
        
        Returns:
            APIResponse with identity data (names, emails, phone numbers, addresses)
        """
        endpoint = "identity/get"
        data = {
            "access_token": access_token
        }
        
        return await self.post(endpoint, data)
    
    async def get_income(self, access_token: str) -> APIResponse:
        """
        Retrieve Income information for an Item.
        
        Args:
            access_token: Access token for the Item
        
        Returns:
            APIResponse with income data (stream income, tax info)
        """
        endpoint = "income/get"
        data = {
            "access_token": access_token
        }
        
        return await self.post(endpoint, data)
    
    async def get_balance(self, access_token: str) -> APIResponse:
        """
        Retrieve real-time balance for each account.
        
        Args:
            access_token: Access token for the Item
        
        Returns:
            APIResponse with balance data
        """
        endpoint = "accounts/balance/get"
        data = {
            "access_token": access_token
        }
        
        return await self.post(endpoint, data)
    
    def parse_cash_flow_data(self, auth_response: APIResponse, transactions_response: APIResponse) -> Dict:
        """
        Parse Plaid data into cash-flow underwriting format.
        
        Returns:
            Dict with underwriting-relevant fields:
            - account_count: Number of accounts
            - total_balance: Sum of all account balances
            - monthly_income: Estimated monthly income
            - monthly_expenses: Estimated monthly expenses
            - cash_flow: Net monthly cash flow
            - account_types: Breakdown by account type
            - transaction_summary: Transaction statistics
        """
        if not auth_response.success or not transactions_response.success:
            return {"error": "Failed to retrieve Plaid data"}
        
        auth_data = auth_response.data
        transactions_data = transactions_response.data
        
        # Extract account information
        accounts = auth_data.get("accounts", [])
        total_balance = sum(acc.get("balances", {}).get("current", 0) for acc in accounts)
        
        # Extract transactions
        transactions = transactions_data.get("transactions", [])
        
        # Calculate income and expenses (simplified)
        income = sum(t.get("amount", 0) for t in transactions if t.get("amount", 0) > 0)
        expenses = sum(abs(t.get("amount", 0)) for t in transactions if t.get("amount", 0) < 0)
        
        return {
            "account_count": len(accounts),
            "total_balance": total_balance,
            "monthly_income": income,
            "monthly_expenses": expenses,
            "cash_flow": income - expenses,
            "account_types": self._extract_account_types(accounts),
            "transaction_summary": {
                "total_transactions": len(transactions),
                "income_transactions": len([t for t in transactions if t.get("amount", 0) > 0]),
                "expense_transactions": len([t for t in transactions if t.get("amount", 0) < 0])
            },
            "underwriting_notes": self._generate_cash_flow_notes(income, expenses, total_balance)
        }
    
    def _extract_account_types(self, accounts: List[Dict]) -> Dict[str, int]:
        """Extract account type breakdown."""
        types = {}
        for acc in accounts:
            acc_type = acc.get("type", "unknown")
            types[acc_type] = types.get(acc_type, 0) + 1
        return types
    
    def _generate_cash_flow_notes(self, income: float, expenses: float, balance: float) -> List[str]:
        """Generate underwriting notes based on cash flow."""
        notes = []
        
        cash_flow = income - expenses
        
        if cash_flow < 0:
            notes.append("WARNING: Negative monthly cash flow")
        elif cash_flow < income * 0.1:
            notes.append("LOW: Tight cash flow margin")
        else:
            notes.append("GOOD: Positive cash flow")
        
        if balance < 1000:
            notes.append("LOW: Low account balance")
        
        if expenses > income:
            notes.append("CRITICAL: Expenses exceed income")
        
        return notes
