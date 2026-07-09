"""
Example usage of Layer Crawler ETL Engine
"""
import asyncio
from pathlib import Path
from layer_crawler_etl import (
    ETLPipeline,
    Source,
    SubjectType,
    CodeCrawler,
    DependencyCrawler,
    LicenseCrawler,
    TestBuildCrawler,
    SecuritySecretsCrawler,
    DocsClaimsCrawler,
    BrowserRuntimeCrawler
)

async def main():
    # Initialize pipeline
    output_dir = Path("receipts")
    pipeline = ETLPipeline(output_dir)
    
    # Register crawlers
    pipeline.register_crawler(SubjectType.CODE, CodeCrawler())
    pipeline.register_crawler(SubjectType.DEPENDENCY, DependencyCrawler())
    pipeline.register_crawler(SubjectType.LICENSE, LicenseCrawler())
    pipeline.register_crawler(SubjectType.TEST_BUILD, TestBuildCrawler())
    pipeline.register_crawler(SubjectType.SECURITY_SECRETS, SecuritySecretsCrawler())
    pipeline.register_crawler(SubjectType.DOCS_CLAIMS, DocsClaimsCrawler())
    pipeline.register_crawler(SubjectType.BROWSER_RUNTIME, BrowserRuntimeCrawler(headless=True))
    
    # Define sources
    sources = [
        Source(type="repo", location=".", metadata={"name": "email-crawler"}),
        # Source(type="url", location="http://localhost:7860", metadata={"name": "webapp"}),
    ]
    
    # Run pipeline
    receipt = await pipeline.run(sources, system="Membra Desktop Operator 2")
    
    # Print results
    print("\n" + "="*60)
    print("RECEIPT GENERATED")
    print("="*60)
    print(f"System: {receipt.system}")
    print(f"Subject: {receipt.subject}")
    print(f"Timestamp: {receipt.timestamp}")
    print(f"Hash: {receipt.hash}")
    print("\nSignals:")
    for key, value in receipt.signals.items():
        print(f"  {key}: {value}")
    print("\nScores:")
    for key, value in receipt.scores.items():
        print(f"  {key}: {value}")
    print(f"\nArtifact: {receipt.artifact}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
