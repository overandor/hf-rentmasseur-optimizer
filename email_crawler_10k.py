"""
10K Email Crawler with Micro-Dossiers, Clustering & Response Likelihood
- Crawls public pages, extracts emails + phones + names + titles
- Builds micro-dossier per email (org, role, location, category, keywords)
- Clusters by domain/organization
- Scores response likelihood (0-100) based on heuristics
- No crawl limit, targets 10K+
"""

import os, re, json, time, sqlite3, hashlib, logging, requests, csv
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from datetime import datetime
from pathlib import Path
import urllib3
from collections import defaultdict
urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('/tmp/crawler10k.log'), logging.StreamHandler()])
log = logging.getLogger('crawler')

DB = str(Path(__file__).parent / 'data' / 'emails10k.db')
os.makedirs(os.path.dirname(DB), exist_ok=True)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:\+?1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})')
NAME_RE = re.compile(r'([A-Z][a-z]+ [A-Z][a-z]+)')
TITLE_RE = re.compile(r'(Partner|Associate|Counsel|Managing Director|Director|VP|Vice President|Principal|Senior|Junior|Attorney|Lawyer|Analyst|Consultant|Advisor|Head|Chief|Founder|Co-Founder|CEO|CFO|COO|CTO|President|Chairman|Of Counsel)', re.I)
LOC_RE = re.compile(r'(New York|San Francisco|Los Angeles|Chicago|Boston|Washington|Houston|Dallas|Atlanta|Miami|Seattle|Denver|London|Paris|Frankfurt|Tokyo|Hong Kong|Singapore|Dubai|Zurich|Geneva|Toronto|Sydney|Palo Alto|Menlo Park|Austin|Silicon Valley)', re.I)

JUNK = {'wixpress.com','example.com','sentry.io','cloudflare.com','godaddy.com',
        'squarespace.com','wordpress.com','google.com','facebook.com','twitter.com',
        'linkedin.com','instagram.com','youtube.com','github.com','medium.com',
        'substack.com','mailchimp.com','hubspot.com','typepad.com','blogspot.com'}

