"""
Calm passenger-facing palette + language for turbulence severity.

Design rule (non-negotiable): NEVER use an alarming fire-engine red. A nervous
flier reads red as danger even when the turbulence is harmless. Everything is
muted and soft. Smooth air gets no blob at all.
"""

# internal_label -> presentation
SEVERITY = {
    "smooth": {
        "passenger": "Smooth",
        "map_color": "#BcdcF2",   # very soft sky blue (usually not drawn)
        "fill_opacity": 0.0,
        "line_color": "#BcdcF2",
        "draw": False,
        "score": 0,
    },
    "light": {
        "passenger": "A few light bumps, completely normal",
        "map_color": "#A6D6B0",   # soft green
        "fill_opacity": 0.30,
        "line_color": "#8CC79A",
        "draw": True,
        "score": 1,
    },
    "moderate": {
        "passenger": "Some noticeable bumps, normal and safe",
        "map_color": "#EBCB86",   # soft amber
        "fill_opacity": 0.34,
        "line_color": "#DDB868",
        "draw": True,
        "score": 2,
    },
    "severe": {
        "passenger": "A bumpier stretch, seatbelt sign likely on",
        "map_color": "#DDA277",   # muted orange (never bright red)
        "fill_opacity": 0.38,
        "line_color": "#CE8F60",
        "draw": True,
        "score": 3,
    },
    "extreme": {
        "passenger": "A rough patch (rare), everyone stays seated and belted",
        "map_color": "#B57F6E",   # muted red-brown
        "fill_opacity": 0.42,
        "line_color": "#A66E5D",
        "draw": True,
        "score": 4,
    },
}

# Order low -> high, used for contour band assignment.
ORDER = ["smooth", "light", "moderate", "severe", "extreme"]


def label_for_edr(edr, bands):
    """Return the internal severity label for an EDR value."""
    if edr is None or edr != edr:  # None or NaN
        return "smooth"
    for lo, hi, label in bands:
        if lo <= edr < hi:
            return label
    return "extreme"


def style_for_label(label):
    return SEVERITY.get(label, SEVERITY["smooth"])
