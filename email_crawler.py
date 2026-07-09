"""
Real Email Crawler - visits pages, finds @ signs, extracts business emails.
Crawls public directories and firm websites for actual email addresses.

Strategy:
1. Crawl lawyer directories (Martindale, Justia, HG.org, Avvo, SuperLawyers)
   - These have profile pages with real emails
2. Crawl law firm attorney/team listing pages -> individual bio pages
3. Crawl SEC EDGAR filings (contain real contact emails)
4. Crawl hedge fund / VC firm team pages -> individual bios
5. Crawl Crunchbase company pages
6. For each page: extract all text, find @ signs, extract emails, store with URL

Output: link + email pairs, no hallucination.
"""

import os
import re
import json
import time
import sqlite3
import hashlib
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from datetime import datetime
from pathlib import Path
import urllib3
urllib3.disable_warnings()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/email_crawler.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('crawler')

DB_PATH = str(Path(__file__).parent / 'data' / 'crawled_emails.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Obfuscated email patterns: "name at firm dot com", "name [at] firm [dot] com"
OBF_REGEX1 = re.compile(r'(\w+)\s*(?:\[at\]|\(at\)|\bat\b|\@\s)\s*(\w+)\s*(?:\[dot\]|\(dot\)|\.|\sdot\s)\s*([a-zA-Z]{2,4})')

JUNK_DOMAINS = {'wixpress.com', 'example.com', 'sentry.io', 'cloudflare.com', 
                'godaddy.com', 'squarespace.com', 'wordpress.com', 'google.com',
                'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
                'youtube.com', 'github.com', 'medium.com', 'substack.com'}

JUNK_PREFIXES = {'noreply', 'no-reply', 'donotreply', 'do-not-reply', 'test@',
                 'example@', 'info@2x', 'sentry', 'support@cloudflare'}

def is_business_email(email):
    """Check if email looks like a real business email."""
    email = email.lower().strip()
    
    # Filter junk
    for prefix in JUNK_PREFIXES:
        if email.startswith(prefix):
            return False
    
    domain = email.split('@')[1] if '@' in email else ''
    
    if domain in JUNK_DOMAINS:
        return False
    
    # Filter image/file extensions
    if any(email.endswith(ext) for ext in ['.png', '.jpg', '.gif', '.css', '.js', '.ico', '.svg']):
        return False
    
    # Filter very long emails
    if len(email) > 80:
        return False
    
    # Must have a real domain with at least one dot
    if '.' not in domain:
        return False
    
    # Filter emails that are just numbers
    local = email.split('@')[0]
    if local.isdigit():
        return False
    
    return True

def extract_all_emails(html_text):
    """Extract all emails from HTML text, including obfuscated ones."""
    emails = set()
    
    # Standard emails
    for m in EMAIL_REGEX.findall(html_text):
        if is_business_email(m):
            emails.add(m.lower())
    
    # Obfuscated: "name at firm dot com"
    for m in OBF_REGEX1.findall(html_text):
        email = f"{m[0]}@{m[1]}.{m[2]}"
        if is_business_email(email):
            emails.add(email.lower())
    
    # mailto: links
    emails.update(EMAIL_REGEX.findall(html_text))
    
    return list(emails)

# ─── Database ───────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        source_url TEXT NOT NULL,
        page_title TEXT,
        category TEXT,
        organization TEXT,
        name TEXT,
        crawled_at TEXT,
        page_text_snippet TEXT
    )''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_email ON emails(email)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_cat ON emails(category)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_url ON emails(source_url)''')
    conn.commit()
    conn.close()

def save_email(email, source_url, page_title='', category='', org='', name='', snippet=''):
    email = email.lower().strip()
    item_id = hashlib.md5(f"{email}:{source_url}".encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM emails WHERE id=?", (item_id,))
    if c.fetchone():
        conn.close()
        return False
    
    c.execute("""INSERT OR IGNORE INTO emails 
        (id, email, source_url, page_title, category, organization, name, crawled_at, page_text_snippet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, email, source_url, page_title[:200], category, org, name,
         datetime.now().isoformat(), snippet[:300]))
    conn.commit()
    conn.close()
    return True

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM emails")
    total = c.fetchone()[0]
    c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category ORDER BY COUNT(*) DESC")
    cats = c.fetchall()
    c.execute("SELECT COUNT(DISTINCT source_url) FROM emails")
    urls = c.fetchone()[0]
    conn.close()
    return total, cats, urls

# ─── Crawler ────────────────────────────────────────────────────────────────

class Crawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.visited = set()
        self.email_count = 0
    
    def fetch(self, url):
        """Fetch a URL and return (html, soup, emails)."""
        if url in self.visited:
            return None, None, []
        self.visited.add(url)
        
        try:
            r = self.session.get(url, timeout=15, verify=False, allow_redirects=True)
            if r.status_code != 200:
                return None, None, []
            
            html = r.text
            soup = BeautifulSoup(html, 'html.parser')
            emails = extract_all_emails(html)
            
            # Also check for emails in rendered text (some are in JS-rendered content)
            text = soup.get_text()
            extra_emails = extract_all_emails(text)
            emails = list(set(emails + extra_emails))
            
            return html, soup, emails
        except:
            return None, None, []
    
    def get_title(self, soup):
        if soup and soup.title:
            return soup.title.text.strip()
        return ''
    
    def find_links(self, soup, base_url, keywords=None):
        """Find links on page, optionally filtered by keywords in href or text."""
        links = []
        if not soup:
            return links
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text().strip().lower()
            
            # Resolve relative URLs
            full_url = urljoin(base_url, href)
            
            # Same domain only
            if urlparse(full_url).netloc != urlparse(base_url).netloc:
                continue
            
            # Filter by keywords if provided
            if keywords:
                href_lower = href.lower()
                if not any(kw in href_lower or kw in text for kw in keywords):
                    continue
            
            if full_url not in self.visited and full_url not in links:
                links.append(full_url)
        
        return links
    
    def crawl_site(self, base_url, category='', org='', max_pages=30, 
                   link_keywords=None, profile_keywords=None):
        """
        Crawl a site: start at base_url, follow links matching link_keywords,
        extract emails from each page. If profile_keywords given, prioritize
        those pages for email extraction.
        """
        if link_keywords is None:
            link_keywords = ['attorney', 'lawyer', 'partner', 'team', 'people', 
                           'professional', 'staff', 'contact', 'about', 'bio',
                           'profile', 'directory', 'member', 'consultant', 'advisor']
        if profile_keywords is None:
            profile_keywords = ['attorney', 'lawyer', 'partner', 'bio', 'profile',
                              'team', 'people', 'professional', 'member']
        
        to_visit = [base_url]
        pages_crawled = 0
        site_emails = 0
        
        while to_visit and pages_crawled < max_pages:
            url = to_visit.pop(0)
            
            html, soup, emails = self.fetch(url)
            if html is None:
                continue
            
            pages_crawled += 1
            title = self.get_title(soup)
            
            # Save emails from this page
            for email in emails:
                if is_business_email(email):
                    # Try to extract name from page context
                    name = self._extract_name_near_email(soup, email)
                    snippet = soup.get_text()[:300] if soup else ''
                    
                    if save_email(email, url, title, category, org, name, snippet):
                        site_emails += 1
                        self.email_count += 1
                        log.info(f"    ✉️  {email} <- {urlparse(url).path[:50]}")
            
            # Find more links to follow
            links = self.find_links(soup, url, link_keywords)
            
            # Prioritize profile/bio pages
            profile_links = [l for l in links if any(kw in l.lower() for kw in profile_keywords)]
            other_links = [l for l in links if l not in profile_links]
            
            to_visit = profile_links[:10] + to_visit + other_links[:5]
            
            # Be polite
            time.sleep(0.3)
        
        log.info(f"  {org or base_url}: {pages_crawled} pages, {site_emails} emails")
        return site_emails
    
    def _extract_name_near_email(self, soup, email):
        """Try to find a person's name near the email on the page."""
        if not soup:
            return ''
        
        # Look for the email in text and grab surrounding text
        text = soup.get_text()
        idx = text.find(email)
        if idx >= 0:
            # Get 100 chars before the email
            before = text[max(0, idx-100):idx].strip()
            # Look for a name pattern (First Last)
            names = re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+)', before)
            if names:
                return names[-1]
        return ''
    
    def crawl_directory(self, directory_url, category, max_listings=50):
        """
        Crawl a directory listing page, follow each listing to profile pages,
        extract emails from profiles.
        """
        log.info(f"  Directory: {directory_url[:60]}")
        
        html, soup, emails = self.fetch(directory_url)
        if html is None:
            return 0
        
        # Save any direct emails
        count = 0
        for email in emails:
            if is_business_email(email):
                if save_email(email, directory_url, self.get_title(soup), category):
                    count += 1
                    self.email_count += 1
                    log.info(f"    ✉️  {email}")
        
        # Find profile/listing links
        all_links = []
        if soup:
            for a in soup.find_all('a', href=True):
                href = urljoin(directory_url, a['href'])
                text = a.get_text().strip()
                # Profile pages usually have person names as link text
                if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+', text) and len(text) < 50:
                    all_links.append((href, text))
                # Or URLs with profile/attorney/lawyer patterns
                elif any(kw in href.lower() for kw in ['profile', 'attorney', 'lawyer', 
                       'lawfirm', 'detail', 'view', 'member']):
                    all_links.append((href, text))
        
        # Visit each profile page
        for profile_url, link_text in all_links[:max_listings]:
            html2, soup2, profile_emails = self.fetch(profile_url)
            if html2 is None:
                continue
            
            for email in profile_emails:
                if is_business_email(email):
                    name = link_text if re.match(r'^[A-Z]', link_text) else ''
                    if not name:
                        name = self._extract_name_near_email(soup2, email)
                    
                    if save_email(email, profile_url, self.get_title(soup2), category, name=name):
                        count += 1
                        self.email_count += 1
                        log.info(f"    ✉️  {email} ({name})")
            
            time.sleep(0.3)
        
        log.info(f"  Directory result: {count} emails from {len(all_links)} listings")
        return count

# ─── Sources ────────────────────────────────────────────────────────────────

def crawl_ip_lawyers(crawler):
    """Crawl IP lawyer directories and law firm sites."""
    log.info("\n=== IP LAWYERS ===")
    total = 0
    
    # 1. HG.org - IP lawyer directory
    log.info("HG.org IP lawyer directory...")
    for state in ['california', 'new-york', 'texas', 'florida', 'illinois', 'massachusetts', 'washington']:
        url = f"https://www.hg.org/law-firms/intellectual-property/{state}.html"
        total += crawler.crawl_directory(url, 'ip_lawyer', max_listings=20)
        time.sleep(1)
    
    # 2. Justia - IP lawyer directory
    log.info("Justia IP lawyer directory...")
    for state in ['california', 'new-york', 'texas', 'florida']:
        url = f"https://www.justia.com/lawyers/intellectual-property/{state}"
        total += crawler.crawl_directory(url, 'ip_lawyer', max_listings=20)
        time.sleep(1)
    
    # 3. Martindale - IP lawyer directory
    log.info("Martindale IP lawyer directory...")
    url = "https://www.martindale.com/intellectual-property-law/lawyers.htm"
    total += crawler.crawl_directory(url, 'ip_lawyer', max_listings=30)
    time.sleep(1)
    
    # 4. Law firm websites - crawl attorney bio pages
    log.info("Law firm websites (deep crawl)...")
    firms = [
        ("https://www.finnegan.com/en/professionals.html", "Finnegan", "ip_lawyer"),
        ("https://www.fishjackson.com/people", "Fish & Richardson", "ip_lawyer"),
        ("https://www.knobbe.com/people", "Knobbe Martens", "ip_lawyer"),
        ("https://www.wilmerhale.com/en/people", "WilmerHale", "ip_lawyer"),
        ("https://www.ropesgray.com/en/people", "Ropes & Gray", "ip_lawyer"),
        ("https://www.cooley.com/people", "Cooley", "ip_lawyer"),
        ("https://www.perkinscoie.com/en/professionals.html", "Perkins Coie", "ip_lawyer"),
        ("https://www.morganlewis.com/en/people", "Morgan Lewis", "ip_lawyer"),
        ("https://www.kirkland.com/lawyers", "Kirkland & Ellis", "ma_lawyer"),
        ("https://www.latham.com/lawyers", "Latham & Watkins", "ma_lawyer"),
        ("https://www.skadden.com/professionals", "Skadden", "ma_lawyer"),
        ("https://www.davispolk.com/lawyers", "Davis Polk", "ma_lawyer"),
        ("https://www.sullcrom.com/professionals", "Sullivan & Cromwell", "ma_lawyer"),
        ("https://www.jonesday.com/lawyers", "Jones Day", "ip_lawyer"),
        ("https://www.hoganlovells.com/en/people", "Hogan Lovells", "ip_lawyer"),
        ("https://www.bakermckenzie.com/en/people", "Baker McKenzie", "ip_lawyer"),
        ("https://www.whitecase.com/people", "White & Case", "ma_lawyer"),
        ("https://www.goodwinlaw.com/en/people.html", "Goodwin", "ip_lawyer"),
        ("https://www.arnoldporter.com/en/professionals", "Arnold & Porter", "ip_lawyer"),
        ("https://www.crowell.com/people", "Crowell & Moring", "ip_lawyer"),
    ]
    
    for url, org, cat in firms:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=25)
        time.sleep(0.5)
    
    return total

def crawl_hedge_funds(crawler):
    """Crawl hedge fund websites for team/contact emails."""
    log.info("\n=== HEDGE FUNDS ===")
    total = 0
    
    funds = [
        ("https://www.bridgewater.com/our-people", "Bridgewater", "hedge_fund"),
        ("https://www.renaissance.com/contact", "Renaissance Tech", "hedge_fund"),
        ("https://www.aqr.com/About-Us/Our-Team", "AQR Capital", "hedge_fund"),
        ("https://www.two-sigma.com/about/our-people", "Two Sigma", "hedge_fund"),
        ("https://www.baupost.com/contact", "Baupost Group", "hedge_fund"),
        ("https://www.pershingsquarecapital.com/contact", "Pershing Square", "hedge_fund"),
        ("https://www.thirdpoint.com/contact", "Third Point", "hedge_fund"),
        ("https://www.exoduspoint.com/contact", "ExodusPoint", "hedge_fund"),
        ("https://www.maverickcapital.com/contact", "Maverick Capital", "hedge_fund"),
        ("https://www.elliottmgmt.com/contact", "Elliott Management", "hedge_fund"),
        ("https://www.citadel.com/about/our-people", "Citadel", "hedge_fund"),
        ("https://www.point72.com/our-people", "Point72", "hedge_fund"),
        ("https://www.millennium.com/about/our-people", "Millennium", "hedge_fund"),
        ("https://www.balyasny.com/about/our-team", "Balyasny", "hedge_fund"),
        ("https://www.capitalfund.com/contact", "Capital Fund", "hedge_fund"),
        ("https://www.deshaw.com/our-people", "D.E. Shaw", "hedge_fund"),
        ("https://www.tudor.com/contact", "Tudor Investment", "hedge_fund"),
        ("https://www.ochziff.com/contact", "Och-Ziff", "hedge_fund"),
        ("https://www.glenviewcapital.com/contact", "Glenview Capital", "hedge_fund"),
        ("https://www.vikingglobal.com/contact", "Viking Global", "hedge_fund"),
    ]
    
    for url, org, cat in funds:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=20)
        time.sleep(0.5)
    
    return total

def crawl_vc_pe(crawler):
    """Crawl VC and PE firm websites."""
    log.info("\n=== VC / PE FIRMS ===")
    total = 0
    
    firms = [
        ("https://www.sequoiacap.com/people", "Sequoia Capital", "vc_firm"),
        ("https://www.a16z.com/people/", "Andreessen Horowitz", "vc_firm"),
        ("https://www.benchmark.com/people", "Benchmark", "vc_firm"),
        ("https://www.indexventures.com/people", "Index Ventures", "vc_firm"),
        ("https://www.accel.com/people", "Accel", "vc_firm"),
        ("https://www.greylock.com/people", "Greylock", "vc_firm"),
        ("https://www.bv.com/people", "Bessemer Venture", "vc_firm"),
        ("https://www.kpcb.com/people", "Kleiner Perkins", "vc_firm"),
        ("https://www.foundersfund.com/team", "Founders Fund", "vc_firm"),
        ("https://www.lightspeedvp.com/people", "Lightspeed", "vc_firm"),
        ("https://www.blackstone.com/our-people", "Blackstone", "pe_firm"),
        ("https://www.kkr.com/our-people", "KKR", "pe_firm"),
        ("https://www.carlyle.com/our-people", "Carlyle Group", "pe_firm"),
        ("https://www.apollo.com/our-people", "Apollo Global", "pe_firm"),
        ("https://www.baincapital.com/people", "Bain Capital", "pe_firm"),
        ("https://www.tpghome.com/our-people", "TPG", "pe_firm"),
        ("https://www.warburgpincus.com/people", "Warburg Pincus", "pe_firm"),
        ("https://www.nea.com/team", "NEA", "vc_firm"),
        ("https://www.ggvcapital.com/team", "GGV Capital", "vc_firm"),
        ("https://www.ivp.com/team", "IVP", "vc_firm"),
    ]
    
    for url, org, cat in firms:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=20)
        time.sleep(0.5)
    
    return total

def crawl_tech_transfer(crawler):
    """Crawl university tech transfer offices."""
    log.info("\n=== TECH TRANSFER OFFICES ===")
    total = 0
    
    unis = [
        ("https://techtransfer.stanford.edu/people", "Stanford OTL", "tech_transfer"),
        ("https://tlo.mit.edu/people", "MIT TLO", "tech_transfer"),
        ("https://otd.harvard.edu/people", "Harvard OTD", "tech_transfer"),
        ("https://otl.berkeley.edu/people", "Berkeley OTL", "tech_transfer"),
        ("https://techtransfer.columbia.edu/people", "Columbia TTO", "tech_transfer"),
        ("https://ott.yale.edu/people", "Yale OTT", "tech_transfer"),
        ("https://www.princeton.edu/otl/people", "Princeton OTL", "tech_transfer"),
        ("https://techtransfer.umich.edu/people", "Michigan TT", "tech_transfer"),
        ("https://ott.cornell.edu/people", "Cornell OTT", "tech_transfer"),
        ("https://www.upenn.edu/ott/people", "Penn OTT", "tech_transfer"),
    ]
    
    for url, org, cat in unis:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=15)
        time.sleep(0.5)
    
    return total

def crawl_ip_brokers(crawler):
    """Crawl IP broker and marketplace websites."""
    log.info("\n=== IP BROKERS ===")
    total = 0
    
    brokers = [
        ("https://www.icap.com/contact-us", "ICAP Patent Brokerage", "ip_broker"),
        ("https://www.intven.com/contact", "Intellectual Ventures", "ip_broker"),
        ("https://www.yet2.com/about/team", "yet2.com", "ip_broker"),
        ("https://www.tynax.com/about", "Tynax", "ip_broker"),
        ("https://www.ideabuyer.com/about", "IdeaBuyer", "ip_broker"),
        ("https://www.aminnovation.com/about", "Amin Innovation", "ip_broker"),
        ("https://www.ipmarketplace.com/about", "IP Marketplace", "ip_broker"),
        ("https://www.spectrumip.com/about", "Spectrum IP", "ip_broker"),
    ]
    
    for url, org, cat in brokers:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=10)
        time.sleep(0.5)
    
    return total

def crawl_investment_banks(crawler):
    """Crawl investment bank team pages."""
    log.info("\n=== INVESTMENT BANKS ===")
    total = 0
    
    banks = [
        ("https://www.goldmansachs.com/our-firm/people.html", "Goldman Sachs", "investment_bank"),
        ("https://www.jpmorgan.com/our-firm/people", "JP Morgan", "investment_bank"),
        ("https://www.morganstanley.com/people", "Morgan Stanley", "investment_bank"),
        ("https://www.lazard.com/our-people", "Lazard", "investment_bank"),
        ("https://www.evercore.com/our-people", "Evercore", "investment_bank"),
        ("https://www.centerview.com/our-people", "Centerview", "investment_bank"),
        ("https://www.moelis.com/our-people", "Moelis & Co", "investment_bank"),
    ]
    
    for url, org, cat in banks:
        total += crawler.crawl_site(url, category=cat, org=org, max_pages=15)
        time.sleep(0.5)
    
    return total

def crawl_sec_edgar_emails(crawler):
    """Search SEC EDGAR full-text for emails in filings."""
    log.info("\n=== SEC EDGAR FILINGS ===")
    total = 0
    
    # SEC full-text search API
    search_queries = [
        ("intellectual property", "hedge_fund"),
        ("patent acquisition", "ip_lawyer"),
        ("IP portfolio purchase", "ip_broker"),
    ]
    
    for query, cat in search_queries:
        try:
            url = f"https://efts.sec.gov/LATEST/search-index?q=%22{quote(query)}%22&dateRange=custom&startdt=2024-01-01&forms=8-K,DEF-14A"
            r = crawler.session.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                hits = data.get('hits', {}).get('hits', [])[:20]
                for hit in hits:
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{hit['_source']['entity_id']}/{hit['_source']['file_name']}"
                    html, soup, emails = crawler.fetch(filing_url)
                    for email in emails:
                        if is_business_email(email):
                            if save_email(email, filing_url, hit['_source'].get('entity_name', ''), cat):
                                total += 1
                                crawler.email_count += 1
                                log.info(f"    ✉️  {email} (SEC filing)")
                    time.sleep(0.5)
        except Exception as e:
            log.error(f"  SEC search: {e}")
    
    log.info(f"  SEC EDGAR: {total} emails")
    return total

# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("EMAIL CRAWLER - VISITING PAGES, FINDING @ SIGNS")
    log.info("=" * 60)
    
    init_db()
    crawler = Crawler()
    
    grand_total = 0
    
    # Run all crawlers
    grand_total += crawl_ip_lawyers(crawler)
    grand_total += crawl_hedge_funds(crawler)
    grand_total += crawl_vc_pe(crawler)
    grand_total += crawl_tech_transfer(crawler)
    grand_total += crawl_ip_brokers(crawler)
    grand_total += crawl_investment_banks(crawler)
    grand_total += crawl_sec_edgar_emails(crawler)
    
    # Stats
    total, cats, urls = get_stats()
    log.info("\n" + "=" * 60)
    log.info(f"CRAWL COMPLETE")
    log.info(f"Total emails: {total}")
    log.info(f"Unique source URLs: {urls}")
    log.info(f"Pages visited: {len(crawler.visited)}")
    log.info("=" * 60)
    log.info("By category:")
    for cat, count in cats:
        log.info(f"  {cat}: {count}")
    
    # Export
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, source_url, page_title, category, organization, name FROM emails ORDER BY category, email")
    rows = c.fetchall()
    conn.close()
    
    # JSON export
    export_path = str(Path(__file__).parent / 'data' / 'crawled_emails.json')
    with open(export_path, 'w') as f:
        json.dump([{
            'email': r[0], 'source_url': r[1], 'page_title': r[2],
            'category': r[3], 'organization': r[4], 'name': r[5]
        } for r in rows], f, indent=2)
    
    # CSV export
    import csv
    csv_path = str(Path(__file__).parent / 'data' / 'crawled_emails.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['email', 'source_url', 'page_title', 'category', 'organization', 'name'])
        for r in rows:
            w.writerow(r)
    
    log.info(f"\nExported {len(rows)} emails:")
    log.info(f"  JSON: {export_path}")
    log.info(f"  CSV: {csv_path}")
    
    # Print sample
    log.info(f"\nSample emails (first 20):")
    for r in rows[:20]:
        log.info(f"  {r[0]} | {r[3]} | {r[4] or ''} | {r[1][:60]}")

if __name__ == "__main__":
    main()
