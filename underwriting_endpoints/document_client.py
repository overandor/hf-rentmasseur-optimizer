"""
Document extraction and analysis clients for underwriting.
"""

import base64
from typing import Dict, List, Optional
from underwriting_endpoints.base_client import BaseAPIClient, APIResponse


class AWSTextractClient(BaseAPIClient):
    """Client for AWS Textract document extraction."""
    
    BASE_URL = "https://textract.{region}.amazonaws.com"
    
    def __init__(self, access_key: str, secret_key: str, region: str = "us-east-1"):
        """
        Initialize AWS Textract client.
        
        Args:
            access_key: AWS access key
            secret_key: AWS secret key
            region: AWS region
        """
        # Note: This would typically use boto3 SDK
        # For HTTP API, use appropriate AWS signature
        super().__init__(self.BASE_URL.format(region=region))
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
    
    async def extract_text_from_document(
        self,
        document_bytes: bytes,
        document_type: str = "pdf"
    ) -> APIResponse:
        """
        Extract text from a document (PDF, image, etc.).
        
        Args:
            document_bytes: Document file bytes
            document_type: Type of document (pdf, png, jpeg, etc.)
        
        Returns:
            APIResponse with extracted text
        """
        # Note: This requires AWS SDK (boto3) for proper implementation
        # HTTP API would require AWS Signature V4
        
        import warnings
        warnings.warn("AWS Textract requires boto3 SDK. Use DocumentAI or similar for HTTP API.")
        
        return APIResponse(
            success=False,
            errors=["AWS Textract requires boto3 SDK. Install with: pip install boto3"]
        )
    
    async def analyze_expense(self, document_bytes: bytes) -> APIResponse:
        """
        Analyze expense documents (receipts, invoices).
        
        Args:
            document_bytes: Document file bytes
        
        Returns:
            APIResponse with extracted expense data
        """
        return APIResponse(
            success=False,
            errors=["AWS Textract requires boto3 SDK"]
        )


class GoogleDocumentAIClient(BaseAPIClient):
    """Client for Google Cloud Document AI."""
    
    BASE_URL = "https://documentai.googleapis.com/v1"
    
    def __init__(self, api_key: str, project_id: str, location: str = "us"):
        """
        Initialize Google Document AI client.
        
        Args:
            api_key: Google API key
            project_id: Google Cloud project ID
            location: Processor location
        """
        super().__init__(self.BASE_URL, api_key)
        self.project_id = project_id
        self.location = location
    
    async def process_document(
        self,
        document_bytes: bytes,
        processor_id: str,
        mime_type: str = "application/pdf"
    ) -> APIResponse:
        """
        Process a document with Document AI.
        
        Args:
            document_bytes: Document file bytes
            processor_id: Document AI processor ID
            mime_type: MIME type of document
        
        Returns:
            APIResponse with extracted text and entities
        """
        import base64
        
        endpoint = f"projects/{self.project_id}/locations/{self.location}/processors/{processor_id}:process"
        
        data = {
            "rawDocument": {
                "content": base64.b64encode(document_bytes).decode(),
                "mimeType": mime_type
            }
        }
        
        return await self.post(endpoint, data=data)
    
    async def extract_bank_statement(self, document_bytes: bytes) -> APIResponse:
        """
        Extract data from bank statement.
        
        Args:
            document_bytes: Bank statement PDF bytes
        
        Returns:
            APIResponse with account balances, transactions, etc.
        """
        # Use specialized bank statement processor
        processor_id = "bank-statement-processor"  # Example processor ID
        return await self.process_document(document_bytes, processor_id)


