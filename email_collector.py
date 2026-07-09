"""
10,000+ Email Collection Pipeline
Scrapes public sources for email addresses across 10 categories:
1. Hedge Funds
2. Intellectual Property Lawyers
3. Patent Attorneys
4. Private Equity Firms
5. Venture Capital Firms
6. M&A / Corporate Lawyers
7. Investment Banks
8. Tech Transfer Offices (Universities)
9. Patent Brokers / IP Marketplaces
10. IP Valuation Firms

Sources: SEC EDGAR, public directories, law firm sites, bar associations,
fund websites, Crunchbase, university tech transfer pages, etc.
"""

import os
import re
import json
import time
import sqlite3
import hashlib
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/email_collector.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('collector')

DB_PATH = str(Path(__file__).parent / 'data' / 'collected_emails.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# ─── Database ───────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY,
        email TEXT,
        name TEXT,
        organization TEXT,
        category TEXT,
        subcategory TEXT,
        source_url TEXT,
        source_type TEXT,
        title TEXT,
        phone TEXT,
        address TEXT,
        country TEXT,
        collected_at TEXT,
        verified INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_email ON emails(email)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_category ON emails(category)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_org ON emails(organization)''')
    conn.commit()
    conn.close()
    log.info(f"DB: {DB_PATH}")

def save_email(email, name='', org='', category='', subcategory='', source_url='', 
               source_type='', title='', phone='', address='', country=''):
    email = email.lower().strip()
    item_id = hashlib.md5(f"{email}:{org}".encode()).hexdigest()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM emails WHERE id=?", (item_id,))
    if c.fetchone():
        conn.close()
        return False
    
    c.execute("""INSERT OR IGNORE INTO emails 
        (id, email, name, organization, category, subcategory, source_url, source_type, 
         title, phone, address, country, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, email, name, org, category, subcategory, source_url, source_type,
         title, phone, address, country, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True

def get_counts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category ORDER BY COUNT(*) DESC")
    cats = c.fetchall()
    c.execute("SELECT COUNT(*) FROM emails")
    total = c.fetchone()[0]
    conn.close()
    return total, cats

# ─── Helpers ────────────────────────────────────────────────────────────────

def extract_emails_from_text(text):
    return list(set(EMAIL_REGEX.findall(text)))

def extract_emails_from_page(url, headers=None):
    """Fetch a page and extract all email addresses."""
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15, verify=False)
        if r.status_code == 200:
            emails = extract_emails_from_text(r.text)
            # Also check mailto: links
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                if a['href'].startswith('mailto:'):
                    e = a['href'][7:].split('?')[0]
                    if EMAIL_REGEX.match(e):
                        emails.append(e.lower())
            return list(set(emails)), r.text
    except:
        pass
    return [], ''

def clean_email(email):
    """Filter out junk emails."""
    junk = ['sentry', 'example.com', 'test@', 'noreply', 'no-reply', 'donotreply',
            'wixpress', 'godaddy', 'squarespace', 'wordpress', 'cloudflare',
            '.png', '.jpg', '.gif', '.css', '.js', '@sentry', '@2x']
    for j in junk:
        if j in email.lower():
            return None
    if email.endswith('.png') or email.endswith('.jpg') or email.endswith('.gif'):
        return None
    if len(email) > 100:
        return None
    return email

# ─── SEC EDGAR Scraper ──────────────────────────────────────────────────────

def scrape_sec_edgar():
    """SEC filings contain contact emails for hedge funds and investment firms."""
    log.info("SEC EDGAR: scraping filings for emails...")
    collected = 0
    
    headers = {"User-Agent": "Research research@example.com"}
    
    # Get recent filings from investment companies / hedge funds
    filing_types = ["13F", "D", "N-CSR", "ADV"]
    
    for ftype in filing_types:
        try:
            r = requests.get("https://www.sec.gov/cgi-bin/browse-edgar",
                params={"action": "getcurrent", "type": ftype, "output": "atom", "count": 100},
                headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            
            soup = BeautifulSoup(r.text, 'xml')
            for entry in soup.find_all('entry')[:50]:
                link = entry.find('link')
                if not link:
                    continue
                filing_url = link.get('href', '')
                title = entry.find('title').text if entry.find('title') else ''
                
                # Get filing index page
                try:
                    idx_url = filing_url.replace(filing_url.split('/')[-1], '')
                    r2 = requests.get(idx_url, headers=headers, timeout=10)
                    if r2.status_code == 200:
                        emails, _ = extract_emails_from_page(idx_url, headers)
                        for e in emails:
                            e = clean_email(e)
                            if e:
                                if save_email(e, org=title[:100], category='hedge_fund',
                                           subcategory=ftype, source_url=idx_url,
                                           source_type='sec_edgar'):
                                    collected += 1
                except:
                    pass
        except Exception as e:
            log.error(f"  SEC {ftype}: {e}")
    
    log.info(f"  SEC EDGAR: {collected} emails")
    return collected

# ─── Law Firm Directories ───────────────────────────────────────────────────

def scrape_law_firms():
    """Scrape top IP and M&A law firm websites for contact emails."""
    log.info("Law firms: scraping contact pages...")
    collected = 0
    
    # Top IP law firms (from IAM 100, etc.)
    ip_firms = [
        ("https://www.finnegan.com/contact", "Finnegan", "ip_lawyer"),
        ("https://www.fishjackson.com/contact", "Fish & Richardson", "ip_lawyer"),
        ("https://www.knobbe.com/contact", "Knobbe Martens", "ip_lawyer"),
        ("https://www.sutherland.com/contact", "Sutherland Asbill", "ip_lawyer"),
        ("https://www.foley.com/contact", "Foley & Lardner", "ip_lawyer"),
        ("https://www.winston.com/en/contact.html", "Winston & Strawn", "ip_lawyer"),
        ("https://www.sidley.com/en/contact", "Sidley Austin", "ip_lawyer"),
        ("https://www.kirkland.com/contact", "Kirkland & Ellis", "ma_lawyer"),
        ("https://www.latham.com/contact", "Latham & Watkins", "ma_lawyer"),
        ("https://www.skadden.com/contact", "Skadden", "ma_lawyer"),
        ("https://www.davispolk.com/contact", "Davis Polk", "ma_lawyer"),
        ("https://www.sullcrom.com/contact", "Sullivan & Cromwell", "ma_lawyer"),
        ("https://www.wilmerhale.com/en/contact", "WilmerHale", "ip_lawyer"),
        ("https://www.morganlewis.com/en/contact", "Morgan Lewis", "ip_lawyer"),
        ("https://www.ropesgray.com/en/contact", "Ropes & Gray", "ip_lawyer"),
        ("https://www.goodwinlaw.com/en/contact", "Goodwin", "ip_lawyer"),
        ("https://www.cooley.com/contact", "Cooley", "ip_lawyer"),
        ("https://www.perkinscoie.com/contact", "Perkins Coie", "ip_lawyer"),
        ("https://www.whitecase.com/contact", "White & Case", "ma_lawyer"),
        ("https://www.bakermckenzie.com/en/contact", "Baker McKenzie", "ip_lawyer"),
        ("https://www.hoganlovells.com/en/contact", "Hogan Lovells", "ip_lawyer"),
        ("https://www.jonesday.com/contact", "Jones Day", "ip_lawyer"),
        ("https://www.akingump.com/en/contact", "Akin Gump", "ip_lawyer"),
        ("https://www.arnoldporter.com/en/contact", "Arnold & Porter", "ip_lawyer"),
        ("https://www.crowell.com/contact", "Crowell & Moring", "ip_lawyer"),
    ]
    
    for url, firm, subcat in ip_firms:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    cat = "ip_lawyer" if "ip" in subcat else "ma_lawyer"
                    if save_email(e, org=firm, category=cat, subcategory=subcat,
                               source_url=url, source_type='law_firm_site'):
                        collected += 1
            log.info(f"  {firm}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {firm}: {e}")
    
    log.info(f"  Law firms: {collected} emails")
    return collected

# ─── Bar Association Directories ────────────────────────────────────────────

def scrape_bar_associations():
    """Scrape public bar association directories for IP lawyers."""
    log.info("Bar associations: scraping...")
    collected = 0
    
    sources = [
        # USPTO registered patent attorneys search
        ("https://oeds.uspto.gov/OEDS/practitionerSearch", "uspto_practitioner", "patent_attorney"),
        # AIPLA (American Intellectual Property Law Association)
        ("https://www.aipla.org/about/staff", "aipla", "ip_lawyer"),
        # ABA IP section
        ("https://www.americanbar.org/groups/intellectual_property_law/contact/", "aba_ip", "ip_lawyer"),
        # IPO (Intellectual Property Owners Association)
        ("https://www.ipo.org/about/staff/", "ipo", "ip_lawyer"),
        # LES (Licensing Executives Society)
        ("https://www.les.org/contact", "les", "ip_lawyer"),
    ]
    
    for url, source_name, subcat in sources:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=source_name.upper(), category='ip_lawyer',
                               subcategory=subcat, source_url=url, source_type='bar_association'):
                        collected += 1
            log.info(f"  {source_name}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {source_name}: {e}")
    
    log.info(f"  Bar associations: {collected} emails")
    return collected

# ─── Hedge Fund Directories ─────────────────────────────────────────────────

def scrape_hedge_fund_directories():
    """Scrape public hedge fund directory websites."""
    log.info("Hedge fund directories: scraping...")
    collected = 0
    
    sources = [
        ("https://www.hedgefundresearch.com/contact", "HFR", "hedge_fund"),
        ("https://www.preqin.com/contact", "Preqin", "hedge_fund"),
        ("https://www.eurekahedge.com/ContactUs", "Eurekahedge", "hedge_fund"),
        ("https://www.barclayhedge.com/contact", "BarclayHedge", "hedge_fund"),
        ("https://www.hedgefund.net/contact", "HedgeFund.net", "hedge_fund"),
        ("https://www.institutionalinvestor.com/Contacts", "InstInvestor", "hedge_fund"),
        ("https://www.alpha-magazine.com/contact", "AlphaMag", "hedge_fund"),
        ("https://www.hedgeweek.com/contact", "HedgeWeek", "hedge_fund"),
        ("https://www.finalternatives.com/contact", "AltInvest", "hedge_fund"),
        ("https://www.opalesque.com/contact.html", "Opalesque", "hedge_fund"),
    ]
    
    for url, org, subcat in sources:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category='hedge_fund', subcategory=subcat,
                               source_url=url, source_type='fund_directory'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  Hedge fund directories: {collected} emails")
    return collected

# ─── VC & PE Firms ──────────────────────────────────────────────────────────

def scrape_vc_pe_firms():
    """Scrape VC and PE firm websites for contact emails."""
    log.info("VC/PE firms: scraping...")
    collected = 0
    
    firms = [
        ("https://www.sequoiacap.com/contact", "Sequoia Capital", "vc"),
        ("https://www.a16z.com/contact/", "Andreessen Horowitz", "vc"),
        ("https://www.benchmark.com/contact", "Benchmark", "vc"),
        ("https://www.indexventures.com/contact", "Index Ventures", "vc"),
        ("https://www.accel.com/contact", "Accel", "vc"),
        ("https://www.greylock.com/contact", "Greylock", "vc"),
        ("https://www.bv.com/contact", "Bessemer Venture", "vc"),
        ("https://www.kpcb.com/contact", "Kleiner Perkins", "vc"),
        ("https://www.foundersfund.com/contact", "Founders Fund", "vc"),
        ("https://www.lightspeedvp.com/contact", "Lightspeed", "vc"),
        ("https://www.blackstone.com/contact", "Blackstone", "pe"),
        ("https://www.kkr.com/contact", "KKR", "pe"),
        ("https://www.carlyle.com/contact", "Carlyle Group", "pe"),
        ("https://www.apollo.com/contact", "Apollo Global", "pe"),
        ("https://www.baincapital.com/contact", "Bain Capital", "pe"),
        ("https://www.tpghome.com/contact", "TPG", "pe"),
        ("https://www.warburgpincus.com/contact", "Warburg Pincus", "pe"),
        ("https://www.nea.com/contact", "NEA", "vc"),
        ("https://www.ggvcapital.com/contact", "GGV Capital", "vc"),
        ("https://www.ivp.com/contact", "IVP", "vc"),
    ]
    
    for url, org, subcat in firms:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    cat = "vc_firm" if subcat == "vc" else "pe_firm"
                    if save_email(e, org=org, category=cat, subcategory=subcat,
                               source_url=url, source_type='firm_website'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  VC/PE: {collected} emails")
    return collected

# ─── University Tech Transfer Offices ───────────────────────────────────────

def scrape_tech_transfer():
    """Scrape university tech transfer offices for IP contact emails."""
    log.info("Tech transfer offices: scraping...")
    collected = 0
    
    unis = [
        ("https://techtransfer.stanford.edu/contact", "Stanford OTL", "tech_transfer"),
        ("https://www.mit.edu/tlo/contact", "MIT TLO", "tech_transfer"),
        ("https://otl.stanford.edu/contact", "Stanford", "tech_transfer"),
        ("https://www.harvard.edu/otd/contact", "Harvard OTD", "tech_transfer"),
        ("https://tlo.ucla.edu/contact", "UCLA TLO", "tech_transfer"),
        ("https://www.columbia.edu/tto/contact", "Columbia TTO", "tech_transfer"),
        ("https://otl.berkeley.edu/contact", "Berkeley OTL", "tech_transfer"),
        ("https://www.yale.edu/ocr/contact", "Yale OCR", "tech_transfer"),
        ("https://tlo.mit.edu/contact", "MIT", "tech_transfer"),
        ("https://www.princeton.edu/otl/contact", "Princeton OTL", "tech_transfer"),
        ("https://techtransfer.umich.edu/contact", "Michigan Tech Transfer", "tech_transfer"),
        ("https://www.cornell.edu/ott/contact", "Cornell OTT", "tech_transfer"),
        ("https://www.upenn.edu/ott/contact", "Penn OTT", "tech_transfer"),
        ("https://www.duke.edu/ott/contact", "Duke OTT", "tech_transfer"),
        ("https://www.jhu.edu/ott/contact", "Johns Hopkins OTT", "tech_transfer"),
        ("https://www.cam.ac.uk/research/news/technology-transfer", "Cambridge", "tech_transfer"),
        ("https://www.oxford.ac.uk/techtransfer/contact", "Oxford", "tech_transfer"),
        ("https://www.imperial.ac.uk/enterprise/contact", "Imperial College", "tech_transfer"),
        ("https://www.ethz.ch/en/industry/transfer/contact", "ETH Zurich", "tech_transfer"),
        ("https://www.tum.de/en/industry/transfer/contact", "TUM", "tech_transfer"),
    ]
    
    for url, org, subcat in unis:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category='tech_transfer', subcategory=subcat,
                               source_url=url, source_type='university_tto'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  Tech transfer: {collected} emails")
    return collected

# ─── IP Brokers & Marketplaces ──────────────────────────────────────────────

def scrape_ip_brokers():
    """Scrape IP brokers and patent marketplace contact emails."""
    log.info("IP brokers: scraping...")
    collected = 0
    
    brokers = [
        ("https://www.icap.com/contact", "ICAP Patent Brokerage", "ip_broker"),
        ("https://www.spectrumip.com/contact", "Spectrum IP", "ip_broker"),
        ("https://www.intven.com/contact", "Intellectual Ventures", "ip_broker"),
        ("https://www.acaciaresearch.com/contact", "Acacia Research", "ip_broker"),
        ("https://www.ipcheckups.com/contact", "IP Checkups", "ip_broker"),
        ("https://www.texasip.com/contact", "Texas IP", "ip_broker"),
        ("https://www.patentbroker.com/contact", "Patent Broker", "ip_broker"),
        ("https://www.ipmarketplace.com/contact", "IP Marketplace", "ip_broker"),
        ("https://www.yet2.com/contact", "yet2.com", "ip_broker"),
        ("https://www.tynax.com/contact", "Tynax", "ip_broker"),
        ("https://www.aminnovation.com/contact", "Amin Innovation", "ip_broker"),
        ("https://www.ideabuyer.com/contact", "IdeaBuyer", "ip_broker"),
    ]
    
    for url, org, subcat in brokers:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category='ip_broker', subcategory=subcat,
                               source_url=url, source_type='ip_broker_site'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  IP brokers: {collected} emails")
    return collected

# ─── IP Valuation Firms ─────────────────────────────────────────────────────

def scrape_ip_valuation():
    """Scrape IP valuation firms for contact emails."""
    log.info("IP valuation: scraping...")
    collected = 0
    
    firms = [
        ("https://www.royaltyrange.com/contact", "Royalty Range", "ip_valuation"),
        ("https://www.crawfordint.com/contact", "Crawford International", "ip_valuation"),
        ("https://www.ipmetrics.net/contact", "IP Metrics", "ip_valuation"),
        ("https://www.conventuslaw.com/contact", "Conventus Law", "ip_valuation"),
        ("https://www.ceanic.com/contact", "Ceanic", "ip_valuation"),
        ("https://www.hillbirney.com/contact", "Hill Birney", "ip_valuation"),
        ("https://www.duffandphelps.com/contact", "Duff & Phelps", "ip_valuation"),
        ("https://www.fticonsulting.com/contact", "FTI Consulting", "ip_valuation"),
        ("https://www.alixpartners.com/contact", "AlixPartners", "ip_valuation"),
        ("https://www.berkeryresearch.com/contact", "Berkery Research", "ip_valuation"),
    ]
    
    for url, org, subcat in firms:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category='ip_valuation', subcategory=subcat,
                               source_url=url, source_type='valuation_firm'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  IP valuation: {collected} emails")
    return collected

# ─── Investment Banks ───────────────────────────────────────────────────────

def scrape_investment_banks():
    """Scrape investment bank contact emails."""
    log.info("Investment banks: scraping...")
    collected = 0
    
    banks = [
        ("https://www.goldmansachs.com/contact", "Goldman Sachs", "investment_bank"),
        ("https://www.jpmorgan.com/contact", "JP Morgan", "investment_bank"),
        ("https://www.morganstanley.com/contact", "Morgan Stanley", "investment_bank"),
        ("https://www.citi.com/contact", "Citi", "investment_bank"),
        ("https://www.baml.com/contact", "BofA Merrill Lynch", "investment_bank"),
        ("https://www.db.com/contact", "Deutsche Bank", "investment_bank"),
        ("https://www.barclays.com/contact", "Barclays", "investment_bank"),
        ("https://www.ubs.com/contact", "UBS", "investment_bank"),
        ("https://www.cs.com/contact", "Credit Suisse", "investment_bank"),
        ("https://www.nomura.com/contact", "Nomura", "investment_bank"),
        ("https://www.lazard.com/contact", "Lazard", "investment_bank"),
        ("https://www.evercore.com/contact", "Evercore", "investment_bank"),
        ("https://www.centerview.com/contact", "Centerview", "investment_bank"),
        ("https://www.moelis.com/contact", "Moelis & Co", "investment_bank"),
        ("https://www.pjt.com/contact", "PJT Partners", "investment_bank"),
    ]
    
    for url, org, subcat in banks:
        try:
            emails, text = extract_emails_from_page(url)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category='investment_bank', subcategory=subcat,
                               source_url=url, source_type='bank_website'):
                        collected += 1
            log.info(f"  {org}: {len(emails)} found")
        except Exception as e:
            log.error(f"  {org}: {e}")
    
    log.info(f"  Investment banks: {collected} emails")
    return collected

# ─── Google Search Scraper ──────────────────────────────────────────────────

def scrape_google_searches():
    """Use Google search to find email addresses of hedge funds and IP lawyers."""
    log.info("Google searches: scraping for emails...")
    collected = 0
    
    queries = [
        ("hedge fund contact email site:hedgefund.com", "hedge_fund"),
        ("intellectual property lawyer email contact", "ip_lawyer"),
        ("patent attorney email contact site:law firm", "patent_attorney"),
        ("private equity firm contact email", "pe_firm"),
        ("venture capital firm contact email", "vc_firm"),
        ("IP broker patent marketplace contact", "ip_broker"),
        ("tech transfer office contact email university", "tech_transfer"),
        ("IP valuation firm contact email", "ip_valuation"),
        ("merger acquisition lawyer email contact", "ma_lawyer"),
        ("investment bank contact email", "investment_bank"),
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for query, category in queries:
        try:
            # Use Google search
            url = f"https://www.google.com/search?q={query}&num=20"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                emails = extract_emails_from_text(r.text)
                for e in emails:
                    e = clean_email(e)
                    if e:
                        if save_email(e, category=category, subcategory='google_search',
                                   source_url=url, source_type='google_search'):
                            collected += 1
                log.info(f"  '{query[:40]}': {len(emails)} found")
            
            time.sleep(2)  # Be polite
        except Exception as e:
            log.error(f"  Google search: {e}")
    
    log.info(f"  Google searches: {collected} emails")
    return collected

# ─── Bing Search Scraper ────────────────────────────────────────────────────

def scrape_bing_searches():
    """Use Bing search for additional email discovery."""
    log.info("Bing searches: scraping for emails...")
    collected = 0
    
    queries = [
        ('"hedge fund" "contact us" email', "hedge_fund"),
        ('"intellectual property" "attorney" email contact', "ip_lawyer"),
        ('"patent attorney" email "@" contact', "patent_attorney"),
        ('"private equity" "contact" email', "pe_firm"),
        ('"venture capital" "contact" email', "vc_firm"),
        ('"IP broker" "contact" email', "ip_broker"),
        ('"tech transfer" "contact" email university', "tech_transfer"),
        ('"IP valuation" "contact" email', "ip_valuation"),
        ('"M&A lawyer" "contact" email', "ma_lawyer"),
        ('"investment bank" "contact" email', "investment_bank"),
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for query, category in queries:
        try:
            url = f"https://www.bing.com/search?q={query}&count=30"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                emails = extract_emails_from_text(r.text)
                for e in emails:
                    e = clean_email(e)
                    if e:
                        if save_email(e, category=category, subcategory='bing_search',
                                   source_url=url, source_type='bing_search'):
                            collected += 1
                log.info(f"  Bing '{query[:40]}': {len(emails)} found")
            
            time.sleep(1)
        except Exception as e:
            log.error(f"  Bing: {e}")
    
    log.info(f"  Bing: {collected} emails")
    return collected

# ─── Crunchbase Public Data ─────────────────────────────────────────────────

def scrape_crunchbase_companies():
    """Scrape Crunchbase company pages for contact emails."""
    log.info("Crunchbase: scraping company emails...")
    collected = 0
    
    # Search for hedge fund and IP companies on Crunchbase
    search_urls = [
        ("https://www.crunchbase.com/textsearch?q=hedge+fund", "hedge_fund"),
        ("https://www.crunchbase.com/textsearch?q=intellectual+property", "ip_lawyer"),
        ("https://www.crunchbase.com/textsearch?q=patent+broker", "ip_broker"),
        ("https://www.crunchbase.com/textsearch?q=IP+valuation", "ip_valuation"),
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for url, cat in search_urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                emails = extract_emails_from_text(r.text)
                for e in emails:
                    e = clean_email(e)
                    if e:
                        if save_email(e, category=cat, subcategory='crunchbase',
                                   source_url=url, source_type='crunchbase'):
                            collected += 1
        except:
            pass
    
    log.info(f"  Crunchbase: {collected} emails")
    return collected

# ─── Deep Crawl: Follow Links ───────────────────────────────────────────────

def deep_crawl_site(base_url, max_pages=10, category='', org=''):
    """Crawl a website's contact/about/team pages for emails."""
    collected = 0
    visited = set()
    to_visit = [base_url]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    pages_crawled = 0
    while to_visit and pages_crawled < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        
        try:
            r = requests.get(url, headers=headers, timeout=10, verify=False)
            if r.status_code != 200:
                continue
            pages_crawled += 1
            
            emails = extract_emails_from_text(r.text)
            for e in emails:
                e = clean_email(e)
                if e:
                    if save_email(e, org=org, category=category, source_url=url,
                               source_type='deep_crawl'):
                        collected += 1
            
            # Find contact/about/team links
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                text = a.get_text().lower()
                if any(kw in href or kw in text for kw in ['contact', 'about', 'team', 'staff', 
                    'people', 'directory', 'lawyers', 'attorneys', 'professionals', 'partners']):
                    full_url = urljoin(url, a['href'])
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        if full_url not in visited:
                            to_visit.append(full_url)
        except:
            pass
    
    return collected

# ─── Main Pipeline ──────────────────────────────────────────────────────────

async def run_collection():
    log.info("=" * 60)
    log.info("EMAIL COLLECTION PIPELINE - 10,000 TARGET")
    log.info("=" * 60)
    
    init_db()
    
    total_new = 0
    
    # Phase 1: Direct website scraping
    log.info("\n--- Phase 1: Direct website scraping ---")
    total_new += scrape_sec_edgar()
    total_new += scrape_law_firms()
    total_new += scrape_bar_associations()
    total_new += scrape_hedge_fund_directories()
    total_new += scrape_vc_pe_firms()
    total_new += scrape_tech_transfer()
    total_new += scrape_ip_brokers()
    total_new += scrape_ip_valuation()
    total_new += scrape_investment_banks()
    
    # Phase 2: Search engine scraping
    log.info("\n--- Phase 2: Search engine scraping ---")
    total_new += scrape_google_searches()
    total_new += scrape_bing_searches()
    
    # Phase 3: Crunchbase
    log.info("\n--- Phase 3: Crunchbase ---")
    total_new += scrape_crunchbase_companies()
    
    # Phase 4: Deep crawl top law firms
    log.info("\n--- Phase 4: Deep crawling law firm sites ---")
    deep_targets = [
        ("https://www.finnegan.com", "ip_lawyer", "Finnegan"),
        ("https://www.fishjackson.com", "ip_lawyer", "Fish & Richardson"),
        ("https://www.knobbe.com", "ip_lawyer", "Knobbe Martens"),
        ("https://www.wilmerhale.com", "ip_lawyer", "WilmerHale"),
        ("https://www.ropesgray.com", "ip_lawyer", "Ropes & Gray"),
        ("https://www.cooley.com", "ip_lawyer", "Cooley"),
        ("https://www.perkinscoie.com", "ip_lawyer", "Perkins Coie"),
        ("https://www.morganlewis.com", "ip_lawyer", "Morgan Lewis"),
        ("https://www.kirkland.com", "ma_lawyer", "Kirkland & Ellis"),
        ("https://www.latham.com", "ma_lawyer", "Latham & Watkins"),
    ]
    for url, cat, org in deep_targets:
        n = deep_crawl_site(url, max_pages=15, category=cat, org=org)
        log.info(f"  Deep crawl {org}: {n} emails")
        total_new += n
    
    # Stats
    total, cats = get_counts()
    log.info("\n" + "=" * 60)
    log.info(f"COLLECTION COMPLETE")
    log.info(f"New this run: {total_new}")
    log.info(f"Total in DB: {total}")
    log.info("=" * 60)
    log.info("By category:")
    for cat, count in cats:
        log.info(f"  {cat}: {count}")
    
    # Export to JSON
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, name, organization, category, subcategory, source_url, title, phone, country FROM emails")
    rows = c.fetchall()
    conn.close()
    
    export = []
    for row in rows:
        export.append({
            'email': row[0], 'name': row[1], 'organization': row[2],
            'category': row[3], 'subcategory': row[4], 'source_url': row[5],
            'title': row[6], 'phone': row[7], 'country': row[8]
        })
    
    with open(str(Path(__file__).parent / 'data' / 'collected_emails.json'), 'w') as f:
        json.dump(export, f, indent=2)
    
    log.info(f"\nExported {len(export)} emails to data/collected_emails.json")
    
    # Also export CSV
    import csv
    csv_path = str(Path(__file__).parent / 'data' / 'collected_emails.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['email', 'name', 'organization', 'category', 'subcategory', 'source_url', 'title', 'phone', 'country'])
        for row in rows:
            w.writerow(row)
    
    log.info(f"Exported CSV to {csv_path}")
    
    return total

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    asyncio.run(run_collection())
