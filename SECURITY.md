# Security policy

## Reporting a vulnerability

Open a private security advisory:
**Settings → Security → Advisories → Report a vulnerability**

Please **do not** open a public issue for security-impacting reports. Include:

- A clear description of the issue and its impact
- Reproduction steps (or a minimal PoC)
- The commit SHA or live URL where you observed the behaviour

You can expect an acknowledgement within 5 business days. Critical issues
(remote code execution, secret exposure, account takeover) are prioritized.

## Threat model

TechPulse is a **static, read-only public site** with **no authenticated
users, no comments, no form submissions, and no server-side code at runtime**.
Compromise scenarios reduce to:

| Threat | Mitigation |
| --- | --- |
| **XSS through `data/feed.json`** (attacker writes script into a Reddit/HN title and we render it) | All title/body content is HTML-escaped before injection (`escapeHtml`). All attribute values use `escapeAttr`. Category accents are validated against a hex-color regex (`safeColor`). Category IDs used in `id=`/`href="#..."` are slugified (`safeSlug`). Content-Security-Policy header further blocks any successful injection from loading remote scripts. |
| **CSS injection** (attacker writes `expression(...)` / `url(javascript:...)` into a value used inside `style="..."`) | Only hex-color values pass `safeColor`; everything else falls back to a safe default. The CSP `style-src` directive forbids loading external stylesheets. |
| **Clickjacking** | `X-Frame-Options: DENY` and `frame-ancestors 'none'` in CSP. |
| **MIME confusion / sniffing** | `X-Content-Type-Options: nosniff`. |
| **HTTPS downgrade** | `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`. |
| **Browser-feature abuse via XSS** | `Permissions-Policy` disables camera, microphone, geolocation, payment, USB, sensors, FLoC. |
| **Memory-exhaustion DoS on the GitHub Actions runner** (malicious feed returns a multi-GB body) | `utils.safe_get` enforces a 5 MB cap via streaming + `Content-Length` check; oversized responses are aborted before deserialization. |
| **SSRF / arbitrary URL fetch** | All fetch URLs come from `scripts/config.py`; nothing user-controlled reaches `safe_get`. |
| **XXE in RSS parsing** | `feedparser` disables external entity resolution by default. |
| **Secret exfiltration via PR** | The workflow has no `pull_request` trigger; only `schedule` and `workflow_dispatch` run with secrets. |
| **Supply-chain compromise of pipeline deps** | All deps in `scripts/requirements.txt` are pinned to exact versions. Dependabot proposes upgrades weekly so a known-CVE dep isn't accidentally shipped for months. |
| **Compromised third-party action** | Actions are pinned to major versions from first-party publishers (`actions/checkout@v5`, `actions/setup-python@v6`). For higher assurance, pin to commit SHAs (see "Hardening further" below). |

## Out of scope

- **Compromise of GitHub itself** (your repo's actor, GitHub.com, or Actions runners) — outside our control.
- **Compromise of upstream sources** (Reddit, HN, RSS feeds, Lobsters, Google Gemini). Sandboxed by the mitigations above.
- **Account takeover of the repo owner.** Use 2FA, audit collaborators, and rotate the `GEMINI_API_KEY` if you suspect leakage.

## Hardening further (optional, not yet applied)

These add friction (mostly to maintenance) for a smaller delta in real security. Recommended only if the dashboard handles sensitive content or hosts a brand worth defending against targeted attack:

1. **Pin third-party actions to commit SHAs** rather than version tags.
   Replace `uses: actions/checkout@v5` with
   `uses: actions/checkout@<full-40-char-sha>  # v5.0.0`.
   GitHub's `dependabot` config already understands SHA pins and will keep
   them current.
2. **Self-host the Google Fonts CSS and font files** to drop
   `fonts.googleapis.com` from `style-src` and `fonts.gstatic.com` from
   `font-src`. CSP becomes strict-`'self'` only.
3. **Remove `'unsafe-inline'` from `style-src`** by refactoring
   `app.js` to set per-category accents via
   `el.style.setProperty('--cat-color', ...)` instead of interpolated
   `style="..."` attributes. Requires moving from `innerHTML` to DOM
   creation for the affected elements.
4. **Run `pip-audit` / `safety` in CI** to fail the build on a known CVE
   in the locked dependency set, even before Dependabot opens a PR.
5. **Sign commits** with a Sigstore / GPG key, and require signed commits
   on the `main` branch. Stops an attacker who steals a write token from
   silently committing.

## Reproducible audit

To re-validate the pipeline locally:

```bash
python -m compileall -q scripts/
python -m pip install pip-audit && pip-audit -r scripts/requirements.txt
```

The first command catches syntax errors; the second flags any dependency
with a known CVE at the pinned version.
