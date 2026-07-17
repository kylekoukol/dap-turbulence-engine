#!/usr/bin/env python3
"""
Evergreen pillar pages (the AEO moat).

Unlike the corridor pages (which refresh daily off live forecast data), these are
evergreen explainers that answer the questions a nervous flier types into Google
or asks ChatGPT. They are written once from PRIMARY sources (FAA, NTSB, NASA,
NOAA, the Code of Federal Regulations) with every number tied to a real citation,
and refreshed only when a source changes. A good pillar gets cited by answer
engines for years, which is what actually pulls traffic away from a bare map like
turbli and differentiates us: we explain, in a real pilot voice, what the numbers
mean for the person in seat 14C.

They publish to the same content system as corridors: POST /api/content with
type "pillar", which renders at /learn/<slug> with Article + FAQ schema and lands
in sitemap.xml automatically.

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
TOOL = f"{APP}/"
REVIEWED = "July 17, 2026"

# --- shared source URLs (primary only) --------------------------------------
S = {
    "cfr_301": "https://www.law.cornell.edu/cfr/text/14/25.301",
    "cfr_303": "https://www.law.cornell.edu/cfr/text/14/25.303",
    "cfr_305": "https://www.law.cornell.edu/cfr/text/14/25.305",
    "cfr_337": "https://www.law.cornell.edu/cfr/text/14/25.337",
    "cfr_341": "https://www.law.cornell.edu/cfr/text/14/25.341",
    "ntsb": "https://www.ntsb.gov/safety/safety-studies/Documents/SS2101.pdf",
    "faa_turb": "https://www.faa.gov/travelers/fly_safe/turbulence",
    "faa_ac88": "https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_120-88A_CHG_1.pdf",
    "faa_uprt": "https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_120-111.pdf",
    "nws_turb": "https://www.weather.gov/source/zhu/ZHU_Training_Page/turbulence_stuff/turbulence/turbulence.htm",
    "faa_cat": "https://www.faa.gov/documentlibrary/media/advisory_circular/ac_00-30c.pdf",
    "aim_wake": "https://www.faa.gov/Air_traffic/Publications/atpubs/aim_html/chap7_section_4.html",
    "aim_sigmet": "https://www.faa.gov/air_traffic/publications/atpubs/aim_html/chap7_section_1.html",
    "awc_edr": "https://aviationweather.gov/turbulence/help?page=plot",
    "faa_gtg": "https://www.faa.gov/nextgen/programs/weather/awrp/turbulence",
    "faa_criteria": "https://www.faa.gov/air_traffic/publications/atpubs/FSS/fss0902.html",
}


def cite(key, text):
    return f'<a href="{S[key]}" target="_blank" rel="noopener">{text}</a>'


def sources_block(items):
    lis = "\n".join(f'<li>{cite(k, label)}</li>' for k, label in items)
    return (
        '<h2>Sources</h2>\n<ul>\n' + lis + '\n</ul>\n'
        f'<p><em>Last reviewed {REVIEWED}. These pages are built from primary '
        f'sources and reviewed as those sources change.</em></p>'
    )


def cta_block():
    return (
        '<h2>If you would like to talk it through</h2>\n'
        '<p>If reading the numbers helps but you would still like to hear it from '
        'a person, you can book a one on one call with a real airline pilot at '
        f'<a href="{BOOKING}" target="_blank" rel="noopener">Dial A Pilot</a>. And '
        f'before your next flight, you can <a href="{TOOL}">check the turbulence '
        'forecast for your exact route</a> in plain language.</p>'
    )


# ---------------------------------------------------------------------------
# Pillar 1: Is Turbulence Dangerous?
# ---------------------------------------------------------------------------
P1_BODY = f"""<p class="lead">No. Turbulence is uncomfortable, but for anyone wearing a seat belt it is a safety non-event on a modern US airliner. The most recent turbulence death on a US airline recorded by the National Transportation Safety Board happened in December 1997, and across the ten years from 2009 through 2018 the NTSB found that of the 123 people seriously hurt by turbulence, {cite("ntsb", "only one was documented wearing a seat belt")}.</p>

