#!/usr/bin/env python3
"""
scraper.py — NanoDevTools Portfolio Scraper
"""

import os, re, sys
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
DEVELOPER_PLAY_ID = "5787769488900173827"
USE_NUMERIC_ID    = True

PORTFOLIO_TITLE   = "NanoDevTools"
PORTFOLIO_TAGLINE = "Lightweight Apps. Sharp Experience."
CONTACT_EMAIL     = "contact@nanodevtools.com"
PLAY_STORE_URL    = f"https://play.google.com/store/apps/dev?id={DEVELOPER_PLAY_ID}"

FALLBACK_APPS: List[dict] = [
    {
        "title":    "QR Code Scanner Barcode",
        "url":      "https://play.google.com/store/apps/details?id=com.example.qr",
        "icon":     "https://placehold.co/240x240/0f0f1a/8b5cf6?text=QR",
        "rating":   "4.5",
        "price":    "FREE",
        "category": "Utility",
    },
    {
        "title":    "Craft Skins Mine Addons Maps",
        "url":      "https://play.google.com/store/apps/details?id=com.example.craft",
        "icon":     "https://placehold.co/240x240/0f0f1a/22d3ee?text=CR",
        "rating":   "4.3",
        "price":    "FREE",
        "category": "Game",
    },
    {
        "title":    "Colorful Samsung Watch Face",
        "url":      "https://play.google.com/store/apps/details?id=com.example.watch",
        "icon":     "https://placehold.co/240x240/0f0f1a/8b5cf6?text=WF",
        "rating":   "4.6",
        "price":    "FREE",
        "category": "Watch Face",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
BASE_URL      = "https://play.google.com"
DEV_PAGE_URL  = f"{BASE_URL}/store/apps/dev?id={DEVELOPER_PLAY_ID}"
ICON_SUFFIX   = "=w240-h240-rw"
TEMPLATE_FILE = "template.html"
OUTPUT_FILE   = "index.html"
PLACEHOLDER   = "<!-- {{APPS_PLACEHOLDER}} -->"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_JUNK  = re.compile(r"^\s*(\$[\d.]+|€[\d.]+|free|install|rated|[\d,]+\+?|[\d.]+\s*stars?)\s*$", re.I)
_PRICE = re.compile(r"\s*\$[\d.]+\s*$")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clean_icon(raw: str) -> str:
    if not raw: return ""
    cleaned = re.sub(r"=[a-zA-Z]?\d+[-=].*$", "", raw.strip())
    cleaned = re.sub(r"=[a-zA-Z]\d+$", "", cleaned)
    return cleaned + ICON_SUFFIX


def detect_category(title: str, pkg: str) -> str:
    t = title.lower()
    if any(w in t for w in ["qr", "scanner", "barcode", "tool", "widget"]): return "Utility"
    if any(w in t for w in ["watch", "clock", "face", "theme", "samsung"]): return "Watch Face"
    if any(w in t for w in ["game", "mine", "craft", "skin", "addon", "map"]): return "Game"
    return "App"


def extract_title(link_tag) -> str:
    label = link_tag.get("aria-label", "").strip()
    if label and len(label) < 120:
        return _PRICE.sub("", label).strip()
    candidates = []
    for el in link_tag.find_all(["span", "div"]):
        txt = el.get_text(separator=" ", strip=True)
        if 3 < len(txt) < 120 and not _JUNK.match(txt) and "\n" not in txt:
            candidates.append(txt)
    if candidates:
        filtered = [c for c in candidates if 4 <= len(c) <= 70]
        best = sorted(filtered or candidates, key=len)[0]
        return _PRICE.sub("", best).strip()
    return ""


def extract_icon(link_tag) -> str:
    for img in link_tag.find_all("img"):
        for attr in ("src", "data-src"):
            val = img.get(attr, "")
            if "googleusercontent" in val:
                return clean_icon(val)
    return ""


def extract_rating(element) -> Optional[str]:
    node = element
    for _ in range(7):
        if node is None: break
        hit = node.find(attrs={"aria-label": re.compile(r"Rated\s+\d", re.I)})
        if hit:
            m = re.search(r"(\d+\.?\d*)", hit.get("aria-label", ""))
            if m: return m.group(1)
        node = getattr(node, "parent", None)
    return None


def fetch_missing_icon(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, params={"hl": "en"}, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "play-lh.googleusercontent" in src:
                return clean_icon(src)
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def scrape_apps() -> Optional[List[dict]]:
    print(f"[scraper] Fetching: {DEV_PAGE_URL}")
    try:
        session = requests.Session()
        session.get(BASE_URL, headers=HEADERS, timeout=10)
        resp = session.get(DEV_PAGE_URL, headers=HEADERS, params={"hl": "en", "gl": "US"}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[scraper] ✗ {e}"); return None

    print(f"[scraper]   HTTP {resp.status_code} — {len(resp.text):,} bytes")
    if "play.google.com" not in resp.url or len(resp.text) < 5000:
        print("[scraper] ✗ Blocked"); return None

    soup = BeautifulSoup(resp.text, "html.parser")
    apps: List[dict] = []
    seen: set = set()

    for link in soup.find_all("a", href=re.compile(r"/store/apps/details\?id=")):
        href = link.get("href", "")
        qs   = parse_qs(urlparse(href).query)
        pkg  = qs.get("id", [None])[0]
        if not pkg or pkg in seen: continue
        seen.add(pkg)

        title  = extract_title(link) or pkg.split(".")[-1].replace("_"," ").title()
        icon   = extract_icon(link)
        rating = extract_rating(link)

        raw    = link.get("aria-label", "")
        pm     = re.search(r"\$[\d.]+", raw)
        price  = pm.group(0) if pm else "FREE"

        apps.append({
            "title":    title,
            "url":      urljoin(BASE_URL, href),
            "icon":     icon,
            "rating":   rating,
            "price":    price,
            "category": detect_category(title, pkg),
        })

    if apps:
        print(f"[scraper] ✓ Found {len(apps)} apps")
        for app in apps:
            if not app["icon"]:
                print(f"[scraper]   Fetching icon: {app['title']}")
                app["icon"] = fetch_missing_icon(app["url"])
        return apps

    print("[scraper] ✗ No apps found"); return None


# ══════════════════════════════════════════════════════════════════════════════
#  CARD GENERATION
# ══════════════════════════════════════════════════════════════════════════════

# Category colors
CAT_COLOR = {
    "Utility":    ("text-cyan-400",   "bg-cyan-500/12",   "border-cyan-500/25"),
    "Watch Face": ("text-violet-400", "bg-violet-500/12", "border-violet-500/25"),
    "Game":       ("text-emerald-400","bg-emerald-500/12","border-emerald-500/25"),
    "App":        ("text-slate-400",  "bg-slate-500/12",  "border-slate-500/25"),
}

def _star():
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3 h-3"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77 5.82 21.02 7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'

def _arrow():
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5 flex-shrink-0"><path fill-rule="evenodd" d="M5.22 14.78a.75.75 0 010-1.06L9.44 5.5H5.75a.75.75 0 010-1.5h5.5a.75.75 0 01.75.75v5.5a.75.75 0 01-1.5 0V6.56l-5.22 5.22a.75.75 0 01-1.06 0z" clip-rule="evenodd"/></svg>'

def generate_card(app: dict, index: int) -> str:
    title    = app.get("title") or "App"
    url      = app.get("url") or "#"
    icon     = app.get("icon") or "https://placehold.co/72x72/0f0f1a/8b5cf6?text=N"
    rating   = app.get("rating")
    price    = app.get("price", "FREE")
    category = app.get("category", "App")
    safe     = title.replace('"','&quot;')
    letter   = title[0].upper() if title else "N"

    tc, bc, bdc = CAT_COLOR.get(category, CAT_COLOR["App"])

    rating_html = ""
    if rating:
        try:
            rating_html = f'<span class="flex items-center gap-1 text-amber-400">{_star()}<span class="text-xs font-semibold">{float(rating):.1f}</span></span>'
        except ValueError:
            pass

    is_free   = price.upper() == "FREE"
    price_cls = "text-cyan-400 bg-cyan-500/10 border-cyan-500/20" if is_free else "text-amber-400 bg-amber-500/10 border-amber-500/20"

    # Alternating gradient direction for visual rhythm
    grad = "from-violet-500/8 to-cyan-500/4" if index % 2 == 0 else "from-cyan-500/8 to-violet-500/4"

    return f"""
        <div class="card-item group relative flex flex-col rounded-2xl border border-white/6 overflow-hidden bg-gradient-to-br {grad} backdrop-blur-sm transition-all duration-300 ease-out hover:-translate-y-2 hover:border-violet-500/30 hover:shadow-[0_16px_56px_rgba(139,92,246,0.14)]">

          <!-- Animated top accent -->
          <div class="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-violet-500/0 via-violet-500/0 to-cyan-500/0 transition-all duration-500 group-hover:from-violet-500 group-hover:via-cyan-400 group-hover:to-violet-500/60"></div>

          <!-- Card body -->
          <div class="p-5 flex flex-col gap-4 flex-1">

            <!-- Icon row -->
            <div class="flex items-start justify-between gap-2">
              <div class="relative">
                <img
                  src="{icon}"
                  alt="{safe}"
                  width="64" height="64"
                  loading="lazy"
                  class="w-16 h-16 rounded-2xl object-cover ring-1 ring-white/8"
                  onerror="this.onerror=null;this.src='https://placehold.co/64x64/0f0f1a/8b5cf6?text={letter}'"
                >
              </div>
              <!-- Badges -->
              <div class="flex flex-col items-end gap-1.5">
                <span class="text-[10px] font-bold tracking-wider border rounded-md px-2 py-0.5 {price_cls}">{price}</span>
                <span class="text-[10px] font-semibold tracking-wider border rounded-md px-2 py-0.5 {tc} {bc} {bdc}">{category}</span>
              </div>
            </div>

            <!-- Title + rating -->
            <div class="flex-1">
              <h3 class="text-white/90 font-semibold text-sm leading-snug line-clamp-2 mb-2 group-hover:text-white transition-colors">{title}</h3>
              {rating_html}
            </div>

            <!-- CTA -->
            <a
              href="{url}"
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-center justify-center gap-2 w-full rounded-xl py-2.5 px-3 text-xs font-semibold border border-violet-500/20 text-violet-300 hover:bg-gradient-to-r hover:from-violet-500 hover:to-cyan-500 hover:text-white hover:border-transparent transition-all duration-200 active:scale-95"
            >
              View on Google Play
              {_arrow()}
            </a>

          </div>
        </div>"""


def build_cards(apps: List[dict]) -> str:
    if not apps:
        return '<p class="col-span-full text-center text-slate-600 py-20">No apps found.</p>'
    return "\n".join(generate_card(app, i) for i, app in enumerate(apps))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    apps   = scrape_apps()
    source = "live"
    if not apps:
        print("[scraper] ⚠ Using fallback")
        apps, source = FALLBACK_APPS, "fallback"

    print(f"[scraper] Building {len(apps)} apps ({source})")

    if not os.path.isfile(TEMPLATE_FILE):
        print(f"[scraper] ✗ {TEMPLATE_FILE} not found", file=sys.stderr); sys.exit(1)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        tpl = f.read()

    if PLACEHOLDER not in tpl:
        print(f"[scraper] ✗ Placeholder missing", file=sys.stderr); sys.exit(1)

    out = tpl
    out = out.replace("{{PORTFOLIO_TITLE}}",   PORTFOLIO_TITLE)
    out = out.replace("{{PORTFOLIO_TAGLINE}}", PORTFOLIO_TAGLINE)
    out = out.replace("{{DEVELOPER_PLAY_ID}}", DEVELOPER_PLAY_ID)
    out = out.replace("{{CONTACT_EMAIL}}",     CONTACT_EMAIL)
    out = out.replace("{{PLAY_STORE_URL}}",    PLAY_STORE_URL)

    ts = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    injection = (
        f"\n        <!-- AUTO-GENERATED | {ts} | {len(apps)} apps -->\n"
        + build_cards(apps)
        + "\n        <!-- /AUTO-GENERATED -->"
    )
    out = out.replace(PLACEHOLDER, injection)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"[scraper] ✓ {OUTPUT_FILE} written ({len(out):,} bytes)")


if __name__ == "__main__":
    main()
