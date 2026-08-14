# RAA 2026 — Dashboard Sebastian Trimborn

Dashboard zum **Race Around Austria Extreme 2026 (Solo)** mit Fokus auf Sebastian
Trimborn (Nr. 2), im Vergleich mit Rainer Steinberger (6) und Lukas Kaufmann (5).

**→ https://flame4ever.github.io/raa2026-trimborn/**

Datenquelle: [race.perfect-tracking.com](https://race.perfect-tracking.com/race/raa2026/ergebnisse)

## Wie es läuft

`build_data.py` holt die Renndaten und schreibt `site/data.json`; `index.html`
wird daneben kopiert und liest die Datei im Browser. Der Workflow in
`.github/workflows/update.yml` macht das alle 5 Minuten und veröffentlicht das
Ergebnis auf GitHub Pages.

Fünf Minuten sind das kürzeste Intervall, das GitHub für geplante Läufe zulässt —
unter Last starten sie oft später, der Datenstand kann also auch mal 10–15 Minuten
alt sein. Die Seite zeigt oben rechts immer, wie alt die Zahlen wirklich sind.
Für eine sofortige Aktualisierung: Tab **Actions → Daten holen und veröffentlichen
→ Run workflow**.

## Lokal ausführen

```bash
python3 build_data.py
python3 -m http.server 8000 --directory site
# http://localhost:8000
```

Braucht nur Python 3, keine zusätzlichen Pakete.

## Wie die Abstände berechnet werden

Die Fahrer starten einzeln, hier zwischen 20:36 und 20:44 Uhr. Alle Live-Punkte
stammen von derselben Uhrzeit, gewertet wird aber die Fahrzeit ab dem eigenen
Start — der Kilometerstand allein sagt also nichts über die Reihenfolge.

* **Nahe Gegner** (weniger als 20 km auseinander): Der Abstand auf der Straße wird
  mit dem aktuellen Tempo in Zeit umgerechnet, davon wird der Startversatz abgezogen.
* **Weit entfernte Gegner**: Aus deren Zeiten an den Zeitnahmestellen wird
  interpoliert, wann sie an der aktuellen Position des Fokusfahrers waren.

Positiv heißt: Trimborn liegt vorn. Abweichungen zur offiziellen Wertung sind
möglich — der Veranstalter reiht an den Zeitnahmestellen.