<p>The reason is that turbulence hurts people, not airplanes. In that same ten year review, {cite("ntsb", "no turbulence event caused substantial structural damage to the aircraft")}. The bumps you feel are the air moving unevenly around a wing that never stops making lift. What actually causes injuries is a person being out of their seat, or unbelted, when a sharp bump arrives.</p>

<p>That is also why the people most often hurt are the ones who have to be up and working. The NTSB found that {cite("ntsb", "flight attendants accounted for 78.9 percent of the seriously injured (97 of 123), and no flight crew in the cockpit were seriously injured at all")}. The passengers who get hurt are almost always the ones who had their belt off in smooth looking air.</p>

<h2>Why the airplane itself is not at risk</h2>
<p>An airliner is not built to just barely survive a rough day. It is built and tested to loads far past anything weather puts into it, and the margins are written into federal law. The airframe is designed to two tiers of load: the limit load, meaning {cite("cfr_301", "the maximum loads to be expected in service")}, and the ultimate load above that. By regulation, {cite("cfr_303", "a safety factor of 1.5 must be applied to the limit load")}, and the structure {cite("cfr_305", "must support that ultimate load without failure and support the everyday limit load without any permanent deformation")}.</p>

<p>Put plainly: the strength the wing is signed off to is one and a half times beyond the worst force it is ever expected to meet, and it has to hold that without bending permanently, let alone breaking. A transport airplane's {cite("cfr_337", "positive maneuvering limit is at least 2.5 g")}, a load a passenger cabin essentially never sees in cruise turbulence.</p>

<h3>The numbers, from the source</h3>
<ul>
<li>Only 1 of 123 seriously injured people over 2009 to 2018 was wearing a seat belt. {cite("ntsb", "NTSB SS2101")}</li>
<li>0 turbulence events in that decade caused substantial aircraft structural damage. {cite("ntsb", "NTSB SS2101")}</li>
<li>Flight attendants were 78.9 percent of the serious injuries; cockpit crew, 0. {cite("ntsb", "NTSB SS2101")}</li>
<li>Certified safety factor on structure: 1.5 times the maximum expected load. {cite("cfr_303", "14 CFR 25.303")}</li>
<li>Positive maneuvering limit: at least 2.5 g. {cite("cfr_337", "14 CFR 25.337")}</li>
<li>From 1980 to 2003, only four people seated with seat belts fastened were seriously injured by turbulence. {cite("faa_ac88", "FAA AC 120-88A")}</li>
</ul>

<h2>Three ways to picture it</h2>
<p>A fastened seat belt is not there to hold the airplane together. It is there to keep you moving with the airplane instead of a half second behind it. When the cabin drops and comes back up, a belted passenger goes down and up with it. An unbelted one catches up with the ceiling on the way.</p>

<p>The 1.5 safety factor is the difference between a bridge posted for a fully loaded truck and a bridge that only ever carries bicycles. The truck rating is the ultimate load. The bicycles are your turbulent Tuesday.</p>

<p>Turbulence moves the air the airplane is flying through; it does not slide the airplane the way a car loses traction on ice. The wings keep making lift the entire time. A bump is the cushion of air changing thickness, not the cushion disappearing.</p>

<h2>If you are a nervous flier</h2>
<p>Here is the gap that makes turbulence so frightening. Your body reads a drop in your stomach as danger, because for most of human history a sudden fall was danger. The airplane reads that same moment as a routine load change, well inside limits it was tested far beyond. Both things are true at once. Your fear is a normal alarm firing on very old wiring, not evidence that anything is wrong. The numbers on this page are what the airplane knows. It is fair to let them outvote the feeling, one bump at a time.</p>

