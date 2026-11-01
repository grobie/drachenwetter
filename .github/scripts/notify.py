#!/usr/bin/env python3
"""Prüft die DWD-Vorhersage (ICON via Open-Meteo) für das Tempelhofer Feld und
schickt bei gutem Drachenwetter eine Nachricht an ntfy.

Modi (erstes Argument):
  weekend  – Vorschau für Samstag und Sonntag (Freitagabend)
  today    – nur heute (Samstag-/Sonntagmorgen)
  test     – schickt immer eine Testnachricht mit der aktuellen Lage
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

# Schwellen in km/h (10-Minuten-Mittelwind) – wie in App und Webseite
MIN_FLY, MAX_MEAN, MAX_GUST, MAX_RAIN = 12, 38, 55, 50
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


def best_window(hourly, day, not_before=None):
    """Längstes Zeitfenster mit Drachenwind an einem Tag: (start, ende, max_wind) oder None."""
    best, run = None, []
    for t, w, g, pp in zip(hourly["time"], hourly["wind_speed_10m"],
                           hourly["wind_gusts_10m"], hourly["precipitation_probability"]):
        t = datetime.fromisoformat(t)
        if t.date() != day or not (DAY_FROM <= t.hour <= DAY_TO):
            continue
        if not_before is not None and t.hour < not_before:
            continue
        good = (w is not None and MIN_FLY <= w <= MAX_MEAN
                and (g is None or g <= MAX_GUST) and (pp or 0) < MAX_RAIN)
        if good:
            run.append((t.hour, w))
            if best is None or len(run) > len(best):
                best = list(run)
        else:
            run = []
    if best and len(best) >= MIN_HOURS:
        return best[0][0], best[-1][0] + 1, round(max(w for _, w in best))
    return None


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

    if mode == "test":
        win = best_window(hourly, now.date()) or best_window(hourly, now.date() + timedelta(days=1))
        info = f"Nächstes Fenster: {line(win)}" if win else "Heute und morgen kein Drachenwind."
        send("Test: Benachrichtigungen funktionieren", info,
             image="notify.png" if win else "notify-calm.png")
        return

    if mode == "weekend":
        days = [d for d in (now.date() + timedelta(days=i) for i in range(1, 4)) if d.weekday() >= 5]
        lines = []
        for d in days:
            win = best_window(hourly, d)
            if win:
                lines.append(f"{WEEKDAY[d.weekday()]}: {line(win)}")
        if lines:
            send("🪁 Drachenwetter am Wochenende", "\n".join(lines))
        else:
            print("Kein Drachenwetter am Wochenende.")
        return

    # today
    win = best_window(hourly, now.date(), not_before=now.hour)
    if win:
        send("🪁 Heute Drachenwetter", line(win))
    else:
        print("Heute kein Drachenwetter.")


if __name__ == "__main__":
    main()
