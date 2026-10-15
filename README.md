# GTA Online Fahrzeuge

Such- und filterbare Übersicht aller Fahrzeuge in GTA Online. Statische Webseite (Bootstrap 5.3, Dark Theme), gehostet über GitHub Pages.

## Funktionen

- Volltextsuche (Name, deutscher Name, Modellname, Hersteller)
- Mehrfachauswahl mit Checkboxen: Klasse, Hersteller, Händler, Update/DLC, Lagerort (Hangar, Bunker, Facility, Kosatka ...)
- von/bis-Regler: Vmax, Preis, Sitze
- Ja/Nein-Filter: Bewaffnung, Panzerung, Missile Lock-On Jammer, Imani Tech, HSW, Driftcar, Streifenwagen, Spezialfähigkeiten, kugelsichere Scheiben, Benny's-Umbau, Allrad, nur PS5/Xbox Series/PC Enhanced, Einkaufspreis vorhanden, Pegasus, aus dem Handel entfernt
- Detailansicht mit Bild, Händlertext aus dem Spiel, Preis und Einkaufspreis (Trade Price)
- Darstellung: Dunkel, Hell oder Auto (Systemeinstellung)

## Struktur

```
.
├── index.html               Webseite
├── data/
│   ├── vehicles.json        aufbereitete Fahrzeugdaten
│   └── vehicles-data.js     dieselben Daten für index.html (funktioniert auch per file://)
├── scripts/
│   └── build_vehicles.py    lädt und bereinigt die Daten aus dem GTA Wiki
├── .nojekyll                GitHub Pages ohne Jekyll ausliefern
└── README.md
```

## Daten aktualisieren

Benötigt nur Python 3 (Standardbibliothek).

```
python scripts/build_vehicles.py
git add data
git commit -m "Daten aktualisiert"
git push
```

## Lokal ansehen

`index.html` per Doppelklick im Browser öffnen.

## Bekannte Einschränkungen

- **Garage:** Für „In Garage lagern“ gibt es keine verlässliche Datenquelle, der Filter ist deaktiviert (TODO).
- **Jammer:** Ermittelt aus der Händlerbeschreibung („Missile Lock-On Jammer available“).
- **Streifenwagen:** Polizeifahrzeuge laut Wiki, ohne Helikopter, Flugzeuge, Boote und Motorräder.
- **Entfernt:** Basierend auf den Wiki-Kategorien „removed for purchase“ abzüglich „reinstated for purchase“.
- **Vmax:** Handling-Wert aus den Spieldaten, keine gemessene Höchstgeschwindigkeit.

## Quellen und Lizenz

- Fahrzeugdaten: [GTA Wiki](https://gta.wiki), Lizenz [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/). Die Daten in `data/` stehen daher ebenfalls unter CC BY-NC-SA 3.0 und dürfen nicht kommerziell genutzt werden.
- Bilder werden direkt vom GTA Wiki geladen. Bilder, Fahrzeugnamen und Händlertexte © Rockstar Games.
- Privates, nicht-kommerzielles Fanprojekt, nicht mit Rockstar Games verbunden.