{cta_block()}
"""

P1_FAQ = [
    {"q": "What does severe turbulence actually feel like?",
     "a": "By the FAA's own reporting criteria, severe turbulence is when occupants are thrown against their seat belts and unsecured objects are tossed about, with brief moments where the aircraft is hard to control. It is rare, it is brief, and it is exactly why the belt matters. Moderate turbulence, the far more common kind, is when you feel definite strain against the belt but the airplane is fully under control."},
    {"q": "Has turbulence ever broken a US airliner apart?",
     "a": "Not in the modern record the NTSB reviewed. Across 2009 through 2018, no turbulence event on a US airline caused substantial structural damage to the aircraft. Turbulence's documented toll is injuries to people who were not secured, not airplanes coming apart."},
    {"q": "Why do flight attendants get hurt the most?",
     "a": "Because they are the ones up and moving. The NTSB found flight attendants made up 78.9 percent of the seriously injured, while no cockpit crew were seriously injured at all. When you are belted in your seat, you are in the safest position on the airplane."},
    {"q": "Why does the seat belt sign come on when the air feels smooth?",
     "a": "Because some turbulence cannot be seen, and forecasts and pilot reports let a crew know rough air is likely before you would feel it. The single most effective thing a passenger can do is keep the belt fastened whenever seated, even when the ride is smooth."},
    {"q": "Can pilots avoid turbulence?",
     "a": "Often, yes. Pilots and airline dispatchers use rapidly updated turbulence forecasts and pilot reports to pick smoother altitudes and routes, and to plan around the roughest air. They cannot make every bump disappear, but the worst of it is usually planned around before you ever board."},
]

# ---------------------------------------------------------------------------
# Pillar 2: Can Turbulence Flip or Crash a Plane?
# ---------------------------------------------------------------------------
P2_BODY = f"""<p class="lead">In practical terms, no. A modern airliner is not flipped over or torn apart by the turbulence it meets in normal flight. It is built and tested to loads well beyond what turbulence produces, it is specifically designed for gusts, and the pilots flying it are trained to keep it right side up. The National Transportation Safety Board found that although turbulence causes {cite("ntsb", "the most common type of accident on US airlines")}, across 2009 through 2018 not one of those events caused substantial structural damage to the aircraft.</p>

<p>The word accident here means injuries, almost always to someone who was unbelted. It does not mean the airplane was damaged. That distinction is the whole answer to this question.</p>

<h2>How strong the airplane actually is</h2>
<p>Federal certification rules define aircraft strength in two tiers: {cite("cfr_301", "limit loads, the maximum expected in service, and ultimate loads, which are limit loads multiplied by a safety factor")}. That safety factor is set by regulation at {cite("cfr_303", "1.5")}, and the structure {cite("cfr_305", "must support the ultimate load without failure for at least three seconds and support limit loads without any permanent deformation")}.</p>

<p>On top of that, the airplane is designed for turbulence directly, not just as an afterthought. The gust rules require it to be analyzed for {cite("cfr_341", "specified vertical and lateral gusts, using a reference gust velocity of 56 feet per second at sea level")}. And the maneuvering limits it must tolerate, {cite("cfr_337", "at least positive 2.5 g and negative 1.0 g")}, are far beyond the fraction of a g that ordinary cruise turbulence adds or subtracts.</p>

<h3>The numbers, from the source</h3>
<ul>
<li>Ultimate load is limit load times a safety factor of 1.5. {cite("cfr_303", "14 CFR 25.303")}</li>
<li>The structure must hold ultimate load without failure for at least 3 seconds. {cite("cfr_305", "14 CFR 25.305")}</li>
<li>Maneuvering limits: at least +2.5 g and -1.0 g. {cite("cfr_337", "14 CFR 25.337")}</li>
<li>Certification reference gust: 56.0 feet per second at sea level. {cite("cfr_341", "14 CFR 25.341")}</li>
<li>Turbulence events causing substantial aircraft damage, 2009 to 2018: none. {cite("ntsb", "NTSB SS2101")}</li>
</ul>

<h2>Three ways to picture it</h2>
<p>A gust is a fast push on the wing, and the rules require the airframe to be designed for a defined gust and then strengthened past it. The airplane meets rough air the way a ship meets a swell: it rides up and settles back down. It does not snap.</p>

<p>Rolling an airliner over would take a sustained, one sided force. Turbulence is the opposite of that. It is short, random pushes from every direction that mostly cancel each other out. It is being jostled in a crowd, not being tackled.</p>

<p>The autopilot in turbulence is not fighting for its life. It is making small, constant corrections, the same way you make tiny steering adjustments on a gravel road without even thinking about it. If pilots do hand fly through a rough patch, they are trained for it directly through {cite("faa_uprt", "upset prevention and recovery training")}.</p>

