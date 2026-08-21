"""Scrape Bambu Lab's store for product variants (colour, code, image, price).

The store is a Next.js app; each product page embeds a schema.org ProductGroup
JSON-LD object inside the React Server Components payload. Variant names look
like:  "PLA Basic - Jade White (10100) / Refill / 1 kg"
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NAME_RE = re.compile(r"^(?P<product>.+?)\s+-\s+(?P<colour>.+?)(?:\s+\((?P<code>[0-9A-Za-z]+)\))?\s*/\s*(?P<type>[^/]+?)\s*/\s*(?P<size>[^/]+?)\s*$")


@dataclass
class StoreVariant:
    colour_name: str
    colour_code: str | None
    spool_type: str  # spool | refill
    size: str
    sku: str
    image_url: str | None
    price: float | None
    currency: str | None
    url: str | None
    in_stock: bool | None


@dataclass
class StoreProduct:
    name: str
    handle: str
    url: str
    description: str | None
    variants: list[StoreVariant] = field(default_factory=list)


def _extract_rsc_text(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, flags=re.S)
    out = []
    for c in chunks:
        try:
            out.append(json.loads('"' + c + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def _find_balanced_json(text: str, anchor: str) -> dict | None:
    i = text.find(anchor)
    if i < 0:
        return None
    start = text.rfind("{", 0, i)
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : j + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_product_html(html: str, handle: str, url: str) -> StoreProduct | None:
    ld = _find_balanced_json(html, '"@type": "ProductGroup"')
    if ld is None:
        ld = _find_balanced_json(_extract_rsc_text(html), '"@type": "ProductGroup"')
    if not ld:
        return None
    product = StoreProduct(name=ld.get("name", handle), handle=handle, url=url, description=ld.get("description"))
    for v in ld.get("hasVariant", []):
        m = NAME_RE.match(v.get("name", ""))
        if not m:
            continue
        offers = v.get("offers") or {}
        stype = m.group("type").strip().lower()
        product.variants.append(
            StoreVariant(
                colour_name=m.group("colour").strip(),
                colour_code=m.group("code"),
                spool_type="refill" if "refill" in stype else "spool",
                size=m.group("size").strip(),
                sku=str(v.get("sku", "")),
                image_url=v.get("image"),
                price=float(offers["price"]) if offers.get("price") not in (None, "") else None,
                currency=offers.get("priceCurrency"),
                url=offers.get("url"),
                in_stock=("InStock" in offers.get("availability", "")) if offers.get("availability") else None,
            )
        )
    return product


def product_url(region: str, handle: str) -> str:
    return f"https://{region}.store.bambulab.com/products/{handle}"


class RateLimited(Exception):
    pass


async def _get(client: httpx.AsyncClient, url: str, retries: int = 4) -> httpx.Response | None:
    """GET with polite pacing; the store returns 429 if you go too fast."""
    delay = 3.0
    for attempt in range(retries):
        r = await client.get(url)
        if r.status_code == 429:
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 404:
            return None
        return r
    raise RateLimited(url)


async def fetch_product(region: str, handle: str, client: httpx.AsyncClient | None = None) -> StoreProduct | None:
    url = product_url(region, handle)
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": UA})
    try:
        r = await _get(client, url)
        if r is None or r.status_code != 200:
            return None
        return parse_product_html(r.text, handle, url)
    finally:
        if own:
            await client.aclose()


async def discover_handles(region: str, client: httpx.AsyncClient | None = None) -> list[str]:
    """Best effort: product handles linked from the filament collection page
    (only the server-rendered first page is visible without JS)."""
    url = f"https://{region}.store.bambulab.com/collections/bambu-lab-3d-printer-filament"
    own = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent": UA})
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return []
        text = _extract_rsc_text(r.text) + r.text
        handles = set(re.findall(r'"seoCode":"([a-z0-9-]+)"', text)) | set(re.findall(r"/products/([a-z0-9-]+)", text))
        skip = {"bambu-lab-3d-printer-filament"}
        return sorted(
            h for h in handles
            if h not in skip and not re.fullmatch(r"[a-z]\d[a-z]", h) and "bundle" not in h and "pack" not in h
        )
    finally:
        if own:
            await client.aclose()


# Known filament product handles on the Bambu store (seed list; editable in Settings).
DEFAULT_HANDLES = [
    "pla-basic-filament", "pla-matte", "pla-silk-upgrade", "pla-silk-multi-color",
    "pla-metal", "pla-cf", "pla-tough-upgrade", "pla-pure", "pla-translucent",
    "pla-marble", "pla-sparkle", "pla-galaxy", "pla-glow", "pla-wood", "pla-aero",
    "petg-hf", "petg-basic", "petg-translucent", "petg-cf",
    "abs-filament", "abs-gf", "asa-filament", "asa-aero", "asa-cf",
    "pc-filament", "pc-fr", "tpu-for-ams", "tpu-95a-hf",
    "paht-cf", "pa6-cf", "pa6-gf", "pps-cf", "pet-cf", "ppa-cf", "support-for-pla-petg",
]
