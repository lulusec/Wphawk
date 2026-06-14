# WPHawk
> Asynchronous WordPress penetration testing framework
Built on `aiohttp` + `asyncio`. Every scan phase runs concurrently, every outbound request is rate-limited, and the entire result lands in your terminal with full ANSI color — no mandatory file writes.


## Requirements

- **Python 3.9+**
- pip packages: `aiohttp`, `aiosqlite`, `pyyaml` (optional — enables YAML templates)

No API keys. No external services required for basic scanning.

---

## Installation

### Windows

**Option A — Installer (recommended, double-click)**

```
1. Download or clone the repo
2. Double-click  install.bat
3. Open a NEW terminal — run:  wphawk -u https://target.com
```

The installer automatically:
- Finds your Python 3.9+ installation
- Installs `aiohttp`, `aiosqlite`, `pyyaml` via pip
- Creates a `wphawk.bat` shim in your Python Scripts directory (or `%USERPROFILE%\.local\bin`)
- Adds the shim directory to your user PATH if needed

**Option B — PowerShell manually**

```powershell
git clone https://github.com/yourusername/wphawk.git
cd wphawk
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Option C — Run directly without installing**

```powershell
git clone https://github.com/yourusername/wphawk.git
cd wphawk
& "C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe" -m pip install aiohttp aiosqlite pyyaml
& "C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe" wphawk.py -u https://target.com
```

> **Windows note:** If `python` opens the Microsoft Store instead of running Python, this is the App Execution Alias conflict. Use the full path to `python.exe` as shown above, or run `install.ps1` which detects and uses the real executable automatically.

---

### Linux / macOS

**Option A — Installer (recommended)**

```bash
git clone https://github.com/yourusername/wphawk.git
cd wphawk
chmod +x install.sh
./install.sh
# Open a new terminal, then:
wphawk -u https://target.com
```

No virtual environment required, but recommended for clean installs:

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install aiohttp aiofiles packaging requests
python wphawk.py -u https://target.com
```
## Requirements

- **Python 3.9+**
- pip packages: `aiohttp`, `aiosqlite`, `pyyaml` (optional — enables YAML templates)

No API keys. No external services required for basic scanning.

---

## Installation

### Windows

**Option A — Installer (recommended, double-click)**

```
1. Download or clone the repo
2. Double-click  install.bat
3. Open a NEW terminal — run:  wphawk -u https://target.com
```

The installer automatically:
- Finds your Python 3.9+ installation
- Installs `aiohttp`, `aiosqlite`, `pyyaml` via pip
- Creates a `wphawk.bat` shim in your Python Scripts directory (or `%USERPROFILE%\.local\bin`)
- Adds the shim directory to your user PATH if needed

**Option B — PowerShell manually**

```powershell
git clone https://github.com/yourusername/wphawk.git
cd wphawk
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Option C — Run directly without installing**

```powershell
git clone https://github.com/yourusername/wphawk.git
cd wphawk
& "C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe" -m pip install aiohttp aiosqlite pyyaml
& "C:\Users\<you>\AppData\Local\Programs\Python\Python313\python.exe" wphawk.py -u https://target.com
```

> **Windows note:** If `python` opens the Microsoft Store instead of running Python, this is the App Execution Alias conflict. Use the full path to `python.exe` as shown above, or run `install.ps1` which detects and uses the real executable automatically.

---



## Usage

### Basic scan

```bash
python wphawk.py -u https://target.com
```

### Aggressive enumeration (probes all plugins + themes from wordlists)

```bash
python wphawk.py -u https://target.com --aggressive
```

Wordlists in `wordlists/plugins.txt` and `wordlists/themes.txt` load automatically when `--aggressive` is used. Custom wordlists:

```bash
python wphawk.py -u https://target.com --aggressive \
  --wordlist-plugins /path/to/plugins.txt \
  --wordlist-themes  /path/to/themes.txt
