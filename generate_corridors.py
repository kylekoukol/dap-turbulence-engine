#!/usr/bin/env python3
"""
Daily corridor turbulence pages (the SEO/AEO engine).

For each major US flight corridor we call the app's /api/turbulence-route for a
representative city pair, translate the real forecast into calm, plain-language
pilot copy + FAQ schema, and publish it to the site via /api/content. Stable
URLs (/turbulence/<slug>) that refresh daily, so they accumulate authority while
staying fresh. Deterministic from real NOAA data: accurate, cheap, no AI text.

Env:
  APP_URL        deployed app base (default https://dap-turbulence.lovable.app)
  INGEST_SECRET  shared secret (GitHub Actions Secret)
"""
import os
import json
import datetime
import requests

APP = os.environ.get("APP_URL", "https://dap-turbulence.lovable.app").rstrip("/")
SECRET = os.environ.get("INGEST_SECRET", "")
BOOKING = "https://calendly.com/dialapilotschedule/dial-a-pilot-briefing"

# name, slug, region, representative origin/dest, and a natural phrase
CORRIDORS = [
    ("Over the Rockies", "over-the-rockies", "Rocky Mountains", "DEN", "SFO",
     "the Rocky Mountains between Denver and the West Coast"),
    ("Transcontinental (Los Angeles to New York)", "transcontinental-la-to-new-york",
     "Coast to coast", "LAX", "JFK", "the transcontinental route between Los Angeles and New York"),
    ("Transcontinental (San Francisco to New York)", "transcontinental-sf-to-new-york",
     "Coast to coast", "SFO", "JFK", "the northern transcon between San Francisco and New York"),
    ("Chicago to the Northeast", "chicago-to-the-northeast", "Midwest to Northeast",
     "ORD", "LGA", "the busy corridor between Chicago and the Northeast"),
    ("Florida to the Northeast", "florida-to-the-northeast", "Southeast to Northeast",
     "MIA", "JFK", "the East Coast run between Florida and the Northeast"),
    ("Texas to the West Coast", "texas-to-the-west-coast", "South Central to West",
     "DFW", "LAX", "the route from Texas across the Southwest to California"),
    ("Pacific Northwest to California", "pacific-northwest-to-california", "West Coast",
     "SEA", "SFO", "the West Coast hop between Seattle and the Bay Area"),
    ("Atlanta to the Northeast", "atlanta-to-the-northeast", "Southeast to Northeast",
     "ATL", "LGA", "the corridor between Atlanta and the Northeast"),
    ("Denver to Chicago", "denver-to-chicago", "Great Plains", "DEN", "ORD",
     "the Great Plains route between Denver and Chicago"),
    ("Seattle to Denver", "seattle-to-denver", "Northern Rockies", "SEA", "DEN",
     "the northern Rockies route between Seattle and Denver"),
    ("Los Angeles to Denver", "los-angeles-to-denver", "Southwest to Rockies",
     "LAX", "DEN", "the Southwest-to-Rockies route between Los Angeles and Denver"),
    ("New York to Chicago", "new-york-to-chicago", "Northeast to Midwest", "JFK", "ORD",
     "the Northeast-to-Midwest corridor between New York and Chicago"),
    ("Denver to New York", "denver-to-new-york", "Rockies to Northeast", "DEN", "JFK",
     "the route from Denver across the Plains to New York"),
    ("Phoenix to Chicago", "phoenix-to-chicago", "Southwest to Midwest", "PHX", "ORD",
     "the Southwest-to-Midwest route between Phoenix and Chicago"),
    ("Boston to Chicago", "boston-to-chicago", "Northeast to Midwest", "BOS", "ORD",
     "the corridor between Boston and Chicago"),
    ("Houston to the West Coast", "houston-to-the-west-coast", "Gulf to West",
     "IAH", "LAX", "the route from Houston across the Southwest to California"),
]

SUMMARY = {
    "smooth": "Today's outlook is smooth. Expect a comfortable, quiet ride.",
    "light": "Today's outlook is mostly smooth with a few light bumps. Completely normal, and nothing to worry about.",
    "moderate": "Today's outlook is mostly smooth with a bumpier stretch or two. Noticeable, but normal and safe, and the crew plans around the worst of it.",
    "severe": "Today there is a bumpier patch along the route. It can feel uncomfortable, but it is well within what the aircraft and crew handle every day, and pilots plan around the roughest air.",
    "extreme": "Today shows a rougher patch along parts of this route. Pilots actively route around this kind of air when they can. It can look dramatic, but the aircraft is built for far more.",
}


