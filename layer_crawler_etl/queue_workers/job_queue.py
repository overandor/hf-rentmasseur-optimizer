"""
Queue-based architecture for crawler jobs.
Supports Redis and SQS backends.
"""

import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import boto3
    SQS_AVAILABLE = True
except ImportError:
    SQS_AVAILABLE = False


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class QueueBackend(Enum):
    REDIS = "redis"
    SQS = "sqs"
    MEMORY = "memory"


@dataclass
class Job:
    """Represents a crawl job."""
    job_id: str
    source_id: str
    crawler_type: str
    payload: Dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "source_id": self.source_id,
            "crawler_type": self.crawler_type,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": self.result
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Job":
        return cls(
            job_id=data["job_id"],
            source_id=data["source_id"],
            crawler_type=data["crawler_type"],
            payload=data.get("payload", {}),
            status=JobStatus(data["status"]),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            result=data.get("result")
        )


class MemoryQueue:
    """In-memory queue for testing/local use."""
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.queue: List[str] = []  # Job IDs in priority order
    
    async def enqueue(self, job: Job) -> bool:
        """Add job to queue."""
        self.jobs[job.job_id] = job
        self.queue.append(job.job_id)
        # Sort by priority (higher priority first)
        self.queue.sort(key=lambda jid: -self.jobs[jid].priority)
        return True
    
    async def dequeue(self) -> Optional[Job]:
        """Get next job from queue."""
        if not self.queue:
            return None
        
        job_id = self.queue.pop(0)
        job = self.jobs[job_id]
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.utcnow().isoformat()
        return job
    
    async def update_job(self, job: Job) -> bool:
        """Update job status."""
        if job.job_id in self.jobs:
            self.jobs[job.job_id] = job
            return True
        return False
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self.jobs.get(job_id)
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        return {
            "total_jobs": len(self.jobs),
            "pending": sum(1 for j in self.jobs.values() if j.status == JobStatus.PENDING),
            "processing": sum(1 for j in self.jobs.values() if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in self.jobs.values() if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in self.jobs.values() if j.status == JobStatus.FAILED)
        }


class RedisQueue:
    """Redis-backed queue for distributed processing."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", queue_name: str = "crawler_jobs"):
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed")
        
        self.redis_client = redis.from_url(redis_url)
        self.queue_name = queue_name
        self.job_prefix = f"{queue_name}:job:"
    
    async def enqueue(self, job: Job) -> bool:
        """Add job to Redis queue."""
        # Store job data
        job_key = f"{self.job_prefix}{job.job_id}"
        self.redis_client.set(job_key, json.dumps(job.to_dict()))
        
        # Add to sorted set with priority as score (higher priority = higher score)
        self.redis_client.zadd(self.queue_name, {job.job_id: job.priority})
        
        return True
    
    async def dequeue(self) -> Optional[Job]:
        """Get next job from Redis queue."""
        # Get highest priority job
        result = self.redis_client.zpopmax(self.queue_name)
        if not result:
            return None
        
        job_id = result[0][0].decode() if isinstance(result[0][0], bytes) else result[0][0]
        
        # Get job data
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self.redis_client.get(job_key)
        if not job_data:
            return None
        
        job = Job.from_dict(json.loads(job_data))
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.utcnow().isoformat()
        
        # Update job in Redis
        self.redis_client.set(job_key, json.dumps(job.to_dict()))
        
        return job
    
    async def update_job(self, job: Job) -> bool:
        """Update job in Redis."""
        job_key = f"{self.job_prefix}{job.job_id}"
        job.updated_at = datetime.utcnow().isoformat()
        
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job.completed_at = datetime.utcnow().isoformat()
        
        self.redis_client.set(job_key, json.dumps(job.to_dict()))
        return True
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job from Redis."""
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self.redis_client.get(job_key)
        if not job_data:
            return None
        
        return Job.from_dict(json.loads(job_data))
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        total = self.redis_client.zcard(self.queue_name)
        
        # Count jobs by status (requires scanning all job keys)
        pending = total
        processing = 0
        completed = 0
        failed = 0
        
        for key in self.redis_client.scan_iter(f"{self.job_prefix}*"):
            job_data = self.redis_client.get(key)
            if job_data:
                job = Job.from_dict(json.loads(job_data))
                if job.status == JobStatus.PROCESSING:
                    processing += 1
                elif job.status == JobStatus.COMPLETED:
                    completed += 1
                elif job.status == JobStatus.FAILED:
                    failed += 1
        
        return {
            "total_jobs": total + processing + completed + failed,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed
        }


class JobQueue:
    """Unified job queue interface."""
    
    def __init__(self, backend: QueueBackend = QueueBackend.MEMORY, **kwargs):
        self.backend = backend
        
        if backend == QueueBackend.REDIS:
            self.queue = RedisQueue(**kwargs)
        elif backend == QueueBackend.SQS:
            # TODO: Implement SQS backend
            raise NotImplementedError("SQS backend not yet implemented")
        else:
            self.queue = MemoryQueue()
    
    async def submit_job(
        self,
        source_id: str,
        crawler_type: str,
        payload: Optional[Dict] = None,
        priority: int = 0
    ) -> Job:
        """Submit a new job to the queue."""
        import uuid
        job_id = str(uuid.uuid4())
        
        job = Job(
            job_id=job_id,
            source_id=source_id,
            crawler_type=crawler_type,
            payload=payload or {},
            priority=priority
        )
        
        await self.queue.enqueue(job)
        return job
    
    async def get_next_job(self) -> Optional[Job]:
        """Get the next job to process."""
        return await self.queue.dequeue()
    
    async def update_job_status(self, job: Job, status: JobStatus, result: Optional[Dict] = None, error: Optional[str] = None):
        """Update job status."""
        job.status = status
        job.updated_at = datetime.utcnow().isoformat()
        
        if result:
            job.result = result
        if error:
            job.error = error
        
        if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job.completed_at = datetime.utcnow().isoformat()
        
        await self.queue.update_job(job)
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return await self.queue.get_job(job_id)
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        return self.queue.get_stats()