```

### Full scan — everything in one flag

```bash
wphawk -u https://target.com --full-scan
```

### CVE template engine (local nuclei-style templates)

```bash
# Run templates from ./cve/ against detected components
python wphawk.py -u https://target.com --aggressive --local-cve

# Write all built-in templates to ./cve/ first, then run
python wphawk.py --seed-templates
python wphawk.py -u https://target.com --local-cve
```

### Authenticated scan (cookie session)

```bash
python wphawk.py -u https://target.com \
  --cookie "wordpress_logged_in_abc=xyz; wp-settings-1=..." \
  --auth-scan
```

### Through Burp Suite proxy

```bash
python wphawk.py -u https://target.com \
  --proxy http://127.0.0.1:8080 \
  --no-verify-ssl
```

### Save output

```bash
# JSON report → output/report-target.com.json
python wphawk.py -u https://target.com --json

# Dark-theme HTML report → output/report-target.com.html
python wphawk.py -u https://target.com --html

# Both + terminal output (default)
python wphawk.py -u https://target.com --json --html
```

### Brute force

```bash
# XML-RPC multicall (fast, amplified) — requires --aggressive to find users first
python wphawk.py -u https://target.com --aggressive --brute

# wp-login.php serial brute (slow, stealthy)
python wphawk.py -u https://target.com --brute-login --passwords /path/to/rockyou.txt
```

---

## Rate Limiting

WPHawk defaults to **10 req/s** — enough to scan fast without triggering rate-limit rules on most hosts.

```bash
# Stealth — 2 req/s, flies under most WAF thresholds
python wphawk.py -u https://target.com --aggressive --rps 2

# Default — 10 req/s
python wphawk.py -u https://target.com --aggressive

# Fast — 30 req/s (your own lab / staging server only)
python wphawk.py -u https://target.com --aggressive --rps 30

# Unlimited — no throttle (own infrastructure only)
python wphawk.py -u https://target.com --aggressive --rps 0
```

Scan stats print at the end of every run:
```
Scan stats: 847 requests · 91.3s · 9.3 req/s
```

---

## All Flags

```
Target
  -u, --url              Target WordPress URL (required)

Enumeration
  --enumerate            plugins | themes | users | all  (default: all)
  --aggressive           Enable HTTP probe enumeration against wordlists
  --wordlist             Single wordlist for both plugins and themes
  --wordlist-plugins     Plugin slug wordlist (default: wordlists/plugins.txt)
  --wordlist-themes      Theme slug wordlist  (default: wordlists/themes.txt)
  --max-users            Max author IDs to probe (default: 20)

Speed / Throttle
  --rps                  Max requests per second (default: 10.0 — use 0 for unlimited)
  --concurrency          Max parallel connections (default: 10)
  --delay                Delay between aggressive probes in seconds (default: 0.1)

Scan Modules
  --deep-recon           JS analysis, REST API discovery, robots.txt, crt.sh subdomains
  --cve                  CVE lookup via NVD / GitHub / Patchstack / Exploit-DB
  --refresh-cache        Re-fetch CVE data, ignore local cache
  --scan-backups         Probe for exposed backup archives
  --check-methods        Test dangerous HTTP methods (OPTIONS, TRACE, PUT)
  --timthumb             Scan for vulnerable TimThumb (CVE-2011-4106)
  --crawl-uploads        Crawl wp-content/uploads/ for sensitive exposed files

CVE Template Engine
  --local-cve            Run nuclei-style templates from ./cve/ directory
  --templates-dir        Custom template directory (default: ./cve/)
  --seed-templates       Write all built-in templates to templates dir and exit

Exploitation
  --exploit              Auto-exploit discovered CVEs + SSRF / XSS / Host Header
  --auth-scan            Run authenticated wp-admin scan after credential discovery
  --brute                XML-RPC multicall brute force
  --brute-login          wp-login.php serial brute force
  --passwords            Custom password wordlist path