class AzureDocumentIntelligenceClient(BaseAPIClient):
    """Client for Azure AI Document Intelligence (formerly Form Recognizer)."""
    
    BASE_URL = "https://{resource_name}.cognitiveservices.azure.com/formrecognizer/v2.1"
    
    def __init__(self, api_key: str, resource_name: str):
        """
        Initialize Azure Document Intelligence client.
        
        Args:
            api_key: Azure API key
            resource_name: Azure resource name
        """
        super().__init__(self.BASE_URL.format(resource_name=resource_name), api_key)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get Azure-specific headers."""
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.api_key
        }
        return headers
    
    async def analyze_receipt(self, document_bytes: bytes) -> APIResponse:
        """
        Analyze receipt for expense data.
        
        Args:
            document_bytes: Receipt image bytes
        
        Returns:
            APIResponse with merchant, amount, date, line items
        """
        import base64
        
        endpoint = "prebuilt/receipt/analyze"
        data = {
            "source": f"data:image/jpeg;base64,{base64.b64encode(document_bytes).decode()}"
        }
        
        return await self.post(endpoint, data=data)
    
    async def analyze_invoice(self, document_bytes: bytes) -> APIResponse:
        """
        Analyze invoice for billing data.
        
        Args:
            document_bytes: Invoice PDF bytes
        
        Returns:
            APIResponse with vendor, amount, due date, line items
        """
        import base64
        
        endpoint = "prebuilt/invoice/analyze"
        data = {
            "source": f"data:application/pdf;base64,{base64.b64encode(document_bytes).decode()}"
        }
        
        return await self.post(endpoint, data=data)
    
    async def analyze_identity_document(self, document_bytes: bytes) -> APIResponse:
        """
        Analyze ID document (driver's license, passport).
        
        Args:
            document_bytes: ID document image bytes
        
        Returns:
            APIResponse with name, DOB, address, document number
        """
        import base64
        
        endpoint = "prebuilt/idDocument/analyze"
        data = {
            "source": f"data:image/jpeg;base64,{base64.b64encode(document_bytes).decode()}"
        }
        
        return await self.post(endpoint, data=data)


class OCRProcessor:
    """
    Generic OCR processor using multiple backends.
    Falls back through available options.
    """
    
    def __init__(self):
        self.available_backends = []
        self._check_backends()
    
    def _check_backends(self):
        """Check which OCR backends are available."""
        try:
            import pytesseract
            self.available_backends.append("tesseract")
        except ImportError:
            pass
        
        try:
            import easyocr
            self.available_backends.append("easyocr")
        except ImportError:
            pass
        
        try:
            import paddleocr
            self.available_backends.append("paddleocr")
        except ImportError:
            pass
    
    async def extract_text_from_image(
        self,
        image_path: str,
        backend: Optional[str] = None
    ) -> Dict:
        """
        Extract text from image using available OCR backend.
        
        Args:
            image_path: Path to image file
            backend: Specific backend to use (auto-detect if None)
        
        Returns:
            Dict with extracted text and metadata
        """
        if not self.available_backends:
            return {
                "success": False,
                "error": "No OCR backend available. Install pytesseract, easyocr, or paddleocr"
            }
        
        backend = backend or self.available_backends[0]
        
        if backend == "tesseract":
            return await self._extract_with_tesseract(image_path)
        elif backend == "easyocr":
            return await self._extract_with_easyocr(image_path)
        elif backend == "paddleocr":
            return await self._extract_with_paddleocr(image_path)
        else:
            return {"success": False, "error": f"Unknown backend: {backend}"}
    
    async def _extract_with_tesseract(self, image_path: str) -> Dict:
        """Extract text using Tesseract OCR."""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            
            return {
                "success": True,
                "text": text,
                "backend": "tesseract",
                "confidence": None  # Tesseract doesn't provide confidence by default
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _extract_with_easyocr(self, image_path: str) -> Dict:
        """Extract text using EasyOCR."""
        try:
            import easyocr
            
            reader = easyocr.Reader(['en'])
            results = reader.readtext(image_path)
            
            text = " ".join([result[1] for result in results])
            confidences = [result[2] for result in results]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                "success": True,
                "text": text,
                "backend": "easyocr",
                "confidence": avg_confidence,
                "detections": len(results)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _extract_with_paddleocr(self, image_path: str) -> Dict:
        """Extract text using PaddleOCR."""
        try:
            from paddleocr import PaddleOCR
            
            ocr = PaddleOCR(use_angle_cls=True, lang='en')
            results = ocr.ocr(image_path, cls=True)
            
            text_lines = []
            for line in results[0]:
                text_lines.append(line[1][0])
            
            text = "\n".join(text_lines)
            
            return {
                "success": True,
                "text": text,
                "backend": "paddleocr",
                "confidence": None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