<h2>What turbulence really does at its worst</h2>
<p>The honest risk from severe turbulence is not the airplane, it is an unsecured person or object inside it. That is why crews stow the carts and turn on the seat belt sign before a forecast rough patch. Manage the cabin, and even severe turbulence becomes a bad few minutes rather than an injury.</p>

<h2>If you are a nervous flier</h2>
<p>The fear behind this question is usually a picture: the wing folding, or the airplane rolling over. It helps to know that picture has no basis in how the machine is built or flown. The airframe is certified past its worst expected day, the gusts it will ever meet are designed for on paper before the airplane is even built, and two trained pilots are watching over all of it. What you feel as the edge of control is, from the flight deck, an ordinary day at work.</p>

{cta_block()}
"""

P2_FAQ = [
    {"q": "How strong is an airliner wing?",
     "a": "It is certified to an ultimate load of one and a half times the maximum load ever expected in service, and it must hold that without breaking. It must also carry its everyday limit load with no permanent bending at all. The strength you are riding on is built with margin to spare."},
    {"q": "What is a g or load factor?",
     "a": "A g is a multiple of normal gravity, a way of measuring the force pressing on the airplane and on you. Transport airplanes are certified to at least positive 2.5 g and negative 1.0 g. Ordinary cruise turbulence changes the load by a small fraction of a g, nowhere near those limits."},
    {"q": "Can turbulence roll a plane upside down?",
     "a": "It is extraordinarily unlikely, because rolling an airplane takes a sustained one sided force and turbulence is short and random. And if an airplane is ever upset from normal flight, airline pilots are trained specifically to prevent and recover from that through upset prevention and recovery training."},
    {"q": "Does the autopilot switch off in turbulence?",
     "a": "Usually it stays on and simply makes continuous small corrections. In some conditions pilots choose to hand fly for better feel, which is a routine decision, not an emergency. Either way the airplane is being actively flown the whole time."},
    {"q": "What is the worst that severe turbulence has done recently?",
     "a": "In the modern US record, the worst outcomes have been injuries to people who were not wearing their seat belts, not damage to the aircraft. The NTSB found no substantial structural damage from turbulence across a full decade of US airline flying."},
]

# ---------------------------------------------------------------------------
# Pillar 3: What Causes Turbulence?
# ---------------------------------------------------------------------------
P3_BODY = f"""<p class="lead">Turbulence is simply the airplane flying through air that is moving unevenly, and only a handful of things stir the air up. Heat rising off the ground, wind tumbling over mountains, the fast high altitude rivers of air called jet streams, and the wake of other aircraft. None of them mean anything is wrong with the airplane, and all of them are things pilots forecast and plan around every day.</p>

<h2>The four things that cause bumps</h2>
<p>The first is convective, or thermal, turbulence. On warm days {cite("nws_turb", "the sun heats the ground unevenly and sends up rising columns of air, which on a hot afternoon can build into thunderstorms")}. This is the bumpiness of a summer climb out.</p>

<p>The second is mechanical turbulence, from {cite("nws_turb", "friction between the air and the ground, especially irregular terrain")}. Its strongest form is the mountain wave, the turbulent eddies found downwind of a ridge, which {cite("nws_turb", "produce some of the most severe mechanical turbulence")}. It is why a flight can get bumpy crossing the Rockies on an otherwise clear day.</p>

<p>The third is clear air turbulence, or CAT, which is {cite("nws_turb", "turbulence not associated with clouds, occurring at or above 15,000 feet, and not restricted to cloud free air")}. It tends to be found {cite("faa_cat", "near the jet streams")}, and it is the tricky one because it {cite("faa_cat", "is often encountered unexpectedly and without visual clues to warn pilots")}. That is why the seat belt sign sometimes comes on when the sky outside looks perfectly clear.</p>

<p>The fourth is wake turbulence, which every airplane makes just by flying. Lift creates {cite("aim_wake", "two counter rotating vortices trailing behind the wingtips")}. Air traffic control spaces airplanes to keep clear of it, so it is mostly something you might feel briefly on approach behind a larger jet.</p>