def get_route(o, d, dep):
    r = requests.post(f"{APP}/api/turbulence-route",
                      json={"origin": o, "destination": d, "departure_time": dep, "cruise_fl": 350},
                      timeout=90)
    r.raise_for_status()
    return r.json()


def build_page(name, slug, region, o, d, phrase, j, day):
    ov = j.get("overall", {})
    label = ov.get("label", "smooth")
    summary = SUMMARY.get(label, SUMMARY["light"])
    date_str = day.strftime("%B %d, %Y").replace(" 0", " ")
    coverage = j.get("coverage", {})
    cov_html = ""
    if coverage.get("status") != "full":
        cov_html = "<p>Part of this corridor runs outside our high-resolution US coverage, so a stretch of the forecast is estimated.</p>"
    pirep = j.get("pirep_line")
    pirep_html = f"<p><em>{pirep}</em></p>" if pirep else ""

    title = f"Will your {name} flight be bumpy? Turbulence forecast for {date_str}"
    meta = (f"{summary} A calm, plain-language turbulence forecast for {phrase}, "
            f"from real airline pilots. Updated {date_str}.")
    headline = f"Will your {name.lower()} flight be bumpy today?"
    body = f"""<p class="lead">{summary}</p>
<p>This is a plain-language read on {phrase} for {date_str}. It is built from the same turbulence forecast data pilots use in the flight deck (NOAA's GTG model) and translated by real airline pilots into what you will actually feel in your seat.</p>
<p>{ov.get('headline','')}</p>
{pirep_html}
{cov_html}
<h2>What this means for you</h2>
<p>Turbulence is uncomfortable, but it is routine. Aircraft are engineered to handle far more than they will ever meet, and your crew is trained for exactly this. A few bumps on a day like today are completely normal and do not mean anything is wrong.</p>
<h2>Check your exact flight</h2>
<p>This page is a corridor overview. For your specific flight, with the bumps mapped to your climb, cruise, and descent, use our free turbulence tool.</p>
<p><a href="{APP}/">Check your flight</a>, or <a href="{BOOKING}" target="_blank" rel="noopener">talk to a real airline pilot one on one</a> before you go.</p>"""

    faq = [
        {"q": f"Is it bumpy over {name.lower()} today?", "a": summary},
        {"q": "Is turbulence dangerous?",
         "a": "No. Turbulence is uncomfortable but routine. Modern aircraft are engineered to handle far more than they ever encounter, and pilots plan their route to avoid the roughest air."},
        {"q": "How accurate is this turbulence forecast?",
         "a": "It is built from NOAA's operational turbulence model, the same data used in the flight deck, and refreshed through the day. It is a forecast, so conditions can shift, but it is a reliable read on what to expect."},
    ]
    return {
        "type": "corridor", "slug": slug, "region": region,
        "title": title, "meta_description": meta, "headline": headline,
        "body_html": body, "faq": faq, "published": True, "valid_date": day.isoformat(),
        "data": {"overall": ov, "coverage": coverage, "origin": o, "dest": d, "label": label},
    }


def publish(page):
    r = requests.post(f"{APP}/api/content",
                      headers={"x-ingest-secret": SECRET, "Content-Type": "application/json"},
                      data=json.dumps(page), timeout=60)
    return r.status_code, r.text[:120]


def main():
    if not SECRET:
        raise SystemExit("INGEST_SECRET not set")
    day = datetime.date.today()
    dep = datetime.datetime.combine(day, datetime.time(18, 0)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = 0
    for name, slug, region, o, d, phrase in CORRIDORS:
        try:
            j = get_route(o, d, dep)
            page = build_page(name, slug, region, o, d, phrase, j, day)
            sc, txt = publish(page)
            status = "ok" if sc == 200 else f"FAIL {sc} {txt}"
            print(f"{slug:34s} {page['data']['label']:9s} {status}")
            if sc == 200:
                ok += 1
        except Exception as e:
            print(f"{slug:34s} ERROR {e}")
    print(f"Published {ok}/{len(CORRIDORS)} corridor pages for {day.isoformat()}")


if __name__ == "__main__":
    main()