ROLE_KEYWORDS = {
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
    if len(e) > 80:
        return False
    dom = e.split('@')[1] if '@' in e else ''
    if dom in JUNK or '.' not in dom:
        return False
    local = e.split('@')[0]
    if local.isdigit():
        return False
    return True

def extract_phones(text):
    phones = set()
    for m in PHONE_RE.findall(text):
        p = f"({m[0]}) {m[1]}-{m[2]}"
        if m[0] not in ('000','999','111') and m[1] not in ('000','999'):
            phones.add(p)
    return list(phones)

def classify_role(page_text, email, org=''):
    """Classify email into a role category based on page content."""
    text_lower = page_text.lower()
    scores = defaultdict(int)
    for cat, keywords in ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[cat] += 1
    if scores:
        return max(scores, key=scores.get), dict(scores)
    return 'unknown', {}

def score_response_likelihood(email, name, title, org, category, phones, page_text):
    """Score 0-100 how likely this person is to respond to outreach."""
    score = 30  # base
    local = email.split('@')[0].lower()
    domain = email.split('@')[1].lower() if '@' in email else ''
    
    # Personal email (first.last@) = more likely to reach a person
    if '.' in local and not local.startswith('info') and not local.startswith('contact'):
        score += 20
    if name:
        score += 10
    if title:
        score += 10
    if phones:
        score += 10
    
    # Senior roles more likely to respond to IP/hedge fund outreach
    senior = ['partner','managing director','head','chief','founder','ceo','president','chairman','principal']
    if title and any(s in title.lower() for s in senior):
        score += 15
    elif title and any(s in title.lower() for s in ['associate','analyst','junior']):
        score -= 5
    
    # Generic emails less likely
    if local in ['info','contact','admin','support','webmaster','office','reception','general']:
        score -= 15
    
    # Category bonus - IP lawyers and brokers more likely to respond to IP inquiries
    if category in ('ip_lawyer','ip_broker','ip_valuation','tech_transfer'):
        score += 10
    if category in ('hedge_fund','pe_firm','vc_firm'):
        score += 5
    
    # Org size heuristic - big firms have more gatekeepers
    big_firms = ['kirkland','latham','skadden','davis','sullivan','hogan','baker','jones',
                 'goldman','morgan','jpmorgan','blackstone','kkr','carlyle','apollo']
    if any(b in domain for b in big_firms):
        score -= 5
    
    # Has bio page with substantive content
    if len(page_text) > 500:
        score += 5
    
    return max(0, min(100, score))

def build_dossier(email, name, title, org, category, phones, location, url, page_text, role_scores):
    """Build a micro-dossier for this email."""
    # Extract keywords from page
    keywords = []
    text_lower = page_text.lower()
    ip_terms = ['patent','trademark','copyright','ip','intellectual property','licensing',
                'merger','acquisition','hedge fund','private equity','venture capital',
                'portfolio','arbitration','litigation','prosecution','valuation','royalty']
    for term in ip_terms:
        if term in text_lower:
            keywords.append(term)
    
    dossier = {
        'email': email,
        'name': name or '',
        'title': title or '',
        'organization': org or '',
        'category': category,
        'location': location or '',
        'phones': phones[:3],  # max 3
        'source_url': url,
        'keywords': list(set(keywords))[:10],
        'role_scores': role_scores,
        'response_likelihood': score_response_likelihood(email, name, title, org, category, phones, page_text),
        'dossier_text': f"{name or 'Unknown'} - {title or 'Unknown role'} at {org or 'Unknown org'}. "
                       f"Category: {category}. Location: {location or 'Unknown'}. "
                       f"Keywords: {', '.join(keywords[:5])}. "
                       f"Phones: {', '.join(phones[:2])}. "
                       f"Response likelihood: {score_response_likelihood(email, name, title, org, category, phones, page_text)}/100.",
        'collected_at': datetime.now().isoformat(),
    }
    return dossier

# ─── Database ───────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY, email TEXT, name TEXT, title TEXT, organization TEXT,
        category TEXT, location TEXT, phones TEXT, source_url TEXT, keywords TEXT,
        role_scores TEXT, response_likelihood INTEGER, dossier_text TEXT,
        cluster_id TEXT, collected_at TEXT
    )''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_email ON emails(email)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_cat ON emails(category)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_org ON emails(organization)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_score ON emails(response_likelihood DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_cluster ON emails(cluster_id)''')
    conn.commit()
    conn.close()

def save_dossier(d):
    eid = hashlib.md5(f"{d['email']}:{d['source_url']}".encode()).hexdigest()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM emails WHERE id=?", (eid,))
    if c.fetchone():
        conn.close()
        return False
    c.execute("""INSERT OR IGNORE INTO emails
        (id,email,name,title,organization,category,location,phones,source_url,
         keywords,role_scores,response_likelihood,dossier_text,cluster_id,collected_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eid, d['email'], d['name'], d['title'], d['organization'], d['category'],
         d['location'], json.dumps(d['phones']), d['source_url'],
         json.dumps(d['keywords']), json.dumps(d['role_scores']),
         d['response_likelihood'], d['dossier_text'], '', d['collected_at']))
    conn.commit()
    conn.close()
    return True

def get_count():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM emails")
    n = c.fetchone()[0]
    conn.close()
    return n

def update_clusters():
    """Cluster emails by organization domain."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, email, organization FROM emails")
    rows = c.fetchall()
    
    clusters = defaultdict(list)
    for eid, email, org in rows:
        domain = email.split('@')[1] if '@' in email else 'unknown'
        # Cluster by domain
        cluster_id = hashlib.md5(domain.encode()).hexdigest()[:8]
        clusters[cluster_id].append(eid)
    
    for cid, eids in clusters.items():
        for eid in eids:
            c.execute("UPDATE emails SET cluster_id=? WHERE id=?", (cid, eid))
    
    conn.commit()
    conn.close()
    return len(clusters)

# ─── Crawler ────────────────────────────────────────────────────────────────

class Crawler:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        self.visited = set()
        self.count = 0
    
    def fetch(self, url):
        if url in self.visited:
            return None, None, None
        self.visited.add(url)
        try:
            r = self.s.get(url, timeout=12, verify=False, allow_redirects=True)
            if r.status_code != 200:
                return None, None, None
            soup = BeautifulSoup(r.text, 'html.parser')
            return r.text, soup, soup.get_text()
        except:
            return None, None, None
    
    def extract_emails_from_page(self, html, text):
        emails = set(EMAIL_RE.findall(html))
        emails.update(EMAIL_RE.findall(text))
        return [e.lower() for e in emails if is_real_email(e)]
    
    def find_name_near(self, text, email):
        idx = text.find(email)
        if idx >= 0:
            before = text[max(0, idx-200):idx]
            names = NAME_RE.findall(before)
            if names:
                return names[-1]
            after = text[idx:idx+200]
            names = NAME_RE.findall(after)
            if names:
                return names[0]
        return ''
    
    def find_title_near(self, text, email):
        idx = text.find(email)
        if idx >= 0:
            around = text[max(0, idx-300):idx+300]
            titles = TITLE_RE.findall(around)
            if titles:
                return titles[0]
        return ''
    
    def find_location_near(self, text, email):
        idx = text.find(email)
        if idx >= 0:
            around = text[max(0, idx-500):idx+500]
            locs = LOC_RE.findall(around)
            if locs:
                return locs[0]
        return ''
    
    def process_page(self, url, html, soup, text, category='', org=''):
        """Extract all data from a page and save dossiers."""
        emails = self.extract_emails_from_page(html, text)
        phones = extract_phones(text)
        page_count = 0
        
        for email in emails:
            if not is_real_email(email):
                continue
            
            name = self.find_name_near(text, email)
            title = self.find_title_near(text, email)
            location = self.find_location_near(text, email)
            
            # Classify role
            cat, role_scores = classify_role(text, email, org)
            if category and cat == 'unknown':
                cat = category
            
            dossier = build_dossier(email, name, title, org, cat, phones, location, url, text, role_scores)
            
            if save_dossier(dossier):
                page_count += 1
                self.count += 1
                rl = dossier['response_likelihood']
                marker = '⭐' if rl >= 70 else '✉️'
                log.info(f"    {marker} [{rl}] {email} | {name or '?'} | {title or '?'} | {org or '?'}")
        
        return page_count, emails
    
    def find_sublinks(self, soup, base_url, keywords):
        if not soup:
            return []
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            txt = a.get_text().strip().lower()
            full = urljoin(base_url, href)
            if urlparse(full).netloc != urlparse(base_url).netloc:
                continue
            href_l = href.lower()
            if any(kw in href_l or kw in txt for kw in keywords):
                if full not in self.visited and full not in links:
                    links.append(full)
        return links
    
    def crawl_site(self, base_url, category='', org='', max_pages=40):
        kw = ['attorney','lawyer','partner','team','people','professional','staff',
              'contact','about','bio','profile','directory','member','consultant',
              'advisor','our-people','professionals','lawyers']
        
        queue = [base_url]
        pages = 0
        site_emails = 0
        
        while queue and pages < max_pages:
            url = queue.pop(0)
            html, soup, text = self.fetch(url)
            if html is None:
                continue
            pages += 1
            
            n, _ = self.process_page(url, html, soup, text, category, org)
            site_emails += n
            
            # Find more pages
            links = self.find_sublinks(soup, url, kw)
            # Prioritize profile pages
            profiles = [l for l in links if any(k in l.lower() for k in ['bio','profile','attorney','lawyer','people'])]
            others = [l for l in links if l not in profiles]
            queue = profiles[:15] + queue + others[:5]
            
            time.sleep(0.2)
        
        log.info(f"  {org or base_url[:40]}: {pages}p, {site_emails}e (total: {self.count})")
        return site_emails
    
    def crawl_directory(self, url, category, max_listings=80):
        html, soup, text = self.fetch(url)
        if html is None:
            return 0
        
        n, _ = self.process_page(url, html, soup, text, category)
        
        # Find listing links
        listings = []
        if soup:
            for a in soup.find_all('a', href=True):
                href = urljoin(url, a['href'])
                txt = a.get_text().strip()
                if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+', txt) and len(txt) < 60:
                    listings.append((href, txt))
                elif any(k in href.lower() for k in ['profile','attorney','lawyer','detail','view','member','lawfirm']):
                    listings.append((href, txt))
        
        count = n
        for prof_url, link_name in listings[:max_listings]:
            html2, soup2, text2 = self.fetch(prof_url)
            if html2 is None:
                continue
            n, _ = self.process_page(prof_url, html2, soup2, text2, category)
            count += n
            time.sleep(0.2)
        
        log.info(f"  Dir {url[:50]}: {count}e (total: {self.count})")
        return count

# ─── Sources ────────────────────────────────────────────────────────────────

SOURCES = {
    'ip_lawyers': {
        'directories': [
            ("https://www.hg.org/law-firms/intellectual-property/california.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/new-york.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/texas.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/florida.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/illinois.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/massachusetts.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/intellectual-property/washington.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/patent-law/california.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/patent-law/new-york.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/patent-law/texas.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/trademark-law/california.html", 'ip_lawyer'),
            ("https://www.hg.org/law-firms/trademark-law/new-york.html", 'ip_lawyer'),
        ],
        'firms': [
            ("https://www.finnegan.com/en/professionals.html", "Finnegan", 'ip_lawyer'),
            ("https://www.fishjackson.com/people", "Fish & Richardson", 'ip_lawyer'),
            ("https://www.knobbe.com/people", "Knobbe Martens", 'ip_lawyer'),
            ("https://www.wilmerhale.com/en/people", "WilmerHale", 'ip_lawyer'),
            ("https://www.ropesgray.com/en/people", "Ropes & Gray", 'ip_lawyer'),
            ("https://www.cooley.com/people", "Cooley", 'ip_lawyer'),
            ("https://www.perkinscoie.com/en/professionals.html", "Perkins Coie", 'ip_lawyer'),
            ("https://www.morganlewis.com/en/people", "Morgan Lewis", 'ip_lawyer'),
            ("https://www.hoganlovells.com/en/people", "Hogan Lovells", 'ip_lawyer'),
            ("https://www.bakermckenzie.com/en/people", "Baker McKenzie", 'ip_lawyer'),
            ("https://www.jonesday.com/lawyers", "Jones Day", 'ip_lawyer'),
            ("https://www.goodwinlaw.com/en/people.html", "Goodwin", 'ip_lawyer'),
            ("https://www.arnoldporter.com/en/professionals", "Arnold & Porter", 'ip_lawyer'),
            ("https://www.crowell.com/people", "Crowell & Moring", 'ip_lawyer'),
            ("https://www.fenwick.com/people", "Fenwick & West", 'ip_lawyer'),
            ("https://www.mofo.com/people", "Morrison & Foerster", 'ip_lawyer'),
            ("https://www.gibsondunn.com/people", "Gibson Dunn", 'ip_lawyer'),
            ("https://www.lw.com/en/people", "Latham & Watkins", 'ma_lawyer'),
            ("https://www.kirkland.com/lawyers", "Kirkland & Ellis", 'ma_lawyer'),
            ("https://www.skadden.com/professionals", "Skadden", 'ma_lawyer'),
            ("https://www.davispolk.com/lawyers", "Davis Polk", 'ma_lawyer'),
            ("https://www.sullcrom.com/professionals", "Sullivan & Cromwell", 'ma_lawyer'),
            ("https://www.whitecase.com/people", "White & Case", 'ma_lawyer'),
            ("https://www.sidley.com/en/contact", "Sidley Austin", 'ip_lawyer'),
            ("https://www.winston.com/en/contact.html", "Winston & Strawn", 'ma_lawyer'),
            ("https://www.foley.com/contact", "Foley & Lardner", 'ip_lawyer'),
            ("https://www.akingump.com/en/contact", "Akin Gump", 'ip_lawyer'),
        ],
    },
    'hedge_funds': {
        'firms': [
            ("https://www.bridgewater.com/our-people", "Bridgewater", 'hedge_fund'),
            ("https://www.renaissance.com/about-us/our-people", "Renaissance Tech", 'hedge_fund'),
            ("https://www.aqr.com/About-Us/OurFirm", "AQR Capital", 'hedge_fund'),
            ("https://www.two-sigma.com/about/our-people", "Two Sigma", 'hedge_fund'),
            ("https://www.baupost.com/contact", "Baupost Group", 'hedge_fund'),
            ("https://www.pershingsquarecapital.com/contact", "Pershing Square", 'hedge_fund'),
            ("https://www.thirdpoint.com/contact", "Third Point", 'hedge_fund'),
            ("https://www.exoduspoint.com/contact", "ExodusPoint", 'hedge_fund'),
            ("https://www.maverickcapital.com/contact", "Maverick Capital", 'hedge_fund'),
            ("https://www.elliottmgmt.com/contact", "Elliott Management", 'hedge_fund'),
            ("https://www.citadel.com/about/our-people", "Citadel", 'hedge_fund'),
            ("https://www.point72.com/our-people", "Point72", 'hedge_fund'),
            ("https://www.millennium.com/about/our-people", "Millennium", 'hedge_fund'),
            ("https://www.balyasny.com/about/our-team", "Balyasny", 'hedge_fund'),
            ("https://www.deshaw.com/our-people", "D.E. Shaw", 'hedge_fund'),
            ("https://www.tudor.com/contact", "Tudor Investment", 'hedge_fund'),
            ("https://www.glenviewcapital.com/contact", "Glenview Capital", 'hedge_fund'),
            ("https://www.vikingglobal.com/contact", "Viking Global", 'hedge_fund'),
            ("https://www.rokoscapital.com/contact", "Rokos Capital", 'hedge_fund'),
            ("https://www.brevanhoward.com/contact", "Brevan Howard", 'hedge_fund'),
            ("https://www.capitalmgmt.com/contact", "Capital Management", 'hedge_fund'),
            ("https://www.fairholme.net/contact", "Fairholme", 'hedge_fund'),
            ("https://www.greenlightcapital.com/contact", "Greenlight Capital", 'hedge_fund'),
            ("https://www.tigerglobal.com/contact", "Tiger Global", 'hedge_fund'),
            ("https://www.coatue.com/contact", "Coatue", 'hedge_fund'),
            ("https://www.whalerockpoint.com/contact", "Whalerock Point", 'hedge_fund'),
            ("https://www.meritagefunds.com/contact", "Meritage Funds", 'hedge_fund'),
            ("https://www.anandacapital.com/contact", "Ananda Capital", 'hedge_fund'),
            ("https://www.sculptorcapital.com/contact", "Sculptor Capital", 'hedge_fund'),
            ("https://www.d1capital.com/contact", "D1 Capital", 'hedge_fund'),
        ],
    },
    'vc_pe': {
        'firms': [
            ("https://www.sequoiacap.com/people", "Sequoia Capital", 'vc_firm'),
            ("https://www.a16z.com/people/", "Andreessen Horowitz", 'vc_firm'),
            ("https://www.benchmark.com/people", "Benchmark", 'vc_firm'),
            ("https://www.indexventures.com/people", "Index Ventures", 'vc_firm'),
            ("https://www.accel.com/people", "Accel", 'vc_firm'),
            ("https://www.greylock.com/people", "Greylock", 'vc_firm'),
            ("https://www.bv.com/people", "Bessemer Venture", 'vc_firm'),
            ("https://www.kpcb.com/people", "Kleiner Perkins", 'vc_firm'),
            ("https://www.foundersfund.com/team", "Founders Fund", 'vc_firm'),
            ("https://www.lightspeedvp.com/people", "Lightspeed", 'vc_firm'),
            ("https://www.blackstone.com/our-people", "Blackstone", 'pe_firm'),
            ("https://www.kkr.com/our-people", "KKR", 'pe_firm'),
            ("https://www.carlyle.com/our-people", "Carlyle Group", 'pe_firm'),
            ("https://www.apollo.com/our-people", "Apollo Global", 'pe_firm'),
            ("https://www.baincapital.com/people", "Bain Capital", 'pe_firm'),
            ("https://www.tpghome.com/our-people", "TPG", 'pe_firm'),
            ("https://www.warburgpincus.com/people", "Warburg Pincus", 'pe_firm'),
            ("https://www.nea.com/team", "NEA", 'vc_firm'),
            ("https://www.ggvcapital.com/team", "GGV Capital", 'vc_firm'),
            ("https://www.ivp.com/team", "IVP", 'vc_firm'),
            ("https://www.battery.com/people", "Battery Ventures", 'vc_firm'),
            ("https://www.shastaventures.com/people", "Shasta Ventures", 'vc_firm'),
            ("https://www.felicis.com/team", "Felicis Ventures", 'vc_firm'),
            ("https://www.sparkcapital.com/people", "Spark Capital", 'vc_firm'),
            ("https://www.unionventures.com/people", "Union Square", 'vc_firm'),
            ("https://www.8vc.com/people", "8VC", 'vc_firm'),
            ("https://www.foundationcap.com/people", "Foundation Capital", 'vc_firm'),
            ("https://www.scaleventurepartners.com/people", "Scale VP", 'vc_firm'),
            ("https://www.insidellc.com/people", "Insight Partners", 'vc_firm'),
            ("https://www.generalatlantic.com/people", "General Atlantic", 'pe_firm'),
        ],
    },
    'tech_transfer': {
        'firms': [
            ("https://techtransfer.stanford.edu/people", "Stanford OTL", 'tech_transfer'),
            ("https://tlo.mit.edu/people", "MIT TLO", 'tech_transfer'),
            ("https://otd.harvard.edu/people", "Harvard OTD", 'tech_transfer'),
            ("https://otl.berkeley.edu/people", "Berkeley OTL", 'tech_transfer'),
            ("https://techtransfer.columbia.edu/people", "Columbia TTO", 'tech_transfer'),
            ("https://ott.yale.edu/people", "Yale OTT", 'tech_transfer'),
            ("https://www.princeton.edu/otl/people", "Princeton OTL", 'tech_transfer'),
            ("https://techtransfer.umich.edu/people", "Michigan TT", 'tech_transfer'),
            ("https://ott.cornell.edu/people", "Cornell OTT", 'tech_transfer'),
            ("https://www.upenn.edu/ott/people", "Penn OTT", 'tech_transfer'),
            ("https://www.ot Duke.edu/people", "Duke OTT", 'tech_transfer'),
            ("https://www.jhu.edu/ott/people", "Johns Hopkins OTT", 'tech_transfer'),
            ("https://www.washington.edu/ott/people", "UW OTT", 'tech_transfer'),
            ("https://www.stanford.edu/ott/people", "Stanford", 'tech_transfer'),
            ("https://www.northwestern.edu/ott/people", "Northwestern OTT", 'tech_transfer'),
        ],
    },
    'ip_brokers': {
        'firms': [
            ("https://www.icap.com/contact-us", "ICAP Patent Brokerage", 'ip_broker'),
            ("https://www.intven.com/contact", "Intellectual Ventures", 'ip_broker'),
            ("https://www.yet2.com/about/team", "yet2.com", 'ip_broker'),
            ("https://www.tynax.com/about", "Tynax", 'ip_broker'),
            ("https://www.ideabuyer.com/about", "IdeaBuyer", 'ip_broker'),
            ("https://www.aminnovation.com/about", "Amin Innovation", 'ip_broker'),
            ("https://www.ipmarketplace.com/about", "IP Marketplace", 'ip_broker'),
            ("https://www.spectrumip.com/about", "Spectrum IP", 'ip_broker'),
            ("https://www.acaciaresearch.com/contact", "Acacia Research", 'ip_broker'),
            ("https://www.ipcheckups.com/contact", "IP Checkups", 'ip_broker'),
        ],
    },
    'ip_valuation': {
        'firms': [
            ("https://www.royaltyrange.com/contact", "Royalty Range", 'ip_valuation'),
            ("https://www.ipmetrics.net/contact", "IP Metrics", 'ip_valuation'),
            ("https://www.duffandphelps.com/contact", "Duff & Phelps", 'ip_valuation'),
            ("https://www.fticonsulting.com/contact", "FTI Consulting", 'ip_valuation'),
            ("https://www.alixpartners.com/contact", "AlixPartners", 'ip_valuation'),
            ("https://www.berkeryresearch.com/contact", "Berkery Research", 'ip_valuation'),
            ("https://www.conventuslaw.com/contact", "Conventus Law", 'ip_valuation'),
            ("https://www.hillbirney.com/contact", "Hill Birney", 'ip_valuation'),
        ],
    },
    'investment_banks': {
        'firms': [
            ("https://www.goldmansachs.com/our-firm/people.html", "Goldman Sachs", 'investment_bank'),
            ("https://www.jpmorgan.com/our-firm/people", "JP Morgan", 'investment_bank'),
            ("https://www.morganstanley.com/people", "Morgan Stanley", 'investment_bank'),
            ("https://www.lazard.com/our-people", "Lazard", 'investment_bank'),
            ("https://www.evercore.com/our-people", "Evercore", 'investment_bank'),
            ("https://www.centerview.com/our-people", "Centerview", 'investment_bank'),
            ("https://www.moelis.com/our-people", "Moelis & Co", 'investment_bank'),
            ("https://www.pjt.com/our-people", "PJT Partners", 'investment_bank'),
            ("https://www.citi.com/about/people", "Citi", 'investment_bank'),
            ("https://www.baml.com/about/people", "BofA Merrill Lynch", 'investment_bank'),
        ],
    },
}

def main():
    log.info("=" * 60)
    log.info("10K EMAIL CRAWLER + DOSSIERS + CLUSTERING")
    log.info("=" * 60)
    
    init_db()
    crawler = Crawler()
    
    # Run all sources
    for source_group, data in SOURCES.items():
        log.info(f"\n{'='*40}\n{source_group.upper()}\n{'='*40}")
        
        # Directories first
        for url, cat in data.get('directories', []):
            crawler.crawl_directory(url, cat, max_listings=50)
            time.sleep(0.5)
        
        # Then firm sites
        for url, org, cat in data.get('firms', []):
            crawler.crawl_site(url, category=cat, org=org, max_pages=40)
            time.sleep(0.3)
    
    # Cluster
    n_clusters = update_clusters()
    
    # Stats
    total = get_count()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category ORDER BY COUNT(*) DESC")
    cats = c.fetchall()
    c.execute("SELECT COUNT(DISTINCT organization) FROM emails")
    orgs = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT source_url) FROM emails")
    urls = c.fetchone()[0]
    c.execute("SELECT AVG(response_likelihood) FROM emails")
    avg_rl = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM emails WHERE response_likelihood >= 70")
    high_rl = c.fetchone()[0]
    c.execute("SELECT email, name, title, organization, category, response_likelihood FROM emails ORDER BY response_likelihood DESC LIMIT 20")
    top = c.fetchall()
    conn.close()
    
    log.info(f"\n{'='*60}")
    log.info(f"COMPLETE: {total} emails | {orgs} orgs | {urls} URLs | {n_clusters} clusters")
    log.info(f"Avg response likelihood: {avg_rl:.0f}/100 | High (≥70): {high_rl}")
    log.info(f"{'='*60}")
    log.info("By category:")
    for cat, n in cats:
        log.info(f"  {cat}: {n}")
    log.info(f"\nTop 20 by response likelihood:")
    for e, n, t, o, cat, rl in top:
        log.info(f"  [{rl}] {e} | {n or '?'} | {t or '?'} | {o or '?'} | {cat}")
    
    # Export
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT email,name,title,organization,category,location,phones,source_url,keywords,response_likelihood,dossier_text,cluster_id FROM emails ORDER BY response_likelihood DESC")
    rows = c.fetchall()
    conn.close()
    
    json_path = str(Path(__file__).parent / 'data' / 'emails10k.json')
    with open(json_path, 'w') as f:
        json.dump([{
            'email': r[0], 'name': r[1], 'title': r[2], 'organization': r[3],
            'category': r[4], 'location': r[5], 'phones': json.loads(r[6]) if r[6] else [],
            'source_url': r[7], 'keywords': json.loads(r[8]) if r[8] else [],
            'response_likelihood': r[9], 'dossier': r[10], 'cluster_id': r[11]
        } for r in rows], f, indent=2)
    
    csv_path = str(Path(__file__).parent / 'data' / 'emails10k.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['email','name','title','organization','category','location','phones','source_url','keywords','response_likelihood','cluster_id'])
        for r in rows:
            w.writerow([r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6]) if r[6] else '',r[7],json.loads(r[8]) if r[8] else '',r[9],r[11]])
    
    log.info(f"\nExported: {json_path} + {csv_path}")

if __name__ == "__main__":
    main()