<h2>Why clouds mean bumps</h2>
<p>A puffy fair weather cloud is the visible top of a column of rising warm air, a bit like steam over a pot. When {cite("nws_turb", "cumulus or larger clouds are present, that turbulent layer of rising air extends from the surface all the way up to the cloud tops")}. Flying through it, the bump you feel and the cloud you see are the same event.</p>

<h2>How turbulence is measured and forecast</h2>
<p>Pilots do not rate turbulence by how scary it feels. They rate it by what the airplane does. The FAA's reporting criteria run from {cite("faa_criteria", "light, where loose objects stay at rest, to moderate, severe, and extreme")}. Modern forecasts turn that into a single number called the eddy dissipation rate, or EDR, which {cite("awc_edr", "runs from close to 0 for smooth air to near 1 for the most extreme")}.</p>

<p>That number is not guesswork. The {cite("faa_gtg", "Graphical Turbulence Guidance forecast is generated automatically from aircraft observations and weather model data and expressed as EDR")}. It is the same family of data the forecast behind this tool is built on, which is why our route checker can tell you in plain language what a given flight is likely to feel. Pilots also get advisories such as {cite("aim_sigmet", "SIGMETs and AIRMETs")} describing hazardous weather en route, plus reports from other aircraft ahead of them.</p>

<h2>Two ways to picture it</h2>
<p>Clear air turbulence is wind shear you cannot see, where two layers of air slide past each other at different speeds, like the choppy seam where a fast river current meets slower water. Most of it happens in clear sky, which is exactly why a smooth looking day can still have a bumpy stretch at altitude.</p>

<p>A bump in a cloud is not the airplane hitting something solid. Clouds have no substance to hit. You are feeling the same rising air that made the cloud visible in the first place, the way you would feel a warm updraft if you walked from shade into sun.</p>

<h2>If you are a nervous flier</h2>
<p>Not knowing why the airplane is shaking is its own kind of fear. Once you can name it, warm air rising, wind spilling over a ridge, the seam of a jet stream, the bump stops being a mystery and becomes weather, the same as rain on a windshield. It is uncomfortable, it is temporary, and it is one of the most studied and carefully forecast parts of the entire flight.</p>

