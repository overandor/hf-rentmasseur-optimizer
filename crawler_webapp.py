"""
Web App: Dual Crawl Job Runner
- Launch 2 crawl jobs simultaneously
- Real-time dashboard with live stats
- Job 1: IP Lawyers + M&A Lawyers (law firms + directories)
- Job 2: Hedge Funds + VC/PE + Tech Transfer + IP Brokers + IP Valuation + Investment Banks
"""

import os, re, json, time, sqlite3, hashlib, logging, asyncio, threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import urllib3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import io, csv
import uvicorn

from layer_crawler_etl import run_etl, latest_run, list_receipts
from poptimizer_etl_engine import POptimizerETL, make_router

urllib3.disable_warnings()

poptimizer = POptimizerETL(system_name="Email Crawler Dashboard")
poptimizer.register_source("crawler_repo", "repo", ".")
poptimizer.register_source("crawler_web", "runtime", "http://localhost:7860")

BASE = Path(__file__).parent
DB = str(BASE / 'data' / 'emails10k.db')
os.makedirs(os.path.dirname(DB), exist_ok=True)

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('/tmp/crawler_webapp.log'), logging.StreamHandler()])
log = logging.getLogger('crawler')

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:\+?1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})')
NAME_RE = re.compile(r'([A-Z][a-z]+ [A-Z][a-z]+)')
TITLE_RE = re.compile(r'(Partner|Associate|Counsel|Managing Director|Director|VP|Vice President|Principal|Senior|Junior|Attorney|Lawyer|Analyst|Consultant|Advisor|Head|Chief|Founder|Co-Founder|CEO|CFO|COO|CTO|President|Chairman|Of Counsel)', re.I)
LOC_RE = re.compile(r'(New York|San Francisco|Los Angeles|Chicago|Boston|Washington|Houston|Dallas|Atlanta|Miami|Seattle|Denver|London|Paris|Frankfurt|Tokyo|Hong Kong|Singapore|Dubai|Zurich|Geneva|Toronto|Sydney|Palo Alto|Menlo Park|Austin|Silicon Valley|United States|United Kingdom)', re.I)

JUNK = {'wixpress.com','example.com','sentry.io','cloudflare.com','godaddy.com',
        'squarespace.com','wordpress.com','google.com','facebook.com','twitter.com',
        'linkedin.com','instagram.com','youtube.com','github.com','medium.com',
        'substack.com','mailchimp.com','hubspot.com'}

ROLE_KW = {
    'ip_lawyer': ['intellectual property','ip law','patent','trademark','copyright','licensing','ip litigation','patent prosecution'],
    'ma_lawyer': ['merger','acquisition','m&a','corporate law','transactional','deal','buyout','joint venture'],
    'hedge_fund': ['hedge fund','portfolio manager','quant','trading','alpha','long/short','distressed','arbitrage'],
    'pe_firm': ['private equity','leveraged','buyout','growth equity','portfolio company','lbo'],
    'vc_firm': ['venture capital','startup','early stage','seed','series a','portfolio'],
    'ip_broker': ['patent broker','ip marketplace','patent sale','ip transaction','patent licensing'],
    'ip_valuation': ['ip valuation','intangible asset','royalty rate','ip appraisal','fair value'],
    'tech_transfer': ['tech transfer','technology transfer','ott','otl','licensing office','university'],
    'investment_bank': ['investment bank','ibd','m&a advisory','capital markets','underwriting'],
}

def is_real_email(e):
    e = e.lower().strip()
    if any(e.startswith(p) for p in ['noreply','no-reply','donotreply','test@','example@','sentry']):
        return False
    if any(e.endswith(x) for x in ['.png','.jpg','.gif','.css','.js','.ico','.svg']):
        return False
    if len(e) > 80: return False
    dom = e.split('@')[1] if '@' in e else ''
    if dom in JUNK or '.' not in dom: return False
    local = e.split('@')[0]
    if local.isdigit(): return False
    return True

def extract_phones(text):
    phones = set()
    for m in PHONE_RE.findall(text):
        p = f"({m[0]}) {m[1]}-{m[2]}"
        if m[0] not in ('000','999','111') and m[1] not in ('000','999'):
            phones.add(p)
    return list(phones)

def classify_role(text, email, org=''):
    text_lower = text.lower()
    scores = defaultdict(int)
    for cat, keywords in ROLE_KW.items():
        for kw in keywords:
            if kw in text_lower:
                scores[cat] += 1
    if scores:
        return max(scores, key=scores.get), dict(scores)
    return 'unknown', {}

def score_response(email, name, title, org, category, phones, page_text):
    score = 30
    local = email.split('@')[0].lower()
    domain = email.split('@')[1].lower() if '@' in email else ''
    if '.' in local and not local.startswith(('info','contact','admin','support')):
        score += 20
    if name: score += 10
    if title: score += 10
    if phones: score += 10
    senior = ['partner','managing director','head','chief','founder','ceo','president','chairman','principal']
    if title and any(s in title.lower() for s in senior): score += 15
    elif title and any(s in title.lower() for s in ['associate','analyst','junior']): score -= 5
    if local in ['info','contact','admin','support','webmaster','office','reception','general']: score -= 15
    if category in ('ip_lawyer','ip_broker','ip_valuation','tech_transfer'): score += 10
    if category in ('hedge_fund','pe_firm','vc_firm'): score += 5
    big = ['kirkland','latham','skadden','davis','sullivan','hogan','baker','jones',
           'goldman','morgan','jpmorgan','blackstone','kkr','carlyle','apollo']
    if any(b in domain for b in big): score -= 5
    if len(page_text) > 500: score += 5
    return max(0, min(100, score))

