#!/usr/bin/env python3
"""Prüft die DWD-Vorhersage (ICON via Open-Meteo) für das Tempelhofer Feld und
schickt bei gutem Drachenwetter eine Nachricht an ntfy.

Modi (erstes Argument):
  weekend  – Vorschau für Samstag und Sonntag (Freitagabend)
  today    – nur heute (Samstag-/Sonntagmorgen)
  test     – schickt immer eine Testnachricht mit der aktuellen Lage
  demo     – Wochenendvorschau mit erfundenen Werten (zum Ansehen)
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TOPIC = os.environ["NTFY_TOPIC"]
PAGE = "https://grobie.github.io/drachenwetter/"   # öffnet sich beim Tippen auf die Nachricht
# Vorschaubilder wie in der App: Drachen im Wind bzw. am Boden
ICON = PAGE + "icon-192.png"
BERLIN = ZoneInfo("Europe/Berlin")

# Schwellen in km/h (10-Minuten-Mittelwind) – wie in der App
MIN_FLY, MIN_TRY, MAX_MEAN, MAX_GUST, MAX_RAIN = 12, 8, 38, 55, 50
DAY_FROM, DAY_TO = 9, 17   # tagsüber
MIN_HOURS = 2              # mindestens so viele Stunden am Stück

FORECAST = (
    "https://api.open-meteo.com/v1/forecast?latitude=52.473&longitude=13.403"
    "&hourly=wind_speed_10m,wind_gusts_10m,precipitation_probability"
    "&models=icon_seamless&wind_speed_unit=kmh&timezone=Europe%2FBerlin&forecast_days=4"
)
WEEKDAY = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def line(win):
    start, end, wind = win
    return f"{start}–{end} Uhr · bis {wind} km/h"


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Drachenwetter/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def level(w, g, pp):
    """'fly', 'maybe' oder None für eine Stunde."""
    if w is None or w > MAX_MEAN or (g is not None and g > MAX_GUST) or (pp or 0) >= MAX_RAIN:
        return None
    return "fly" if w >= MIN_FLY else "maybe" if w >= MIN_TRY else None


def best_window(hourly, day, ok, not_before=None):
    """Längstes Zeitfenster tagsüber, in dem jede Stunde `ok` erfüllt: (start, ende, max_wind) oder None."""
    best, run = None, []
    for t, w, g, pp in zip(hourly["time"], hourly["wind_speed_10m"],
                           hourly["wind_gusts_10m"], hourly["precipitation_probability"]):
        t = datetime.fromisoformat(t)
        if t.date() != day or not (DAY_FROM <= t.hour <= DAY_TO):
            continue
        if not_before is not None and t.hour < not_before:
            continue
        if ok(level(w, g, pp)):
            run.append((t.hour, w))
            if best is None or len(run) > len(best):
                best = list(run)
        else:
            run = []
    if best and len(best) >= MIN_HOURS:
        return best[0][0], best[-1][0] + 1, round(max(w for _, w in best))
    return None


def day_status(hourly, day, not_before=None):
    """('fly', fenster), ('maybe', fenster) oder (None, None)."""
    win = best_window(hourly, day, lambda l: l == "fly", not_before)
    if win:
        return "fly", win
    win = best_window(hourly, day, lambda l: l is not None, not_before)
    return ("maybe", win) if win else (None, None)


def line(status, win):
    if status is None:
        return "kein Wind"
    text = f"{win[0]}–{win[1]} Uhr · bis {win[2]} km/h"
    return text if status == "fly" else "knapp, " + text


IMAGE = {"fly": "notify.png", "maybe": "notify-maybe.png", None: "notify-calm.png"}


def send(title, message, image="notify.png"):
    msg = {"topic": TOPIC, "title": title, "message": message, "click": PAGE, "icon": ICON,
           "attach": PAGE + image, "filename": image}
    body = json.dumps(msg).encode()
    req = urllib.request.Request("https://ntfy.sh/", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20).read()
    print("gesendet:", title, "–", message)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "today"
    now = datetime.now(BERLIN)
    hourly = get_json(FORECAST)["hourly"]

    if mode == "demo":
        # Beispiel mit erfundenen Werten, um das Aussehen der Wochenendvorschau zu prüfen
        lines = [f"Samstag: {line('fly', (11, 15, 22))}", f"Sonntag: {line('maybe', (10, 13, 11))}"]
        send("🪁 Samstag Drachenwetter", "\n".join(lines), image=IMAGE["fly"])
        return

    if mode == "test":
        status, win = day_status(hourly, now.date(), not_before=now.hour)
        when = "Heute"
        if status is None:
            status, win = day_status(hourly, now.date() + timedelta(days=1))
            when = "Morgen"
        info = f"{when}: {line(status, win)}" if status else "Heute und morgen kein Drachenwind."
        send("Test: Benachrichtigungen funktionieren", info, image=IMAGE[status])
        return

    if mode == "weekend":
        days = [d for d in (now.date() + timedelta(days=i) for i in range(1, 4)) if d.weekday() >= 5]
        result = [(WEEKDAY[d.weekday()], *day_status(hourly, d)) for d in days]
        fly = [name for name, st, _ in result if st == "fly"]
        maybe = [name for name, st, _ in result if st == "maybe"]
        if not fly and not maybe:
            print("Kein Drachenwetter am Wochenende.")
            return
        if len(fly) == len(result):
            title = "🪁 Drachenwetter am Wochenende"
        elif fly:
            title = f"🪁 {fly[0]} Drachenwetter"
        else:
            title = "🪁 Wochenende: " + (f"{maybe[0]} vielleicht" if len(maybe) == 1 else "vielleicht")
        lines = [f"{name}: {line(st, win)}" for name, st, win in result]
        send(title, "\n".join(lines), image=IMAGE["fly" if fly else "maybe"])
        return

    # today
    status, win = day_status(hourly, now.date(), not_before=now.hour)
    if status == "fly":
        send("🪁 Heute Drachenwetter", line(status, win), image=IMAGE["fly"])
    elif status == "maybe":
        send("🪁 Heute knapp", f"Mit Anlauf vielleicht: {line('fly', win)}", image=IMAGE["maybe"])
    else:
        print("Heute kein Drachenwetter.")


if __name__ == "__main__":
    main()