{cta_block()}
"""

P3_FAQ = [
    {"q": "What is clear air turbulence?",
     "a": "It is turbulence that happens without clouds to signal it, generally at or above 15,000 feet and often near the jet stream. Because it comes without visual clues, it is the main reason pilots ask you to keep your belt fastened even when the sky looks clear. It is still routine, and forecasts increasingly show where it is likely."},
    {"q": "Why is it bumpy when we fly through clouds?",
     "a": "Because many clouds are the visible top of rising air. When cumulus clouds are present, the turbulent layer of rising air reaches from the surface up to the cloud tops, so the bump you feel and the cloud you see are the same rising motion. You are not hitting anything solid."},
    {"q": "What does the jet stream have to do with turbulence?",
     "a": "The jet stream is a fast river of high altitude wind, and clear air turbulence is often found near it where fast and slow air meet. Pilots know where the jet stream is and can often change altitude to find smoother air above or below the roughest layer."},
    {"q": "How do pilots know where turbulence is?",
     "a": "They use automated forecasts like the Graphical Turbulence Guidance, official advisories called SIGMETs and AIRMETs, and real time reports from aircraft flying ahead of them. Together these let a crew plan around the worst air before you ever feel it."},
    {"q": "What do light, moderate, and severe turbulence mean?",
     "a": "They are defined by what happens inside the airplane, not by fear. In light turbulence loose objects stay at rest. In moderate you feel definite strain against your belt but the airplane is fully controlled. Severe, which is rare and brief, throws unsecured occupants against their belts. The airplane handles all of it."},
]

PILLARS = [
    {
        "slug": "is-turbulence-dangerous",
        "title": "Is Turbulence Dangerous? What the Data Actually Shows",
        "headline": "Is Turbulence Dangerous?",
        "region": "Turbulence, explained",
        "meta": ("No. On a US airline, the last turbulence death recorded by the NTSB was in 1997, "
                 "and of 123 people seriously hurt over a decade, only one wore a seat belt. Here is why."),
        "body": P1_BODY,
        "faq": P1_FAQ,
        "sources": [("ntsb", "NTSB Safety Study SS2101, Preventing Turbulence-Related Injuries"),
                    ("cfr_301", "14 CFR 25.301, Loads"),
                    ("cfr_303", "14 CFR 25.303, Factor of safety"),
                    ("cfr_305", "14 CFR 25.305, Strength and deformation"),
                    ("cfr_337", "14 CFR 25.337, Limit maneuvering load factors"),
                    ("faa_turb", "FAA, Turbulence: Staying Safe"),
                    ("faa_ac88", "FAA Advisory Circular 120-88A, Preventing Injuries Caused by Turbulence")],
    },
    {
        "slug": "can-turbulence-flip-or-crash-a-plane",
        "title": "Can Turbulence Flip or Crash a Plane?",
        "headline": "Can Turbulence Flip or Crash a Plane?",
        "region": "Turbulence, explained",
        "meta": ("In practical terms, no. Airliners are certified to 1.5 times their maximum expected load, "
                 "and the NTSB found no turbulence-related structural damage in a decade of US flying."),
        "body": P2_BODY,
        "faq": P2_FAQ,
        "sources": [("cfr_301", "14 CFR 25.301, Loads"),
                    ("cfr_303", "14 CFR 25.303, Factor of safety"),
                    ("cfr_305", "14 CFR 25.305, Strength and deformation"),
                    ("cfr_337", "14 CFR 25.337, Limit maneuvering load factors"),
                    ("cfr_341", "14 CFR 25.341, Gust and turbulence loads"),
                    ("ntsb", "NTSB Safety Study SS2101, Preventing Turbulence-Related Injuries"),
                    ("faa_uprt", "FAA Advisory Circular 120-111, Upset Prevention and Recovery Training")],
    },
    {
        "slug": "what-causes-turbulence",
        "title": "Why Does a Plane Shake? What Actually Causes Turbulence",
        "headline": "Why Does a Plane Shake? What Actually Causes Turbulence",
        "region": "Turbulence, explained",
        "meta": ("Turbulence is the plane flying through uneven air: heat off the ground, wind over mountains, "
                 "jet streams, and aircraft wakes. Here is what each one is, and how pilots forecast it."),
        "body": P3_BODY,
        "faq": P3_FAQ,
        "sources": [("nws_turb", "NOAA National Weather Service, Turbulence training reference"),
                    ("faa_cat", "FAA Advisory Circular 00-30C, Clear Air Turbulence Avoidance"),
                    ("aim_wake", "FAA Aeronautical Information Manual 7-4, Wake Turbulence"),
                    ("aim_sigmet", "FAA Aeronautical Information Manual 7-1, Meteorology"),
                    ("awc_edr", "NOAA Aviation Weather Center, EDR turbulence guidance"),
                    ("faa_gtg", "FAA NextGen, Graphical Turbulence Guidance"),
                    ("faa_criteria", "FAA, Turbulence Reporting Criteria Table")],
    },
]


def build_page(p):
    body = p["body"] + "\n" + sources_block(p["sources"])
    return {
        "type": "pillar",
        "slug": p["slug"],
        "region": p["region"],
        "title": p["title"],
        "meta_description": p["meta"],
        "headline": p["headline"],
        "body_html": body,
        "faq": p["faq"],
        "published": True,
    }


def publish(page):
    r = requests.post(f"{APP}/api/content",
                      headers={"x-ingest-secret": SECRET, "Content-Type": "application/json"},
                      data=json.dumps(page), timeout=60)
    return r.status_code, r.text[:160]


def main():
    if not SECRET:
        raise SystemExit("INGEST_SECRET not set")
    ok = 0
    for p in PILLARS:
        page = build_page(p)
        sc, txt = publish(page)
        status = "ok" if sc == 200 else f"FAIL {sc} {txt}"
        print(f"{p['slug']:42s} {status}")
        if sc == 200:
            ok += 1
    print(f"Published {ok}/{len(PILLARS)} pillar pages")


if __name__ == "__main__":
    main()