Auth / Network
  --cookie               Session cookie string for authenticated scans
  --proxy                HTTP proxy URL (e.g. http://127.0.0.1:8080)
  --ua, --user-agent     Override User-Agent header
  --timeout              HTTP timeout in seconds (default: 30)
  --no-verify-ssl        Disable SSL certificate verification

Output
  --json                 Save JSON report to output/
  --html                 Save self-contained HTML report to output/
  --output               Custom .txt report path
  -v, --verbose          Show all probes, not just hits
```

---

## Features

| Category | What it does |
|---|---|
| **Fingerprinting** | WordPress version (6 sources), server stack, PHP, WAF detection, multisite, custom login URL |
| **Plugin / Theme enum** | Passive (HTML source) + aggressive HTTP probing, version from `readme.txt / readme.md / changelog.txt / CHANGELOG.md / index.html / slug.php` |
| **CVE matching** | NVD + GitHub Advisory + Patchstack + Exploit-DB, version-aware (flags only unpatched), 30+ built-in CVEs |
| **CVE template engine** | Nuclei-style `.json` templates in `cve/` — custom HTTP matchers, DSL expressions, regex, status checks |
| **User enumeration** | REST API (`/wp-json/wp/v2/users`), author redirect probing, login-error confirmation |
| **Deep recon** | JS secret scanning, REST API route discovery, `robots.txt`, `sitemap.xml`, subdomain enum via crt.sh |
| **Upload crawler** | Traverses `wp-content/uploads/` year/month structure + plugin-specific dirs, flags exposed SQL dumps / archives / keys |
| **Drop-in files** | Detects `db.php`, `object-cache.php`, `advanced-cache.php` — common backdoor persistence points |
| **MU-Plugins** | Scans `wp-content/mu-plugins/` for exposed PHP files and open directory listings |
| **GraphQL** | Detects WPGraphQL introspection, dumps exposed type list |
| **Security headers** | CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy |
| **Misc checks** | Open registration, directory listing, wp-cron exposure, debug.log, XML-RPC + multicall, backup files, TimThumb, dangerous HTTP methods |
| **Exploitation** | Auto-exploit CVEs, SSRF, XSS, Host Header injection, wp-config leak |
| **Brute force** | XML-RPC multicall (amplified) + wp-login.php serial, custom password wordlist |
| **Rate limiting** | Token-bucket limiter (`--rps`) — every request in every phase goes through it. No accidental DoS. |
| **Output** | Terminal-first (ANSI color). Optional `--json` / `--html` (self-contained dark-theme report). |

---

---

## CVE Templates

Templates live in `cve/` as plain JSON files. WPHawk ships with 20+ covering WordPress core and the most-exploited plugins. Add your own in the same format:

```json
{
  "id": "CVE-YYYY-NNNNN",
  "info": {
    "name": "Plugin X < 1.2.3 — SQLi (CVSS 9.8)",
    "severity": "critical",
    "cvss_score": 9.8,
    "description": "Unauthenticated SQL injection via the search parameter.",
    "tags": ["sqli", "unauthenticated", "plugin-slug"]
  },
  "target": {
    "type": "plugin",
    "slug": "plugin-slug",
    "fixed_in": "1.2.3"
  },
  "http": [
    {
      "method": "GET",
      "path": "{{BaseURL}}/wp-admin/admin-ajax.php?action=vuln&q=1'",
      "timeout": 10,
      "matchers_condition": "and",
      "matchers": [
        { "type": "status", "status": [200] },
        { "type": "word", "words": ["DB_PASSWORD", "syntax error"], "condition": "or", "part": "body" }
      ]
    }
  ]
}
```

Seed all built-in templates to disk for reference or editing:

```bash
python wphawk.py --seed-templates
```

---

## Legal

Use only against systems you own or have explicit written permission to test. The authors take no responsibility for misuse.
