# Wphawk
Spustenie:
# Všetko naraz — plný pentest
python wphawk.py -u https://target.com --aggressive --deep-recon --cve --exploit --brute --auth-scan

# Len recon + outdated + CVE
python wphawk.py -u https://target.com --cve --deep-recon
