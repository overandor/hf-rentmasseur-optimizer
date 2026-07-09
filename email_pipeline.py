"""
24/7 Public Email Scraping & Crawling Pipeline
Scrapes public sources for hedge fund IP purchaser intelligence.
No login required - all public data sources.

Sources:
1. SEC EDGAR - public filings (13F, 8-K, S-1, etc.)
2. Google Groups public archives
3. RSS feeds (financial news, IP news)
4. Public mailing list archives (mailman, pipermail)
5. Patent assignment searches (USPTO)
6. Public Crunchbase data
7. LinkedIn public posts
8. Hacker News (YC)
9. Reddit (r/investing, r/hedgefunds, r/IP)
10. SEC full-text search
"""

import os
import re
import json
import time
import sqlite3
import hashlib
import logging
import asyncio
import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import schedule
import threading

# LLM
import base64
import pytesseract
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/email_pipeline.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('pipeline')

DB_PATH = str(Path(__file__).parent / 'data' / 'email_intel.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ─── Database ───────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scraped_items (
        id TEXT PRIMARY KEY,
        source TEXT,
        url TEXT,
        title TEXT,
        content TEXT,
        author TEXT,
        date TEXT,
        tags TEXT,
        llm_analysis TEXT,
        relevance_score INTEGER DEFAULT 0,
        scraped_at TEXT,
        processed INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pipeline_stats (
        source TEXT,
        items_scraped INTEGER DEFAULT 0,
        items_flagged INTEGER DEFAULT 0,
        last_run TEXT,
        PRIMARY KEY (source)
    )''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_relevance ON scraped_items(relevance_score DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_source ON scraped_items(source)''')
    conn.commit()
    conn.close()
    log.info(f"DB initialized: {DB_PATH}")

def item_exists(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM scraped_items WHERE id=?", (item_id,))
    r = c.fetchone()
    conn.close()
    return r is not None

def save_item(source, url, title, content, author='', date='', tags=None):
    item_id = hashlib.md5(f"{url}:{title}".encode()).hexdigest()
    if item_exists(item_id):
        return None
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO scraped_items 
        (id, source, url, title, content, author, date, tags, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, source, url, title[:500], content[:5000], author, date,
         json.dumps(tags or []), datetime.now().isoformat()))
    c.execute("""INSERT OR REPLACE INTO pipeline_stats (source, items_scraped, last_run)
        VALUES (?, COALESCE((SELECT items_scraped FROM pipeline_stats WHERE source=?), 0) + 1, ?)""",
        (source, source, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return item_id

def update_analysis(item_id, analysis, score):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE scraped_items SET llm_analysis=?, relevance_score=?, processed=1 WHERE id=?",
              (analysis, score, item_id))
    conn.commit()
    conn.close()

def get_unprocessed(limit=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, source, url, title, content FROM scraped_items WHERE processed=0 LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# ─── LLM Analysis ───────────────────────────────────────────────────────────

class LLMAnalyzer:
    def __init__(self):
        self.url = "http://localhost:11434/api/generate"
        self.model = "llama3.1:latest"
        self._check()
    
    def _check(self):
        try:
            r = requests.post(self.url, json={"model": self.model, "prompt": "OK", "stream": False}, timeout=10)
            log.info(f"Ollama: {'OK' if r.status_code == 200 else 'ERROR'}")
        except:
            log.warning("Ollama not running - analysis will be skipped")
    
    def analyze(self, title, content):
        """Classify content for hedge fund IP relevance."""
        prompt = f"""Analyze this content for hedge fund intellectual property (IP) purchasing activity.

Title: {title}
Content: {content[:1500]}

Respond in JSON format:
{{
  "relevance_score": 0-10,
  "category": "hedge_fund|ip_purchase|patent|acquisition|investment|none",
  "entities": ["company names", "fund names", "people"],
  "summary": "one line summary",
  "action": "monitor|investigate|ignore"
}}

Only output the JSON."""

        try:
            r = requests.post(self.url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=30)
            if r.status_code == 200:
                text = r.json().get("response", "")
                try:
                    return json.loads(text)
                except:
                    # Try to extract JSON
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        return json.loads(match.group())
                    return {"relevance_score": 0, "category": "none", "summary": text[:100], "action": "ignore"}
        except Exception as e:
            log.error(f"LLM error: {e}")
        return None

# ─── Scrapers ───────────────────────────────────────────────────────────────

class SECScraper:
    """Scrape SEC EDGAR for hedge fund filings."""
    
    def __init__(self):
        self.base = "https://www.sec.gov"
        self.headers = {"User-Agent": "Research research@example.com", "Accept-Encoding": "gzip, deflate"}
        self.last_run = None
    
    async def scrape(self):
        log.info("SEC: scraping EDGAR...")
        items = []
        
        # 1. Recent 13F filings (hedge fund portfolios)
        try:
            r = requests.get(f"{self.base}/cgi-bin/browse-edgar",
                params={"action": "getcurrent", "type": "13F", "output": "atom", "count": 40},
                headers=self.headers, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'xml')
                for entry in soup.find_all('entry'):
                    title = entry.find('title').text if entry.find('title') else ''
                    link = entry.find('link').get('href') if entry.find('link') else ''
                    updated = entry.find('updated').text if entry.find('updated') else ''
                    content = entry.find('content').text[:500] if entry.find('content') else ''
                    
                    item_id = save_item('sec_13f', link, title, content, date=updated,
                                       tags=['13f', 'hedge_fund', 'portfolio'])
                    if item_id:
                        items.append(item_id)
            log.info(f"SEC 13F: {len(items)} new items")
        except Exception as e:
            log.error(f"SEC 13F error: {e}")
        
        # 2. Recent 8-K filings (acquisitions, IP transfers)
        try:
            r = requests.get(f"{self.base}/cgi-bin/browse-edgar",
                params={"action": "getcurrent", "type": "8-K", "output": "atom", "count": 40},
                headers=self.headers, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'xml')
                count = 0
                for entry in soup.find_all('entry'):
                    title = entry.find('title').text if entry.find('title') else ''
                    link = entry.find('link').get('href') if entry.find('link') else ''
                    updated = entry.find('updated').text if entry.find('updated') else ''
                    
                    # Filter for IP/acquisition related
                    if any(kw in title.lower() for kw in ['acquisit', 'intellectual', 'patent', 'license', 'merger', 'asset']):
                        item_id = save_item('sec_8k', link, title, title, date=updated,
                                           tags=['8k', 'acquisition', 'ip'])
                        if item_id:
                            items.append(item_id)
                            count += 1
                log.info(f"SEC 8-K (IP/acq): {count} new items")
        except Exception as e:
            log.error(f"SEC 8-K error: {e}")
        
        # 3. Full-text search for IP purchases
        try:
            r = requests.get(f"{self.base}/cgi-bin/srqsb",
                params={"text": "intellectual property purchase", "first": "2024", "last": "", "output": "atom"},
                headers=self.headers, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'xml')
                for entry in soup.find_all('entry')[:20]:
                    title = entry.find('title').text if entry.find('title') else ''
                    link = entry.find('link').get('href') if entry.find('link') else ''
                    item_id = save_item('sec_fts', link, title, title, tags=['full_text', 'ip_purchase'])
                    if item_id:
                        items.append(item_id)
        except Exception as e:
            log.error(f"SEC FTS error: {e}")
        
        self.last_run = datetime.now()
        return items

class RSSScraper:
    """Scrape financial/IP news RSS feeds."""
    
    FEEDS = [
        # Financial / Hedge Fund
        ("https://www.hedgeweek.com/feed/", "hedgeweek", ["hedge_fund", "news"]),
        ("https://www.institutionalinvestor.com/rss", "instinvestor", ["hedge_fund", "institutional"]),
        ("https://www.reuters.com/finance/feeds", "reuters_fin", ["finance", "news"]),
        ("https://feeds.bloomberg.com/markets/news.rss", "bloomberg", ["finance", "markets"]),
        # IP / Patents
        ("https://www.ipwatchdog.com/feed/", "ipwatchdog", ["ip", "patent", "legal"]),
        ("https://www.patentlyo.com/feed", "patentlyo", ["patent", "ip"]),
        # M&A / Acquisitions
        ("https://www.mergersandacquisitions.net/feeds/all", "ma_feed", ["merger", "acquisition"]),
        # Tech / IP transactions
        ("https://techcrunch.com/feed/", "techcrunch", ["tech", "startup"]),
        ("https://www.theinformation.com/feed", "theinfo", ["tech", "finance"]),
        # SEC / Legal
        ("https://www.law360.com/feeds/articles", "law360", ["legal", "ip"]),
    ]
    
    async def scrape(self):
        log.info("RSS: scraping feeds...")
        items = []
        
        for url, source_name, tags in self.FEEDS:
            try:
                feed = feedparser.parse(url)
                count = 0
                for entry in feed.entries[:15]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    content = entry.get('summary', entry.get('description', ''))[:1000]
                    author = entry.get('author', '')
                    date = entry.get('published', '')
                    
                    item_id = save_item(f'rss_{source_name}', link, title, content, author, date, tags)
                    if item_id:
                        items.append(item_id)
                        count += 1
                log.info(f"  {source_name}: {count} new")
            except Exception as e:
                log.error(f"  {source_name}: {e}")
        
        return items

class GoogleGroupsScraper:
    """Scrape public Google Groups archives."""
    
    GROUPS = [
        "comp.patents",
        "misc.invest.funds",
        "alt.invest.hedge-funds",
        "comp.intellectual-property",
    ]
    
    async def scrape(self):
        log.info("Google Groups: scraping...")
        items = []
        
        for group in self.GROUPS:
            try:
                url = f"https://groups.google.com/g/{group}"
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    # Google Groups uses JS rendering, try API
                    pass
                
                # Try Google Groups RSS
                rss_url = f"https://groups.google.com/g/{group}/feed/rss_v2_0/topics.xml"
                feed = feedparser.parse(rss_url)
                count = 0
                for entry in feed.entries[:10]:
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    content = entry.get('summary', '')[:1000]
                    item_id = save_item(f'ggroups_{group}', link, title, content, tags=['google_groups', group])
                    if item_id:
                        items.append(item_id)
                        count += 1
                log.info(f"  {group}: {count} new")
            except Exception as e:
                log.error(f"  {group}: {e}")
        
        return items

class RedditScraper:
    """Scrape Reddit public posts."""
    
    SUBREDDITS = [
        ("investing", ["investing", "finance"]),
        ("hedgefunds", ["hedge_fund"]),
        ("WallStreetBets", ["trading", "finance"]),
        ("patents", ["patent", "ip"]),
        ("IP", ["intellectual_property"]),
        ("Mergers", ["merger", "acquisition"]),
        ("stocks", ["stocks", "finance"]),
    ]
    
    async def scrape(self):
        log.info("Reddit: scraping...")
        items = []
        headers = {"User-Agent": "IntelPipeline/1.0"}
        
        for sub, tags in self.SUBREDDITS:
            try:
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    count = 0
                    for post in data['data']['children']:
                        p = post['data']
                        title = p['title']
                        link = f"https://reddit.com{p['permalink']}"
                        content = p.get('selftext', '')[:1000]
                        author = p.get('author', '')
                        date = str(p.get('created_utc', ''))
                        
                        item_id = save_item(f'reddit_{sub}', link, title, content, author, date, tags)
                        if item_id:
                            items.append(item_id)
                            count += 1
                    log.info(f"  r/{sub}: {count} new")
            except Exception as e:
                log.error(f"  r/{sub}: {e}")
        
        return items

class HackerNewsScraper:
    """Scrape Hacker News for IP/finance related posts."""
    
    async def scrape(self):
        log.info("HN: scraping...")
        items = []
        
        try:
            # Search for IP/hedge fund related stories
            for query in ["intellectual property", "hedge fund", "patent purchase", "IP acquisition"]:
                r = requests.get(f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage=20",
                    timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    count = 0
                    for hit in data['hits']:
                        title = hit.get('title', '')
                        url = hit.get('url', f"https://news.ycombinator.com/item?id={hit['objectID']}")
                        content = hit.get('story_text', '')[:1000]
                        date = str(hit.get('created_at', ''))
                        
                        item_id = save_item('hackernews', url, title, content, date=date,
                                           tags=['hn', query.replace(' ', '_')])
                        if item_id:
                            items.append(item_id)
                            count += 1
                    log.info(f"  HN '{query}': {count} new")
        except Exception as e:
            log.error(f"  HN: {e}")
        
        return items

class USPTOScraper:
    """Scrape USPTO patent assignment data."""
    
    async def scrape(self):
        log.info("USPTO: scraping patent assignments...")
        items = []
        
        try:
            # USPTO patent assignment search
            url = "https://assignment.uspto.gov/search/assignment"
            r = requests.get(url, params={"q": "*", "rows": 50, "sort": "recordedDate desc"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                count = 0
                for assign in data.get('data', [])[:30]:
                    title = f"Patent assignment: {assign.get('assignorName', '')} -> {assign.get('assigneeName', '')}"
                    content = json.dumps(assign)[:1000]
                    link = f"https://assignment.uspto.gov/search/assignment?id={assign.get('id', '')}"
                    
                    item_id = save_item('uspto', link, title, content, tags=['patent', 'assignment', 'ip'])
                    if item_id:
                        items.append(item_id)
                        count += 1
                log.info(f"  USPTO: {count} new")
        except Exception as e:
            log.error(f"  USPTO: {e}")
        
        return items

class PublicMailingListScraper:
    """Scrape public mailing list archives (pipermail/mailman)."""
    
    LISTS = [
        ("https://mail.python.org/pipermail/python-list/", "python-list"),
        ("https://www.openssl.org/lists/openssl-users/", "openssl-users"),
        # Add more public lists as needed
    ]
    
    async def scrape(self):
        log.info("Mailing lists: scraping...")
        items = []
        
        for url, name in self.LISTS:
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    # Find thread links
                    for link in soup.find_all('a', href=True)[:20]:
                        href = link.get('href')
                        if href and not href.startswith('?') and not href.startswith('#'):
                            full_url = urljoin(url, href)
                            title = link.text.strip()
                            if title and len(title) > 5:
                                item_id = save_item(f'maillist_{name}', full_url, title, '',
                                                   tags=['mailing_list', name])
                                if item_id:
                                    items.append(item_id)
            except Exception as e:
                log.error(f"  {name}: {e}")
        
        return items

class CrunchbaseScraper:
    """Scrape public Crunchbase data via API."""
    
    async def scrape(self):
        log.info("Crunchbase: scraping...")
        items = []
        
        try:
            # Crunchbase public API (limited but free)
            # Search for recent IP acquisitions
            for query in ["intellectual property acquisition", "patent purchase", "IP portfolio"]:
                url = f"https://www.crunchbase.com/textsearch?q={query}"
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                # Crunchbase requires JS - try their public RSS
                pass
        except:
            pass
        
        return items

# ─── Pipeline Orchestration ─────────────────────────────────────────────────

class Pipeline:
    def __init__(self):
        self.llm = LLMAnalyzer()
        self.scrapers = [
            SECScraper(),
            RSSScraper(),
            RedditScraper(),
            HackerNewsScraper(),
            USPTOScraper(),
            GoogleGroupsScraper(),
            PublicMailingListScraper(),
        ]
        self.running = False
    
    async def run_scrape_cycle(self):
        """Run one full scrape cycle across all sources."""
        log.info("=" * 50)
        log.info("STARTING SCRAPE CYCLE")
        log.info("=" * 50)
        
        total_new = 0
        for scraper in self.scrapers:
            try:
                items = await scraper.scrape()
                total_new += len(items)
            except Exception as e:
                log.error(f"{scraper.__class__.__name__}: {e}")
        
        log.info(f"Scrape cycle complete: {total_new} new items")
        return total_new
    
    async def run_analysis_cycle(self):
        """Process unprocessed items with LLM."""
        unprocessed = get_unprocessed(50)
        if not unprocessed:
            return 0
        
        log.info(f"Analyzing {len(unprocessed)} items...")
        flagged = 0
        
        for item_id, source, url, title, content in unprocessed:
            analysis = self.llm.analyze(title, content)
            if analysis:
                score = analysis.get('relevance_score', 0)
                category = analysis.get('category', 'none')
                action = analysis.get('action', 'ignore')
                
                update_analysis(item_id, json.dumps(analysis), score)
                
                if score >= 6 or action == 'monitor' or action == 'investigate':
                    flagged += 1
                    log.info(f"  ⚠️  FLAGGED [{score}/10] {category}: {title[:60]}")
                    log.info(f"     Entities: {analysis.get('entities', [])}")
                    log.info(f"     Summary: {analysis.get('summary', '')}")
                    log.info(f"     URL: {url}")
        
        log.info(f"Analysis complete: {flagged}/{len(unprocessed)} flagged")
        return flagged
    
    async def run_forever(self):
        """Run the pipeline 24/7."""
        self.running = True
        log.info("Pipeline started - running 24/7")
        
        # Initial scrape
        await self.run_scrape_cycle()
        await self.run_analysis_cycle()
        
        cycle = 0
        while self.running:
            cycle += 1
            wait_minutes = 30  # Scrape every 30 minutes
            log.info(f"Next cycle in {wait_minutes} minutes (cycle #{cycle})")
            
            # Wait with periodic checks
            for _ in range(wait_minutes * 60):
                if not self.running:
                    break
                await asyncio.sleep(1)
            
            if not self.running:
                break
            
            await self.run_scrape_cycle()
            await self.run_analysis_cycle()
            
            # Print stats every 4 cycles (2 hours)
            if cycle % 4 == 0:
                self.print_stats()
    
    def print_stats(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM scraped_items")
        total = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM scraped_items WHERE relevance_score >= 6")
        flagged = c.fetchone()[0]
        
        c.execute("SELECT source, items_scraped, last_run FROM pipeline_stats ORDER BY items_scraped DESC")
        stats = c.fetchall()
        
        c.execute("SELECT title, url, relevance_score, llm_analysis FROM scraped_items WHERE relevance_score >= 6 ORDER BY relevance_score DESC LIMIT 10")
        top = c.fetchall()
        
        conn.close()
        
        log.info("\n" + "=" * 50)
        log.info("PIPELINE STATISTICS")
        log.info("=" * 50)
        log.info(f"Total items: {total}")
        log.info(f"Flagged (score>=6): {flagged}")
        log.info("\nBy source:")
        for source, count, last in stats:
            log.info(f"  {source}: {count} items (last: {last[:19] if last else 'never'})")
        log.info("\nTop flagged items:")
        for title, url, score, analysis in top:
            log.info(f"  [{score}] {title[:60]}")
            log.info(f"       {url}")
        log.info("=" * 50)
    
    def stop(self):
        self.running = False
        log.info("Pipeline stopping...")

# ─── Main ───────────────────────────────────────────────────────────────────

async def main():
    init_db()
    pipeline = Pipeline()
    
    try:
        await pipeline.run_forever()
    except KeyboardInterrupt:
        pipeline.stop()
        pipeline.print_stats()

if __name__ == "__main__":
    asyncio.run(main())
