#!/usr/bin/env python3
"""Fetch poll-related RSS leads (no topline parsing). Writes data/polls/leads.json."""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLLS = ROOT / "data" / "polls"
BEACH = ROOT / "data" / "calaccess" / "beachheads.json"

POLL_KEYWORDS = re.compile(r"\b(poll|survey|memo|topline|ballot test)\b", re.I)
DISTRICT_RE = re.compile(r"\b(?:AD|Assembly District)[\s-]*(\d{1,2})\b", re.I)

STATEWIDE_FEEDS = [
    {
        "source": "Berkeley IGS",
        "url": "https://igs.berkeley.edu/rss.xml",
        "district_match": None,
    },
    {
        "source": "PPIC",
        "url": "https://www.ppic.org/feed/",
        "district_match": None,
    },
]


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_rss(url: str, max_items: int = 25) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "MajorityIQ-poll-leads/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall(".//item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or item.findtext("published") or ""
        pub_date = None
        if pub:
            try:
                pub_date = parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError, OSError):
                pub_date = pub[:10] if len(pub) >= 10 else None
        items.append({"title": title, "link": link, "date": pub_date, "pub_raw": pub})
    return items


def google_news_query(q: str) -> list[dict]:
    enc = urllib.parse.quote(q)
    url = f"https://news.google.com/rss/search?q={enc}&hl=en-US&gl=US&ceid=US:en"
    rows = fetch_rss(url, max_items=15)
    for r in rows:
        r["source"] = "Google News"
    return rows


def district_queries(beach: dict) -> list[tuple[str, str, list[str]]]:
    """Return (district_id, code, [queries])."""
    out = []
    for row in beach.get("districts") or []:
        did = row.get("id")
        code = row.get("code") or did
        if did not in {"ad-7", "ad-27", "ad-36", "ad-47", "ad-58", "ad-74"}:
            continue
        names = []
        def first_token(name: str | None) -> str | None:
            parts = (name or "").split()
            return parts[0] if parts else None

        if row.get("open_seat"):
            for cand in row.get("general_candidates") or []:
                tok = first_token(cand.get("name"))
                if tok:
                    names.append(tok)
        else:
            inc = row.get("incumbent") or {}
            tok = first_token(inc.get("name"))
            if tok:
                names.append(tok)
            for opp in row.get("known_opponents") or []:
                tok = first_token(opp.get("name"))
                if tok:
                    names.append(tok)
        queries = []
        dist_no = row.get("dist_no") or did.split("-")[-1]
        queries.append(f"California Assembly District {dist_no} poll")
        queries.append(f"AD-{dist_no} poll California")
        for n in names[:4]:
            queries.append(f"{n} California Assembly poll")
            queries.append(f"{n} poll memo")
        out.append((did, str(code), queries))
    return out


def match_district(text: str, beach: dict) -> str | None:
    m = DISTRICT_RE.search(text)
    if m:
        num = m.group(1).lstrip("0") or m.group(1)
        did = f"ad-{num}"
        if any(d.get("id") == did for d in beach.get("districts") or []):
            return did
    lower = text.lower()
    for row in beach.get("districts") or []:
        did = row.get("id")
        if not did:
            continue
        for opp in row.get("known_opponents") or []:
            parts = (opp.get("name") or "").split()
            last = parts[-1].lower() if parts else ""
            if last and last in lower:
                return did
        inc = row.get("incumbent") or {}
        parts = (inc.get("name") or "").split()
        last = parts[-1].lower() if parts else ""
        if last and last in lower:
            return did
        for cand in row.get("general_candidates") or []:
            parts = (cand.get("name") or "").split()
            last = parts[-1].lower() if parts else ""
            if last and last in lower:
                return did
    return None


def lead_key(lead: dict) -> str:
    return (lead.get("link") or lead.get("title") or "").strip().lower()


def merge_leads(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    by_key = {lead_key(x): x for x in existing if lead_key(x)}
    for row in new_rows:
        k = lead_key(row)
        if not k:
            continue
        if k in by_key:
            prev = by_key[k]
            prev["last_seen"] = row.get("fetched_at") or prev.get("last_seen")
            continue
        by_key[k] = row
    merged = list(by_key.values())
    merged.sort(key=lambda x: x.get("date") or "", reverse=True)
    return merged


def main() -> int:
    beach = load_json(BEACH)
    now = datetime.now(timezone.utc).isoformat()
    candidates: list[dict] = []

    for feed in STATEWIDE_FEEDS:
        try:
            items = fetch_rss(feed["url"])
        except Exception as exc:
            print(f"Feed skip {feed['source']}: {exc}", file=sys.stderr)
            continue
        for item in items:
            blob = f"{item.get('title', '')} {item.get('link', '')}"
            if not POLL_KEYWORDS.search(blob):
                continue
            did = match_district(blob, beach) if feed.get("district_match") is not False else None
            candidates.append(
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "date": item.get("date"),
                    "source": feed["source"],
                    "matched_district": did,
                    "query": feed["url"],
                    "fetched_at": now,
                }
            )

    for did, code, queries in district_queries(beach):
        seen_q = set()
        for q in queries:
            if q in seen_q:
                continue
            seen_q.add(q)
            try:
                items = google_news_query(q)
            except Exception as exc:
                print(f"News skip {q}: {exc}", file=sys.stderr)
                continue
            for item in items:
                blob = item.get("title") or ""
                if not POLL_KEYWORDS.search(blob):
                    continue
                matched = match_district(blob, beach) or did
                candidates.append(
                    {
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "date": item.get("date"),
                        "source": item.get("source") or "Google News",
                        "matched_district": matched,
                        "query": q,
                        "fetched_at": now,
                    }
                )

    leads_path = POLLS / "leads.json"
    existing_payload = load_json(leads_path) if leads_path.exists() else {"leads": []}
    merged = merge_leads(existing_payload.get("leads") or [], candidates)

    payload = {
        "schema_version": 1,
        "updated_at": now,
        "notes": existing_payload.get("notes") or "Automated leads only — verify before released.json.",
        "leads": merged,
    }
    POLLS.mkdir(parents=True, exist_ok=True)
    leads_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {leads_path} ({len(merged)} leads, {len(candidates)} new candidates this run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
