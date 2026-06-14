# WPHawk CVE Templates

Nuclei-style JSON/YAML templates — každá šablóna = jeden CVE test.
Wphawk ich načíta, porovná s nájdenými pluginmi/témami a spustí HTTP request.

## Spustenie

```bash
python wphawk.py -u https://target.com --aggressive --local-cve
```

## Formát šablóny

```json
{
  "id": "CVE-YYYY-NNNNN",
  "info": {
    "name": "Plugin X < 1.2.3 — Typ zraniteľnosti (CVSS X.X)",
    "severity": "critical",
    "cvss_score": 9.8,
    "description": "Popis.",
    "tags": ["sqli", "unauthenticated", "plugin-slug"]
  },
  "target": {
    "type": "plugin",
    "slug": "plugin-slug",
    "fixed_in": "1.2.3"
  },
  "http": [
    {
      "method": "POST",
      "path": "{{BaseURL}}/wp-admin/admin-ajax.php",
      "headers": { "Content-Type": "application/x-www-form-urlencoded" },
      "body": "action=vuln_action&param=payload",
      "timeout": 12,
      "matchers_condition": "and",
      "matchers": [
        { "type": "dsl",    "dsl": "duration >= 4.5" },
        { "type": "status", "status": [200] },
        { "type": "word",   "words": ["secret", "DB_PASSWORD"], "condition": "or", "part": "body" },
        { "type": "regex",  "regex": ["root:[x*]:0:0:"],        "part": "body" }
      ]
    }
  ]
}
```

## Path tokeny

| Token          | Hodnota                                       |
|----------------|-----------------------------------------------|
| `{{BaseURL}}`  | https://target.com/                           |
| `{{PluginURL}}`| https://target.com/wp-content/plugins/SLUG/  |
| `{{ThemeURL}}` | https://target.com/wp-content/themes/SLUG/   |

## Matcher typy

| Typ       | Parametre                                         |
|-----------|--------------------------------------------------|
| `status`  | `"status": [200, 302]`                           |
| `word`    | `"words": ["text"]`, `"condition": "or\|and"`, `"part": "body\|header"` |
| `regex`   | `"regex": ["pattern"]`, `"part": "body\|header"` |
| `dsl`     | `"dsl": "duration >= 4.5"` / `"contains(body, \"x\")"` |

Pridaj `"negative": true` na ktorýkoľvek matcher pre inverziu.

## Typ targetu

- `"type": "plugin"` — testuje sa len keď je daný plugin nájdený
- `"type": "theme"`  — testuje sa len keď je daná téma nájdená  
- `"type": "core"`   — testuje sa vždy keď sa detekuje WP verzia

Šablóna sa preskočí ak `detected_version >= fixed_in` (už patchovaná).