# ─── DB ─────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY, email TEXT, name TEXT, title TEXT, organization TEXT,
        category TEXT, location TEXT, phones TEXT, source_url TEXT, keywords TEXT,
        role_scores TEXT, response_likelihood INTEGER, dossier_text TEXT,
        cluster_id TEXT, collected_at TEXT, job_id TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_email ON emails(email)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cat ON emails(category)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_org ON emails(organization)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_score ON emails(response_likelihood DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cluster ON emails(cluster_id)')
    try: c.execute('ALTER TABLE emails ADD COLUMN job_id TEXT')
    except: pass
    c.execute('CREATE INDEX IF NOT EXISTS idx_job ON emails(job_id)')
    conn.commit()
    conn.close()

def save_dossier(d, job_id='job1'):
    eid = hashlib.md5(f"{d['email']}:{d['source_url']}".encode()).hexdigest()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM emails WHERE id=?", (eid,))
    if c.fetchone():
        conn.close()
        return False
    c.execute("""INSERT OR IGNORE INTO emails
        (id,email,name,title,organization,category,location,phones,source_url,
         keywords,role_scores,response_likelihood,dossier_text,cluster_id,collected_at,job_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eid, d['email'], d['name'], d['title'], d['organization'], d['category'],
         d['location'], json.dumps(d['phones']), d['source_url'],
         json.dumps(d['keywords']), json.dumps(d['role_scores']),
         d['response_likelihood'], d['dossier_text'], '', d['collected_at'], job_id))
    conn.commit()
    conn.close()
    return True

def get_db_stats():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM emails")
    total = c.fetchone()[0]
    c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category ORDER BY COUNT(*) DESC")
    cats = c.fetchall()
    c.execute("SELECT COUNT(*) FROM emails WHERE response_likelihood >= 70")
    high = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM emails WHERE response_likelihood >= 90")
    vip = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT organization) FROM emails")
    orgs = c.fetchone()[0]
    c.execute("SELECT job_id, COUNT(*) FROM emails GROUP BY job_id")
    jobs = c.fetchall()
    conn.close()
    return {'total': total, 'categories': dict(cats), 'high': high, 'vip': vip, 'orgs': orgs, 'jobs': dict(jobs)}

# ─── Crawler ────────────────────────────────────────────────────────────────

class Crawler:
    def __init__(self, job_id='job1'):
        self.job_id = job_id
        self.s = requests.Session()
        self.s.headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        self.visited = set()
        self.count = 0
        self.pages = 0
        self.current_org = ''
        self.status = 'idle'
        self.log_lines = []
    
    def _log(self, msg):
        self.log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-100:]
        log.info(f"[{self.job_id}] {msg}")
    
    def fetch(self, url):
        if url in self.visited: return None, None, None
        self.visited.add(url)
        try:
            r = self.s.get(url, timeout=12, verify=False, allow_redirects=True)
            if r.status_code != 200: return None, None, None
            soup = BeautifulSoup(r.text, 'html.parser')
            return r.text, soup, soup.get_text()
        except: return None, None, None
    
    def process_page(self, url, html, soup, text, category='', org=''):
        emails = set(EMAIL_RE.findall(html))
        emails.update(EMAIL_RE.findall(text))
        phones = extract_phones(text)
        page_count = 0
        
        for email in emails:
            if not is_real_email(email): continue
            email = email.lower()
            name = self._find_near(text, email, NAME_RE)
            title = self._find_near(text, email, TITLE_RE)
            location = self._find_near(text, email, LOC_RE)
            cat, role_scores = classify_role(text, email, org)
            if category and cat == 'unknown': cat = category
            
            keywords = []
            tl = text.lower()
            for term in ['patent','trademark','copyright','ip','intellectual property','licensing',
                         'merger','acquisition','hedge fund','private equity','venture capital',
                         'portfolio','arbitration','litigation','prosecution','valuation','royalty']:
                if term in tl: keywords.append(term)
            
            rl = score_response(email, name, title, org, cat, phones, text)
            dossier = {
                'email': email, 'name': name, 'title': title, 'organization': org,
                'category': cat, 'location': location, 'phones': phones[:3],
                'source_url': url, 'keywords': list(set(keywords))[:10],
                'role_scores': role_scores, 'response_likelihood': rl,
                'dossier_text': f"{name or 'Unknown'} - {title or 'Unknown role'} at {org or 'Unknown org'}. "
                               f"Category: {cat}. Location: {location or 'Unknown'}. "
                               f"Keywords: {', '.join(keywords[:5])}. "
                               f"Phones: {', '.join(phones[:2])}. "
                               f"Response likelihood: {rl}/100.",
                'collected_at': datetime.now().isoformat(),
            }
            if save_dossier(dossier, self.job_id):
                page_count += 1
                self.count += 1
                marker = '⭐' if rl >= 70 else '✉️'
                self._log(f"{marker} [{rl}] {email} | {name or '?'} | {title or '?'} | {org or '?'}")
        return page_count
    
    def _find_near(self, text, email, regex):
        idx = text.find(email)
        if idx >= 0:
            around = text[max(0, idx-300):idx+300]
            matches = regex.findall(around)
            if matches: return matches[0] if isinstance(matches[0], str) else matches[0][0]
        return ''
    
    def find_sublinks(self, soup, base_url, keywords):
        if not soup: return []
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            txt = a.get_text().strip().lower()
            full = urljoin(base_url, href)
            if urlparse(full).netloc != urlparse(base_url).netloc: continue
            if any(kw in href.lower() or kw in txt for kw in keywords):
                if full not in self.visited and full not in links:
                    links.append(full)
        return links
    
    def crawl_site(self, base_url, category='', org='', max_pages=40):
        kw = ['attorney','lawyer','partner','team','people','professional','staff',
              'contact','about','bio','profile','directory','member','consultant',
              'advisor','our-people','professionals','lawyers']
        queue = [base_url]
        self.current_org = org or base_url[:40]
        site_emails = 0
        
        while queue and self.pages < max_pages and self.status == 'running':
            url = queue.pop(0)
            html, soup, text = self.fetch(url)
            if html is None: continue
            self.pages += 1
            site_emails += self.process_page(url, html, soup, text, category, org)
            links = self.find_sublinks(soup, url, kw)
            profiles = [l for l in links if any(k in l.lower() for k in ['bio','profile','attorney','lawyer','people'])]
            others = [l for l in links if l not in profiles]
            queue = profiles[:15] + queue + others[:5]
            time.sleep(0.2)
        
        self._log(f"  {org or base_url[:40]}: {self.pages}p, {site_emails}e (total: {self.count})")
        return site_emails
    
    def crawl_directory(self, url, category, max_listings=50):
        html, soup, text = self.fetch(url)
        if html is None: return 0
        self.pages += 1
        count = self.process_page(url, html, soup, text, category)
        
        listings = []
        if soup:
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                txt = a.get_text().strip()
                if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+', txt) and len(txt) < 60:
                    listings.append((href, txt))
                elif any(k in href.lower() for k in ['profile','attorney','lawyer','detail','view','member']):
                    listings.append((href, txt))
        
        for prof_url, _ in listings[:max_listings]:
            if self.status != 'running': break
            html2, soup2, text2 = self.fetch(prof_url)
            if html2 is None: continue
            self.pages += 1
            count += self.process_page(prof_url, html2, soup2, text2, category)
            time.sleep(0.2)
        
        self._log(f"  Dir {url[:50]}: {count}e (total: {self.count})")
        return count
    
    def run(self, sources):
        self.status = 'running'
        self._log(f"STARTING: {len(sources)} sources")
        
        for source in sources:
            if self.status != 'running': break
            if source.get('type') == 'directory':
                self.crawl_directory(source['url'], source['category'], source.get('max_listings', 50))
            else:
                self.crawl_site(source['url'], source['category'], source.get('org',''), source.get('max_pages', 40))
            time.sleep(0.3)
        
        self.status = 'done'
        self._log(f"DONE: {self.count} emails, {self.pages} pages")

# ─── Job Definitions ────────────────────────────────────────────────────────

JOB1_SOURCES = [
    # Directories
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/california.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/new-york.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/texas.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/florida.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/illinois.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/massachusetts.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/intellectual-property/washington.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/patent-law/california.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/patent-law/new-york.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/patent-law/texas.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/trademark-law/california.html','category':'ip_lawyer'},
    {'type':'directory','url':'https://www.hg.org/law-firms/trademark-law/new-york.html','category':'ip_lawyer'},
    # Law firms
    {'type':'site','url':'https://www.finnegan.com/en/professionals.html','org':'Finnegan','category':'ip_lawyer'},
    {'type':'site','url':'https://www.fishjackson.com/people','org':'Fish & Richardson','category':'ip_lawyer'},
    {'type':'site','url':'https://www.knobbe.com/people','org':'Knobbe Martens','category':'ip_lawyer'},
    {'type':'site','url':'https://www.wilmerhale.com/en/people','org':'WilmerHale','category':'ip_lawyer'},
    {'type':'site','url':'https://www.ropesgray.com/en/people','org':'Ropes & Gray','category':'ip_lawyer'},
    {'type':'site','url':'https://www.cooley.com/people','org':'Cooley','category':'ip_lawyer'},
    {'type':'site','url':'https://www.perkinscoie.com/en/professionals.html','org':'Perkins Coie','category':'ip_lawyer'},
    {'type':'site','url':'https://www.morganlewis.com/en/people','org':'Morgan Lewis','category':'ip_lawyer'},
    {'type':'site','url':'https://www.hoganlovells.com/en/people','org':'Hogan Lovells','category':'ip_lawyer'},
    {'type':'site','url':'https://www.bakermckenzie.com/en/people','org':'Baker McKenzie','category':'ip_lawyer'},
    {'type':'site','url':'https://www.jonesday.com/lawyers','org':'Jones Day','category':'ip_lawyer'},
    {'type':'site','url':'https://www.goodwinlaw.com/en/people.html','org':'Goodwin','category':'ip_lawyer'},
    {'type':'site','url':'https://www.fenwick.com/people','org':'Fenwick & West','category':'ip_lawyer'},
    {'type':'site','url':'https://www.mofo.com/people','org':'Morrison & Foerster','category':'ip_lawyer'},
    {'type':'site','url':'https://www.gibsondunn.com/people','org':'Gibson Dunn','category':'ip_lawyer'},
    {'type':'site','url':'https://www.kirkland.com/lawyers','org':'Kirkland & Ellis','category':'ma_lawyer'},
    {'type':'site','url':'https://www.lw.com/en/people','org':'Latham & Watkins','category':'ma_lawyer'},
    {'type':'site','url':'https://www.skadden.com/professionals','org':'Skadden','category':'ma_lawyer'},
    {'type':'site','url':'https://www.davispolk.com/lawyers','org':'Davis Polk','category':'ma_lawyer'},
    {'type':'site','url':'https://www.sullcrom.com/professionals','org':'Sullivan & Cromwell','category':'ma_lawyer'},
    {'type':'site','url':'https://www.whitecase.com/people','org':'White & Case','category':'ma_lawyer'},
    {'type':'site','url':'https://www.arnoldporter.com/en/professionals','org':'Arnold & Porter','category':'ip_lawyer'},
    {'type':'site','url':'https://www.crowell.com/people','org':'Crowell & Moring','category':'ip_lawyer'},
    {'type':'site','url':'https://www.sidley.com/en/contact','org':'Sidley Austin','category':'ip_lawyer'},
    {'type':'site','url':'https://www.foley.com/contact','org':'Foley & Lardner','category':'ip_lawyer'},
    {'type':'site','url':'https://www.akingump.com/en/contact','org':'Akin Gump','category':'ip_lawyer'},
]

JOB2_SOURCES = [
    # Hedge funds
    {'type':'site','url':'https://www.bridgewater.com/our-people','org':'Bridgewater','category':'hedge_fund'},
    {'type':'site','url':'https://www.renaissance.com/about-us/our-people','org':'Renaissance Tech','category':'hedge_fund'},
    {'type':'site','url':'https://www.aqr.com/About-Us/OurFirm','org':'AQR Capital','category':'hedge_fund'},
    {'type':'site','url':'https://www.two-sigma.com/about/our-people','org':'Two Sigma','category':'hedge_fund'},
    {'type':'site','url':'https://www.baupost.com/contact','org':'Baupost Group','category':'hedge_fund'},
    {'type':'site','url':'https://www.pershingsquarecapital.com/contact','org':'Pershing Square','category':'hedge_fund'},
    {'type':'site','url':'https://www.thirdpoint.com/contact','org':'Third Point','category':'hedge_fund'},
    {'type':'site','url':'https://www.exoduspoint.com/contact','org':'ExodusPoint','category':'hedge_fund'},
    {'type':'site','url':'https://www.maverickcapital.com/contact','org':'Maverick Capital','category':'hedge_fund'},
    {'type':'site','url':'https://www.elliottmgmt.com/contact','org':'Elliott Management','category':'hedge_fund'},
    {'type':'site','url':'https://www.citadel.com/about/our-people','org':'Citadel','category':'hedge_fund'},
    {'type':'site','url':'https://www.point72.com/our-people','org':'Point72','category':'hedge_fund'},
    {'type':'site','url':'https://www.millennium.com/about/our-people','org':'Millennium','category':'hedge_fund'},
    {'type':'site','url':'https://www.balyasny.com/about/our-team','org':'Balyasny','category':'hedge_fund'},
    {'type':'site','url':'https://www.deshaw.com/our-people','org':'D.E. Shaw','category':'hedge_fund'},
    {'type':'site','url':'https://www.tudor.com/contact','org':'Tudor Investment','category':'hedge_fund'},
    {'type':'site','url':'https://www.glenviewcapital.com/contact','org':'Glenview Capital','category':'hedge_fund'},
    {'type':'site','url':'https://www.vikingglobal.com/contact','org':'Viking Global','category':'hedge_fund'},
    {'type':'site','url':'https://www.rokoscapital.com/contact','org':'Rokos Capital','category':'hedge_fund'},
    {'type':'site','url':'https://www.brevanhoward.com/contact','org':'Brevan Howard','category':'hedge_fund'},
    {'type':'site','url':'https://www.tigerglobal.com/contact','org':'Tiger Global','category':'hedge_fund'},
    {'type':'site','url':'https://www.coatue.com/contact','org':'Coatue','category':'hedge_fund'},
    {'type':'site','url':'https://www.d1capital.com/contact','org':'D1 Capital','category':'hedge_fund'},
    # VC/PE
    {'type':'site','url':'https://www.sequoiacap.com/people','org':'Sequoia Capital','category':'vc_firm'},
    {'type':'site','url':'https://www.a16z.com/people/','org':'Andreessen Horowitz','category':'vc_firm'},
    {'type':'site','url':'https://www.benchmark.com/people','org':'Benchmark','category':'vc_firm'},
    {'type':'site','url':'https://www.indexventures.com/people','org':'Index Ventures','category':'vc_firm'},
    {'type':'site','url':'https://www.accel.com/people','org':'Accel','category':'vc_firm'},
    {'type':'site','url':'https://www.greylock.com/people','org':'Greylock','category':'vc_firm'},
    {'type':'site','url':'https://www.bv.com/people','org':'Bessemer Venture','category':'vc_firm'},
    {'type':'site','url':'https://www.kpcb.com/people','org':'Kleiner Perkins','category':'vc_firm'},
    {'type':'site','url':'https://www.foundersfund.com/team','org':'Founders Fund','category':'vc_firm'},
    {'type':'site','url':'https://www.lightspeedvp.com/people','org':'Lightspeed','category':'vc_firm'},
    {'type':'site','url':'https://www.blackstone.com/our-people','org':'Blackstone','category':'pe_firm'},
    {'type':'site','url':'https://www.kkr.com/our-people','org':'KKR','category':'pe_firm'},
    {'type':'site','url':'https://www.carlyle.com/our-people','org':'Carlyle Group','category':'pe_firm'},
    {'type':'site','url':'https://www.apollo.com/our-people','org':'Apollo Global','category':'pe_firm'},
    {'type':'site','url':'https://www.baincapital.com/people','org':'Bain Capital','category':'pe_firm'},
    {'type':'site','url':'https://www.tpghome.com/our-people','org':'TPG','category':'pe_firm'},
    {'type':'site','url':'https://www.warburgpincus.com/people','org':'Warburg Pincus','category':'pe_firm'},
    {'type':'site','url':'https://www.nea.com/team','org':'NEA','category':'vc_firm'},
    {'type':'site','url':'https://www.ggvcapital.com/team','org':'GGV Capital','category':'vc_firm'},
    {'type':'site','url':'https://www.ivp.com/team','org':'IVP','category':'vc_firm'},
    {'type':'site','url':'https://www.battery.com/people','org':'Battery Ventures','category':'vc_firm'},
    {'type':'site','url':'https://www.sparkcapital.com/people','org':'Spark Capital','category':'vc_firm'},
    {'type':'site','url':'https://www.insidellc.com/people','org':'Insight Partners','category':'vc_firm'},
    {'type':'site','url':'https://www.generalatlantic.com/people','org':'General Atlantic','category':'pe_firm'},
    # Tech transfer
    {'type':'site','url':'https://techtransfer.stanford.edu/people','org':'Stanford OTL','category':'tech_transfer'},
    {'type':'site','url':'https://tlo.mit.edu/people','org':'MIT TLO','category':'tech_transfer'},
    {'type':'site','url':'https://otd.harvard.edu/people','org':'Harvard OTD','category':'tech_transfer'},
    {'type':'site','url':'https://otl.berkeley.edu/people','org':'Berkeley OTL','category':'tech_transfer'},
    {'type':'site','url':'https://techtransfer.columbia.edu/people','org':'Columbia TTO','category':'tech_transfer'},
    {'type':'site','url':'https://ott.yale.edu/people','org':'Yale OTT','category':'tech_transfer'},
    {'type':'site','url':'https://www.princeton.edu/otl/people','org':'Princeton OTL','category':'tech_transfer'},
    {'type':'site','url':'https://techtransfer.umich.edu/people','org':'Michigan TT','category':'tech_transfer'},
    {'type':'site','url':'https://ott.cornell.edu/people','org':'Cornell OTT','category':'tech_transfer'},
    # IP brokers
    {'type':'site','url':'https://www.icap.com/contact-us','org':'ICAP Patent Brokerage','category':'ip_broker'},
    {'type':'site','url':'https://www.intven.com/contact','org':'Intellectual Ventures','category':'ip_broker'},
    {'type':'site','url':'https://www.yet2.com/about/team','org':'yet2.com','category':'ip_broker'},
    {'type':'site','url':'https://www.tynax.com/about','org':'Tynax','category':'ip_broker'},
    {'type':'site','url':'https://www.ideabuyer.com/about','org':'IdeaBuyer','category':'ip_broker'},
    # IP valuation
    {'type':'site','url':'https://www.royaltyrange.com/contact','org':'Royalty Range','category':'ip_valuation'},
    {'type':'site','url':'https://www.ipmetrics.net/contact','org':'IP Metrics','category':'ip_valuation'},
    {'type':'site','url':'https://www.duffandphelps.com/contact','org':'Duff & Phelps','category':'ip_valuation'},
    {'type':'site','url':'https://www.fticonsulting.com/contact','org':'FTI Consulting','category':'ip_valuation'},
    {'type':'site','url':'https://www.alixpartners.com/contact','org':'AlixPartners','category':'ip_valuation'},
    # Investment banks
    {'type':'site','url':'https://www.goldmansachs.com/our-firm/people.html','org':'Goldman Sachs','category':'investment_bank'},
    {'type':'site','url':'https://www.jpmorgan.com/our-firm/people','org':'JP Morgan','category':'investment_bank'},
    {'type':'site','url':'https://www.morganstanley.com/people','org':'Morgan Stanley','category':'investment_bank'},
    {'type':'site','url':'https://www.lazard.com/our-people','org':'Lazard','category':'investment_bank'},
    {'type':'site','url':'https://www.evercore.com/our-people','org':'Evercore','category':'investment_bank'},
    {'type':'site','url':'https://www.centerview.com/our-people','org':'Centerview','category':'investment_bank'},
    {'type':'site','url':'https://www.moelis.com/our-people','org':'Moelis & Co','category':'investment_bank'},
    {'type':'site','url':'https://www.pjt.com/our-people','org':'PJT Partners','category':'investment_bank'},
]

from serl import router as serl_router

# ─── App State ──────────────────────────────────────────────────────────────

app = FastAPI(title="MEMBRA — Intellectual Capital OS + Email Crawler Dashboard")
app.include_router(make_router(poptimizer))
app.include_router(serl_router)
init_db()

jobs = {
    'job1': {'crawler': None, 'thread': None, 'sources': JOB1_SOURCES, 'name': 'IP & M&A Lawyers'},
    'job2': {'crawler': None, 'thread': None, 'sources': JOB2_SOURCES, 'name': 'Hedge Funds + VC/PE + Tech Transfer + IP Brokers + Banks'},
}
ws_clients = set()

def run_job(job_id):
    c = jobs[job_id]['crawler']
    if c is None: return
    c.run(jobs[job_id]['sources'])
    try:
        run_etl(save=True)
    except Exception as e:
        log.warning(f"[ETL] post-crawl receipt failed: {e}")

def start_job(job_id):
    if jobs[job_id]['crawler'] and jobs[job_id]['crawler'].status == 'running':
        return False
    c = Crawler(job_id=job_id)
    jobs[job_id]['crawler'] = c
    t = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    jobs[job_id]['thread'] = t
    t.start()
    return True

def stop_job(job_id):
    if jobs[job_id]['crawler']:
        jobs[job_id]['crawler'].status = 'stopped'
        return True
    return False

def get_job_status(job_id):
    c = jobs[job_id]['crawler']
    if c is None:
        return {'status': 'idle', 'count': 0, 'pages': 0, 'current_org': '', 'logs': []}
    return {
        'status': c.status,
        'count': c.count,
        'pages': c.pages,
        'current_org': c.current_org,
        'logs': c.log_lines[-20:],
    }

# ─── API ────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    return get_db_stats()

@app.get("/api/job/{job_id}/status")
async def api_job_status(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "unknown job"}, 404)
    return {'job_id': job_id, 'name': jobs[job_id]['name'], **get_job_status(job_id)}

@app.post("/api/job/{job_id}/start")
async def api_job_start(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "unknown job"}, 404)
    ok = start_job(job_id)
    return {'started': ok, 'job_id': job_id, 'name': jobs[job_id]['name']}

@app.post("/api/job/{job_id}/stop")
async def api_job_stop(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "unknown job"}, 404)
    ok = stop_job(job_id)
    return {'stopped': ok, 'job_id': job_id}

@app.post("/api/start-all")
async def api_start_all():
    r1 = start_job('job1')
    r2 = start_job('job2')
    return {'job1': r1, 'job2': r2}

@app.post("/api/stop-all")
async def api_stop_all():
    r1 = stop_job('job1')
    r2 = stop_job('job2')
    return {'job1': r1, 'job2': r2}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "email-crawler", "port": int(os.environ.get("PORT", 7860))}

@app.get("/api/categories")
async def api_categories():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category ORDER BY COUNT(*) DESC")
    rows = c.fetchall()
    conn.close()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows]}

@app.get("/api/organizations")
async def api_organizations(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT organization, COUNT(*) as cnt, AVG(response_likelihood) as avg_score FROM emails GROUP BY organization ORDER BY cnt DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    conn.close()
    return {"organizations": [{"name": r[0], "email_count": r[1], "avg_score": round(r[2] or 0, 1)} for r in rows]}

@app.get("/api/search")
async def api_search(q: str = '', category: str = '', min_score: int = 0, limit: int = 100, offset: int = 0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    conditions = []
    params = []
    if q:
        conditions.append("(email LIKE ? OR name LIKE ? OR organization LIKE ? OR title LIKE ?)")
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%'])
    if category:
        conditions.append("category=?")
        params.append(category)
    if min_score:
        conditions.append("response_likelihood>=?")
        params.append(min_score)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    c.execute(f"SELECT COUNT(*) FROM emails{where}", params)
    total = c.fetchone()[0]
    q2 = f"SELECT email,name,title,organization,category,location,phones,source_url,response_likelihood,job_id FROM emails{where} ORDER BY response_likelihood DESC LIMIT ? OFFSET ?"
    c.execute(q2, params + [limit, offset])
    rows = c.fetchall()
    conn.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [{'email':r[0],'name':r[1],'title':r[2],'organization':r[3],'category':r[4],
                     'location':r[5],'phones':json.loads(r[6]) if r[6] else [],'source_url':r[7],
                     'response_likelihood':r[8],'job_id':r[9]} for r in rows]
    }

@app.get("/api/email/{email_id}")
async def api_email_detail(email_id: str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    eid = hashlib.md5(email_id.lower().encode()).hexdigest()
    c.execute("SELECT email,name,title,organization,category,location,phones,source_url,keywords,role_scores,response_likelihood,dossier_text,cluster_id,collected_at,job_id FROM emails WHERE id=?", (eid,))
    r = c.fetchone()
    conn.close()
    if not r:
        return JSONResponse({"error": "not found"}, 404)
    return {'email':r[0],'name':r[1],'title':r[2],'organization':r[3],'category':r[4],
            'location':r[5],'phones':json.loads(r[6]) if r[6] else [],'source_url':r[7],
            'keywords':json.loads(r[8]) if r[8] else [],'role_scores':json.loads(r[9]) if r[9] else {},
            'response_likelihood':r[10],'dossier_text':r[11],'cluster_id':r[12],
            'collected_at':r[13],'job_id':r[14]}

@app.get("/api/export/csv")
async def api_export_csv(category: str = '', min_score: int = 0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    q = "SELECT email,name,title,organization,category,location,phones,source_url,response_likelihood,job_id FROM emails"
    conditions = []
    params = []
    if category: conditions.append("category=?"); params.append(category)
    if min_score: conditions.append("response_likelihood>=?"); params.append(min_score)
    if conditions: q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY response_likelihood DESC"
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['email','name','title','organization','category','location','phones','source_url','response_likelihood','job_id'])
    for r in rows:
        writer.writerow([r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="emails_export.csv"'})

@app.get("/api/export/json")
async def api_export_json(category: str = '', min_score: int = 0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    q = "SELECT email,name,title,organization,category,location,phones,source_url,response_likelihood,job_id FROM emails"
    conditions = []
    params = []
    if category: conditions.append("category=?"); params.append(category)
    if min_score: conditions.append("response_likelihood>=?"); params.append(min_score)
    if conditions: q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY response_likelihood DESC"
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    data = [{'email':r[0],'name':r[1],'title':r[2],'organization':r[3],'category':r[4],
             'location':r[5],'phones':json.loads(r[6]) if r[6] else [],'source_url':r[7],
             'response_likelihood':r[8],'job_id':r[9]} for r in rows]
    return JSONResponse(data, headers={'Content-Disposition': 'attachment; filename="emails_export.json"'})

@app.get("/api/etl/receipt/{receipt_id}")
async def api_etl_receipt_detail(receipt_id: str):
    from layer_crawler_etl import RECEIPTS_DIR
    path = RECEIPTS_DIR / f"{receipt_id}.json"
    if not path.exists():
        return JSONResponse({"error": "receipt not found"}, 404)
    return json.loads(path.read_text(encoding='utf-8'))

@app.get("/hf-space")
async def hf_space_meta():
    return {
        "title": "Email Crawler Dashboard",
        "sdk": "docker",
        "app_port": int(os.environ.get("PORT", 7860)),
        "endpoints": [
            {"method": "GET", "path": "/", "desc": "Dashboard UI"},
            {"method": "GET", "path": "/health", "desc": "Health check"},
            {"method": "GET", "path": "/api/stats", "desc": "Database stats"},
            {"method": "GET", "path": "/api/categories", "desc": "List categories with counts"},
            {"method": "GET", "path": "/api/organizations", "desc": "List organizations with counts and avg scores"},
            {"method": "GET", "path": "/api/emails", "desc": "Paginated email list with filters"},
            {"method": "GET", "path": "/api/search", "desc": "Full-text search across emails"},
            {"method": "GET", "path": "/api/email/{id}", "desc": "Single email dossier"},
            {"method": "GET", "path": "/api/export/csv", "desc": "Export all emails as CSV"},
            {"method": "GET", "path": "/api/export/json", "desc": "Export all emails as JSON"},
            {"method": "POST", "path": "/api/job/{job_id}/start", "desc": "Start crawl job"},
            {"method": "POST", "path": "/api/job/{job_id}/stop", "desc": "Stop crawl job"},
            {"method": "POST", "path": "/api/start-all", "desc": "Start all crawl jobs"},
            {"method": "POST", "path": "/api/stop-all", "desc": "Stop all crawl jobs"},
            {"method": "POST", "path": "/api/etl/run", "desc": "Run ETL audit"},
            {"method": "GET", "path": "/api/etl/score", "desc": "Latest ETL scores"},
            {"method": "GET", "path": "/api/etl/receipts", "desc": "List all receipts"},
            {"method": "GET", "path": "/api/etl/receipt/{id}", "desc": "Single receipt detail"},
            {"method": "GET", "path": "/api/etl/run/latest", "desc": "Latest ETL run summary"},
            {"method": "GET", "path": "/hf-space", "desc": "This metadata"},
        ],
        "crawler_jobs": list(jobs.keys()),
        "etl_layers": ["source_registry", "subject_crawlers", "etl", "scoring", "action"],
    }

@app.get("/api/emails")
async def api_emails(limit: int = 100, offset: int = 0, category: str = '', min_score: int = 0):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    q = "SELECT email,name,title,organization,category,location,phones,source_url,response_likelihood,job_id FROM emails"
    conditions = []
    params = []
    if category: conditions.append("category=?"); params.append(category)
    if min_score: conditions.append("response_likelihood>=?"); params.append(min_score)
    if conditions: q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY response_likelihood DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    return [{'email':r[0],'name':r[1],'title':r[2],'organization':r[3],'category':r[4],
             'location':r[5],'phones':json.loads(r[6]) if r[6] else [],'source_url':r[7],
             'response_likelihood':r[8],'job_id':r[9]} for r in rows]

@app.post("/api/etl/run")
async def api_etl_run():
    import asyncio as _a
    loop = _a.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: run_etl(save=True))
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

@app.get("/api/etl/receipts")
async def api_etl_receipts():
    return {"receipts": list_receipts()}

@app.get("/api/etl/run/latest")
async def api_etl_latest():
    run = latest_run()
    if run is None:
        return JSONResponse({"error": "no etl run yet"}, 404)
    return run

@app.get("/api/etl/score")
async def api_etl_score():
    run = latest_run()
    if run is None:
        return JSONResponse({"error": "no etl run yet"}, 404)
    return {
        "run_id": run.get("run_id"),
        "timestamp": run.get("timestamp"),
        "aggregate_scores": run.get("aggregate_scores", {}),
        "hardening_actions": run.get("hardening_actions", []),
    }

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            stats = get_db_stats()
            j1 = get_job_status('job1')
            j2 = get_job_status('job2')
            await ws.send_json({
                'stats': stats,
                'job1': {'name': jobs['job1']['name'], **j1},
                'job2': {'name': jobs['job2']['name'], **j2},
            })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        ws_clients.discard(ws)
    except:
        ws_clients.discard(ws)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Email Crawler - Dual Job Runner</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'SF Mono',Monaco,Consolas,monospace; background:#0a0a0a; color:#e0e0e0; padding:20px; }
h1 { font-size:22px; margin-bottom:16px; color:#fff; }
h2 { font-size:16px; margin-bottom:8px; color:#aaa; text-transform:uppercase; letter-spacing:1px; }
.stats { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:24px; }
.stat { background:#1a1a1a; border:1px solid #333; border-radius:8px; padding:16px; text-align:center; }
.stat .num { font-size:28px; font-weight:bold; color:#4fc3f7; }
.stat .label { font-size:11px; color:#888; margin-top:4px; text-transform:uppercase; }
.stat.vip .num { color:#ffd700; }
.stat.high .num { color:#81c784; }
.jobs { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:24px; }
.job { background:#1a1a1a; border:1px solid #333; border-radius:8px; padding:16px; }
.job-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.job-name { font-size:14px; color:#fff; font-weight:bold; }
.job-status { padding:3px 10px; border-radius:12px; font-size:11px; font-weight:bold; }
.job-status.running { background:#2e7d32; color:#fff; }
.job-status.idle { background:#555; color:#aaa; }
.job-status.done { background:#1565c0; color:#fff; }
.job-status.stopped { background:#c62828; color:#fff; }
.job-controls { display:flex; gap:8px; margin-bottom:12px; }
.btn { padding:6px 16px; border:none; border-radius:6px; cursor:pointer; font-size:12px; font-family:inherit; }
.btn-start { background:#2e7d32; color:#fff; }
.btn-stop { background:#c62828; color:#fff; }
.btn:hover { opacity:0.85; }
.job-info { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:12px; }
.job-info .info { background:#222; border-radius:6px; padding:8px; text-align:center; }
.job-info .info .v { font-size:18px; color:#4fc3f7; font-weight:bold; }
.job-info .info .k { font-size:10px; color:#888; }
.logs { background:#111; border:1px solid #222; border-radius:6px; padding:8px; height:200px; overflow-y:auto; font-size:11px; line-height:1.6; }
.logs .line { color:#aaa; }
.logs .line:has(⭐) { color:#ffd700; }
.controls { margin-bottom:16px; }
.btn-big { padding:10px 24px; font-size:14px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th { background:#1a1a1a; padding:8px; text-align:left; color:#888; border-bottom:1px solid #333; }
td { padding:6px 8px; border-bottom:1px solid #222; }
tr:hover { background:#1a1a1a; }
.etl-panel { background:#1a1a1a; border:1px solid #333; border-radius:8px; padding:16px; margin-bottom:24px; }
.etl-controls { margin-bottom:12px; }
.etl-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }
.etl-stat { background:#222; border-radius:6px; padding:12px; text-align:center; }
.etl-stat .num { font-size:24px; font-weight:bold; color:#4fc3f7; }
.etl-stat .label { font-size:10px; color:#888; margin-top:4px; text-transform:uppercase; }
.etl-actions { background:#111; border:1px solid #222; border-radius:6px; padding:12px; }
.etl-actions .label { font-size:11px; color:#888; text-transform:uppercase; margin-bottom:8px; }
.etl-actions ul { margin:0; padding-left:18px; font-size:12px; color:#aaa; }
.etl-actions li { margin-bottom:6px; }
.score { font-weight:bold; }
.score-high { color:#81c784; }
.score-vip { color:#ffd700; }
.score-mid { color:#4fc3f7; }
.score-low { color:#666; }
.cat-badge { padding:2px 8px; border-radius:4px; font-size:10px; }
.cat-ip_lawyer { background:#1a237e; color:#90caf9; }
.cat-ma_lawyer { background:#0d4740; color:#80cbc4; }
.cat-hedge_fund { background:#4a148c; color:#ce93d8; }
.cat-pe_firm { background:#3e2723; color:#bcaaa4; }
.cat-vc_firm { background:#1b5e20; color:#a5d6a7; }
.cat-tech_transfer { background:#e65100; color:#ffcc80; }
.cat-ip_broker { background:#827717; color:#dce775; }
.cat-ip_valuation { background:#263238; color:#b0bec5; }
.cat-investment_bank { background:#37474f; color:#cfd8dc; }
</style>
</head>
<body>
<h1>📧 Email Crawler — Dual Job Runner</h1>

<div class="controls">
<button class="btn btn-start btn-big" onclick="startAll()">▶ Start Both Jobs</button>
</div>

<div class="stats" id="stats">
<div class="stat"><div class="num" id="total">0</div><div class="label">Total Emails</div></div>
<div class="stat high"><div class="num" id="high">0</div><div class="label">High (≥70)</div></div>
<div class="stat vip"><div class="num" id="vip">0</div><div class="label">VIP (≥90)</div></div>
<div class="stat"><div class="num" id="orgs">0</div><div class="label">Organizations</div></div>
<div class="stat"><div class="num" id="urls">0</div><div class="label">Source URLs</div></div>
</div>

<div class="jobs">
<div class="job" id="job1-card">
<div class="job-header"><span class="job-name" id="job1-name">Job 1</span><span class="job-status idle" id="job1-status">IDLE</span></div>
<div class="job-controls"><button class="btn btn-start" onclick="startJob('job1')">Start</button><button class="btn btn-stop" onclick="stopJob('job1')">Stop</button></div>
<div class="job-info"><div class="info"><div class="v" id="job1-count">0</div><div class="k">Emails</div></div><div class="info"><div class="v" id="job1-pages">0</div><div class="k">Pages</div></div><div class="info"><div class="v" id="job1-org">—</div><div class="k">Current</div></div></div>
<div class="logs" id="job1-logs"></div>
</div>
<div class="job" id="job2-card">
<div class="job-header"><span class="job-name" id="job2-name">Job 2</span><span class="job-status idle" id="job2-status">IDLE</span></div>
<div class="job-controls"><button class="btn btn-start" onclick="startJob('job2')">Start</button><button class="btn btn-stop" onclick="stopJob('job2')">Stop</button></div>
<div class="job-info"><div class="info"><div class="v" id="job2-count">0</div><div class="k">Emails</div></div><div class="info"><div class="v" id="job2-pages">0</div><div class="k">Pages</div></div><div class="info"><div class="v" id="job2-org">—</div><div class="k">Current</div></div></div>
<div class="logs" id="job2-logs"></div>
</div>
</div>

<h2>Top Emails by Response Likelihood</h2>
<table id="email-table"><thead><tr><th>Score</th><th>Email</th><th>Name</th><th>Title</th><th>Organization</th><th>Category</th><th>Location</th><th>Phone</th></tr></thead><tbody></tbody></table>

<h2>Layer Crawler ETL — Receipts & Hardening</h2>
<div class="etl-panel">
  <div class="etl-controls"><button class="btn btn-start" id="etl-run-btn">▶ Run ETL Audit</button></div>
  <div class="etl-grid">
    <div class="etl-stat"><div class="num" id="etl-evidence">—</div><div class="label">Evidence</div></div>
    <div class="etl-stat"><div class="num" id="etl-prod">—</div><div class="label">ProdScore</div></div>
    <div class="etl-stat"><div class="num" id="etl-harden">—</div><div class="label">HardenRank</div></div>
    <div class="etl-stat"><div class="num" id="etl-ip">—</div><div class="label">IP Risk</div></div>
  </div>
  <div class="etl-actions">
    <div class="label">Hardening Actions</div>
    <ul id="etl-actions"></ul>
  </div>
</div>

<script>
let ws;
function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    updateStats(d.stats);
    updateJob('job1', d.job1);
    updateJob('job2', d.job2);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}
connectWS();

function updateStats(s) {
  document.getElementById('total').textContent = s.total;
  document.getElementById('high').textContent = s.high;
  document.getElementById('vip').textContent = s.vip;
  document.getElementById('orgs').textContent = s.orgs;
  document.getElementById('urls').textContent = s.total;
}

function updateJob(id, j) {
  document.getElementById(id+'-name').textContent = j.name;
  document.getElementById(id+'-count').textContent = j.count;
  document.getElementById(id+'-pages').textContent = j.pages;
  document.getElementById(id+'-org').textContent = j.current_org ? j.current_org.substring(0,15) : '—';
  const st = document.getElementById(id+'-status');
  st.textContent = j.status.toUpperCase();
  st.className = 'job-status ' + j.status;
  const logs = document.getElementById(id+'-logs');
  logs.innerHTML = j.logs.map(l => `<div class="line">${l}</div>`).join('');
  logs.scrollTop = logs.scrollHeight;
}

async function startJob(id) { await fetch(`/api/job/${id}/start`, {method:'POST'}); }
async function stopJob(id) { await fetch(`/api/job/${id}/stop`, {method:'POST'}); }
async function startAll() { await fetch('/api/start-all', {method:'POST'}); }

async function loadEmails() {
  const r = await fetch('/api/emails?limit=100&min_score=0');
  const emails = await r.json();
  const tbody = document.querySelector('#email-table tbody');
  tbody.innerHTML = emails.map(e => {
    const sc = e.response_likelihood;
    const cls = sc>=90?'score-vip':sc>=70?'score-high':sc>=50?'score-mid':'score-low';
    const cat = e.category||'unknown';
    const phone = (e.phones&&e.phones[0])||'';
    return `<tr><td class="score ${cls}">${sc}</td><td>${e.email}</td><td>${e.name||''}</td><td>${e.title||''}</td><td>${e.organization||''}</td><td><span class="cat-badge cat-${cat}">${cat}</span></td><td>${e.location||''}</td><td>${phone}</td></tr>`;
  }).join('');
}
setInterval(loadEmails, 5000);
loadEmails();

async function loadEtl() {
    const r = await fetch('/api/etl/score');
    if (!r.ok) return;
    const s = await r.json();
    const sc = s.aggregate_scores || {};
    document.getElementById('etl-evidence').textContent = sc.evidence ?? '—';
    document.getElementById('etl-prod').textContent = sc.prod_score ?? '—';
    document.getElementById('etl-harden').textContent = sc.harden_rank ?? '—';
    document.getElementById('etl-ip').textContent = sc.ip_risk ?? '—';
    const ul = document.getElementById('etl-actions');
    ul.innerHTML = (s.hardening_actions || []).map(a => `<li>${a}</li>`).join('');
}
document.getElementById('etl-run-btn').addEventListener('click', async () => {
    await fetch('/api/etl/run', {method:'POST'});
    loadEtl();
});
setInterval(loadEtl, 10000);
loadEtl();
</script>
</body>
</html>'''

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
