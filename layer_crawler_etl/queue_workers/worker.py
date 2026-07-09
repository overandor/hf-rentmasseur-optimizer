"""
Worker process for executing crawl jobs from the queue.
"""

import asyncio
import logging
from typing import Optional, Dict
from pathlib import Path

from layer_crawler_etl.queue_workers.job_queue import JobQueue, Job, JobStatus, QueueBackend
from layer_crawler_etl.layer0_source_registry.source_registry import SourceRegistry, Source
from layer_crawler_etl.layer1_crawlers import (
    CodeCrawler, DependencyCrawler, LicenseCrawler, 
    SecurityCrawler, TestBuildCrawler, BrowserRuntimeCrawler
)
from layer_crawler_etl.layer2_etl import Extractor, Transformer, Loader
from layer_crawler_etl.layer3_scoring import Scorer
from layer_crawler_etl.layer4_action import ActionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CrawlerWorker:
    """Worker that processes crawl jobs from the queue."""
    
    CRAWLER_MAP = {
        "code": CodeCrawler,
        "dependency": DependencyCrawler,
        "license": LicenseCrawler,
        "security": SecurityCrawler,
        "test_build": TestBuildCrawler,
        "browser_runtime": BrowserRuntimeCrawler
    }
    
    def __init__(
        self,
        job_queue: JobQueue,
        source_registry: SourceRegistry,
        storage_path: Optional[Path] = None
    ):
        self.job_queue = job_queue
        self.source_registry = source_registry
        self.storage_path = storage_path or Path("layer_crawler_etl/storage")
        
        # Initialize ETL components
        self.extractor = Extractor(storage_path)
        self.transformer = Transformer()
        self.loader = Loader(storage_path / "normalized")
        self.scorer = Scorer()
        self.action_engine = ActionEngine()
        
        # Initialize crawlers
        self.crawlers = {
            crawler_type: crawler_class(storage_path)
            for crawler_type, crawler_class in self.CRAWLER_MAP.items()
        }
    
    async def process_job(self, job: Job) -> bool:
        """Process a single crawl job."""
        logger.info(f"Processing job {job.job_id} for source {job.source_id}")
        
        try:
            # Get source from registry
            source = self.source_registry.get_source(job.source_id)
            if not source:
                raise ValueError(f"Source {job.source_id} not found in registry")
            
            # Get appropriate crawler
            crawler_type = job.crawler_type
            if crawler_type not in self.crawlers:
                raise ValueError(f"Unknown crawler type: {crawler_type}")
            
            crawler = self.crawlers[crawler_type]
            
            # Validate source
            if not crawler.validate_source(source):
                raise ValueError(f"Source not valid for crawler {crawler_type}")
            
            # Execute crawl
            logger.info(f"Crawling source {source.source_id} with {crawler_type}")
            crawl_result = await crawler.crawl(source)
            
            # Extract
            logger.info(f"Extracting data from crawl result")
            extracted = self.extractor.extract_from_crawl_result(crawl_result)
            
            # Transform
            logger.info(f"Transforming extracted data")
            normalized = self.transformer.transform(extracted)
            
            # Load
            logger.info(f"Loading normalized record")
            load_result = self.loader.load(normalized)
            
            # Score
            logger.info(f"Scoring normalized record")
            score_result = self.scorer.score(normalized)
            
            # Generate actions
            logger.info(f"Generating actions")
            action_result = self.action_engine.generate_actions(score_result, normalized.data)
            
            # Update job with result
            result = {
                "crawl_success": crawl_result.success,
                "load_success": load_result.records_loaded > 0,
                "evidence_score": score_result.evidence_score,
                "prod_score": score_result.prod_score,
                "overall_score": score_result.overall_score,
                "risk_level": score_result.risk_level.value,
                "actions_count": len(action_result.actions_generated),
                "blocked": len(action_result.blocked_claims) > 0
            }
            
            await self.job_queue.update_job_status(
                job,
                JobStatus.COMPLETED,
                result=result
            )
            
            # Update source status in registry
            if crawl_result.success:
                from layer_crawler_etl.layer0_source_registry.source_registry import SourceStatus
                self.source_registry.update_source_status(source.source_id, SourceStatus.COMPLETED)
            else:
                from layer_crawler_etl.layer0_source_registry.source_registry import SourceStatus
                self.source_registry.update_source_status(source.source_id, SourceStatus.FAILED)
            
            logger.info(f"Job {job.job_id} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {str(e)}")
            
            # Check if we should retry
            job.retry_count += 1
            if job.retry_count < job.max_retries:
                logger.info(f"Retrying job {job.job_id} (attempt {job.retry_count}/{job.max_retries})")
                await self.job_queue.update_job_status(job, JobStatus.RETRY, error=str(e))
                return False
            else:
                logger.error(f"Job {job.job_id} failed after {job.max_retries} retries")
                await self.job_queue.update_job_status(job, JobStatus.FAILED, error=str(e))
                
                # Update source status
                from layer_crawler_etl.layer0_source_registry.source_registry import SourceStatus
                self.source_registry.update_source_status(job.source_id, SourceStatus.FAILED)
                
                return False
    
    async def run(self, poll_interval: float = 1.0):
        """Run worker continuously, polling for jobs."""
        logger.info("Starting crawler worker")
        
        while True:
            try:
                job = await self.job_queue.get_next_job()
                
                if job:
                    await self.process_job(job)
                else:
                    # No jobs available, wait
                    await asyncio.sleep(poll_interval)
                    
            except Exception as e:
                logger.error(f"Worker error: {str(e)}")
                await asyncio.sleep(poll_interval)
    
    async def run_batch(self, max_jobs: int = 10) -> Dict:
        """Run worker for a batch of jobs."""
        logger.info(f"Starting batch processing (max {max_jobs} jobs)")
        
        processed = 0
        succeeded = 0
        failed = 0
        
        while processed < max_jobs:
            job = await self.job_queue.get_next_job()
            
            if not job:
                logger.info("No more jobs in queue")
                break
            
            success = await self.process_job(job)
            processed += 1
            
            if success:
                succeeded += 1
            else:
                failed += 1
        
        logger.info(f"Batch processing complete: {processed} jobs, {succeeded} succeeded, {failed} failed")
        
        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed
        }


async def main():
    """Main entry point for worker."""
    # Initialize components
    source_registry = SourceRegistry()
    job_queue = JobQueue(backend=QueueBackend.MEMORY)
    worker = CrawlerWorker(job_queue, source_registry)
    
    # Run worker
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
