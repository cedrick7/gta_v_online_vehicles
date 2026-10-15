#!/usr/bin/env python3
"""
GTA Online Fahrzeugdaten aufbereiten.

Quelle: GTA Wiki (https://gta.wiki), MediaWiki-API, Lizenz CC BY-NC-SA 3.0.
Jede Wiki-Seite entspricht einem Fahrzeug, dadurch entfallen die Modell-
Dubletten (z. B. cargobob, cargobob2, cargobob3 ...) aus reinen Spieldaten-Dumps.

Ausgabe (Ordner data/ im Projekt):
  data/vehicles.json     Datenliste
  data/vehicles-data.js  gleiche Daten als  window.VEHICLES = [...]
                         (wird von index.html geladen, funktioniert auch per file://)

Nur Python-Standardbibliothek, kein pip install noetig.
Aufruf (im Projektordner):  python scripts/build_vehicles.py
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://gta.wiki/api.php"
UA = "gta-vehicle-table/1.0 (private, non-commercial use)"
DELAY = 0.6  # Sekunden zwischen Anfragen (Server schonen)

ROOT_CAT = "Category:Vehicles in GTA Online"
FLAG_CATS = {
    "weapons": ["Category:Weaponized Vehicles in GTA Online"],
    "armored": ["Category:Armored vehicles"],
    "drift": ["Category:Drift racing class", "Category:Vehicles eligible for Drift Tune conversion"],
    "pegasus": ["Category:Vehicles requested via Pegasus Lifestyle Management"],
    "hangar": ["Category:Vehicles storable in a Hangar"],  # Unterkategorien nach Groesse
    "imani": ["Category:Vehicles eligible for Imani Tech upgrades"],
    "police": ["Category:Law enforcement vehicles"],
    "hsw": ["Category:Vehicles eligible for Hao's Special Works conversion"],
    "special": ["Category:Vehicles with Special Abilities"],
    "bulletproof": ["Category:Vehicles with bullet-resistant windows"],
    "bennys": ["Category:Vehicles eligible for Benny's Original Motor Works conversion"],
    "awd": ["Category:All wheel drive vehicles"],
    "ee": ["Category:Vehicles in GTA Online: Expanded and Enhanced Edition"],  # ergaenzt um {{E|E&E}} im Infobox-Feld games
}
STORAGE_PREFIX = "Vehicles storable in "
# Klassen, die nicht als "Streifenwagen" zaehlen (Polizei-Helis, -Boote, -Motorraeder)
NOT_PATROL_CLASSES = {"Helicopters", "Planes", "Boats", "Motorcycles", "Cycles"}
DEALER_PREFIX = "Vehicles purchasable from "
MAKER_PREFIX = "Vehicles manufactured by "
MAKER_ALIASES = {"Kraken Submersibles": "Kraken"}  # bei Bedarf ergaenzen
REMOVED_PREFIX = "Vehicles removed for purchase in GTA Online"
REINSTATED_PREFIX = "Vehicles reinstated for purchase in GTA Online"


# ---------------------------------------------------------------- API

def api(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            time.sleep(DELAY)
            return data
        except Exception as e:  # Netzfehler: kurz warten, erneut versuchen
            if attempt == 3:
                raise
            print(f"  Fehler ({e}), neuer Versuch ...", file=sys.stderr)
            time.sleep(3 * (attempt + 1))


def query_all(**params):
    """Folgt dem MediaWiki-'continue' und liefert alle Teilergebnisse."""
    cont = {}
    while True:
        data = api(action="query", **params, **cont)
        yield data.get("query", {})
        if "continue" not in data:
            break
        cont = data["continue"]


def cat_members(cat, recurse_prefix=None, _seen=None):
    """Alle Seiten (Namespace 0) einer Kategorie, optional rekursiv."""
    _seen = _seen if _seen is not None else set()
    if cat in _seen:
        return set()
    _seen.add(cat)
    pages = set()
    for q in query_all(list="categorymembers", cmtitle=cat, cmlimit="500", cmtype="page|subcat"):
        for m in q.get("categorymembers", []):
            if m["ns"] == 0:
                pages.add(m["title"])
            elif m["ns"] == 14 and (recurse_prefix is None or m["title"].startswith(recurse_prefix)):
                pages |= cat_members(m["title"], recurse_prefix, _seen)
    return pages


def categories_with_prefix(prefix):
    out = []
    for q in query_all(list="allcategories", acprefix=prefix, aclimit="500"):
        out += ["Category:" + (c.get("category") or c.get("*")) for c in q.get("allcategories", [])]
    return out


def batched(items, n=50):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ---------------------------------------------------------------- Wikitext-Parser

def find_templates(text, name):
    """Liefert den Inhalt aller {{name ...}} Vorlagen (verschachtelungssicher)."""
    out, low, key = [], text.lower(), "{{" + name.lower()
    i = 0
    while True:
        i = low.find(key, i)
        if i < 0:
            return out
        nxt = low[i + len(key):i + len(key) + 1]
        if nxt and nxt not in "|\n }":  # z. B. {{Quote2 statt {{Quote
            i += 1
            continue
        depth, j = 0, i
        while j < len(text) - 1:
            if text[j:j + 2] == "{{":
                depth += 1; j += 2; continue
            if text[j:j + 2] == "}}":
                depth -= 1; j += 2
                if depth == 0:
                    break
                continue
            j += 1
        out.append(text[i + 2 + len(name):j - 2])
        i = j


def split_params(body):
    """Teilt Vorlagenparameter an '|' auf oberster Ebene."""
    parts, buf, depth = [], [], 0
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1; buf.append(two); i += 2; continue
        if two in ("}}", "]]"):
            depth -= 1; buf.append(two); i += 2; continue
        if body[i] == "|" and depth == 0:
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(body[i]); i += 1
    parts.append("".join(buf))
    named, positional = {}, []
    for p in parts[1:]:  # parts[0] = Rest des Vorlagennamens
        if "=" in p and re.match(r"^\s*[\w ]+\s*=", p):
            k, v = p.split("=", 1)
            named[k.strip().lower()] = v.strip()
        else:
            positional.append(p.strip())
    return named, positional


SIMPLE_TEMPLATES = {"o": "GTA Online", "v": "GTA V", "vo": "GTA V und GTA Online", "nd": "–"}


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"\[\[(?:File|Image|Datei):[^\]]*\]\]", "", s, flags=re.I)
    s = re.sub(r"\[\[:?Category:[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    for _ in range(5):  # innere Vorlagen aufloesen
        def repl(m):
            parts = m.group(1).split("|")
            name = parts[0].strip().lower()
            if name in SIMPLE_TEMPLATES:
                return SIMPLE_TEMPLATES[name]
            if name in ("small", "nowrap", "tooltip") and len(parts) > 1:
                return parts[1]
            if name == "wp" and len(parts) > 1:
                return parts[-1]
            return ""
        s2 = re.sub(r"\{\{([^{}]*)\}\}", repl, s)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def money(s):
    m = re.search(r"\$\s*([\d,]+)", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def first_int(s):
    m = re.search(r"\d+", s or "")
    return int(m.group(0)) if m else None


ONLINE_TAG = re.compile(r"online|gta v(?!i)\b|website and game files|game files", re.I)
OTHER_GAME_TAG = re.compile(r"gta (iv|vi|iii|sa|vc|lcs|vcs|2)\b|tbogt|tlad|eflc|chinatown|ds version", re.I)


def pick_maker(raw, cat_makers=()):
    return pick_for_online(raw, cat_makers)


def pick_for_online(raw, fallback=()):
    """
    Das Wiki listet im Feld 'manufacturer' oft mehrere Spiele, z. B.
      *Western Company (GTA IV)
      *Buckingham (GTA V & GTA Online)
    Gewaehlt wird die Zeile fuer GTA V/Online, sonst die erste Zeile ohne
    fremde Spielangabe. Klammerzusaetze werden entfernt. Fallback: die
    Kategorie 'Vehicles manufactured by X', wenn sie eindeutig ist.
    """
    best = None
    for line in (raw or "").split("\n"):
        line = line.strip().lstrip("*").strip()
        if not line:
            continue
        tags = " ".join(re.findall(r"\(([^)]*)\)?", line))
        name = re.sub(r"\s*\([^)]*\)?", "", line).strip(" ,;)")
        if not name or re.search(r'[="{}|]', name):  # Tabellen-/Markup-Reste verwerfen
            continue
        if ONLINE_TAG.search(tags):
            prio = 0
        elif OTHER_GAME_TAG.search(tags):
            continue
        else:
            prio = 1
        if best is None or prio < best[0]:
            best = (prio, name)
    if best:
        return best[1]
    cats = sorted(set(fallback))
    return cats[0] if len(cats) == 1 else ""


def spec_value(text, template, field):
    """Wert aus Specifications-Vorlagen, bevorzugt fuer das Spiel 'O' (Online)."""
    for body in find_templates(text, template):
        named, _ = split_params(body)
        games = sorted(k for k in named if re.fullmatch(r"game\d+", k))
        order = [g for g in games if named[g].strip().upper() == "O"] + games
        for g in order:
            v = named.get(f"{g}_{field}", "").strip()
            if v:
                return v
    return ""


def parse_page(title, text):
    box = find_templates(text, "Infobox vehicle")
    if not box:
        return None  # Listen-/Uebersichtsseite, kein einzelnes Fahrzeug
    info = split_params(box[0])[0]
    class_cats = [c for c in re.findall(r"\[\[Category:([^\]|]+?) class\s*[\]|]", text)
                  if c.strip() != "Drift racing"]

    descriptions = []
    for body in find_templates(text, "Quote"):
        _, pos = split_params(body)
        if len(pos) >= 2 and "description" in pos[1].lower():
            descriptions.append({"source": clean(pos[1]).rstrip("."), "text": clean(pos[0])})

    speed = spec_value(text, "Specifications Vehicle Handling", "maxvelocity")
    try:
        speed = round(float(speed.replace(",", ".")), 1)
    except ValueError:
        speed = None

    return {
        "title": title,
        "name": clean(info.get("name")) or title,
        "nameDe": clean(spec_value(text, "Specifications Vehicle Language", "langde")),
        "model": clean(spec_value(text, "Specifications Vehicle Model", "modelname")),
        "maker": clean(info.get("manufacturer")),
        "cls": pick_for_online(clean(info.get("class")), class_cats),
        "type": clean(info.get("type")),
        "seats": first_int(clean(info.get("capacity"))),
        "priceText": clean(info.get("price")),
        "price": money(clean(info.get("price"))),
        "tradePriceText": clean(info.get("trade_price")),
        "tradePrice": money(clean(info.get("trade_price"))),
        "speed": speed,
        "descriptions": descriptions,
        # {{E|E&E}} = nur Expanded and Enhanced Edition (PS5, Xbox Series, PC Enhanced);
        # {{E|EE&E}} bedeutet beide Editionen und zaehlt nicht
        "eeOnly": bool(re.search(r"\{\{\s*(?:E|Edition)\s*\|\s*E&E\s*\}\}", info.get("games", ""))),
    }


def dealers_from_price(vehicles):
    """Ergaenzt Haendler, die nur im Preistext stehen (Wiki-Kategorie fehlt, z. B. Hardy)."""
    known = {d for v in vehicles for d in v.get("dealers", [])}
    added = 0
    for v in vehicles:
        text = v.get("priceText") or ""
        for d in known:
            if d in text and d not in v["dealers"]:
                v["dealers"] = sorted(v["dealers"] + [d])
                added += 1
    print(f"    Haendler aus Preistext ergaenzt: {added}")
    return vehicles


DRIFT_SUFFIX = " (Drift Tune)"


def merge_drift_tunes(vehicles):
    """
    Das Wiki fuehrt Drift-Tune-Umbauten als eigene Seiten ("Hardy (Drift Tune)").
    Das ist kein eigenes Fahrzeug, sondern ein Upgrade: Kosten und Werte werden
    beim Basisfahrzeug als 'driftTune' eingetragen, die Upgrade-Seite entfaellt.
    Ohne passendes Basisfahrzeug bleibt der Eintrag unveraendert.
    """
    by_title = {v["title"]: v for v in vehicles}
    merged = set()
    for v in vehicles:
        if not v["title"].endswith(DRIFT_SUFFIX):
            continue
        base = by_title.get(v["title"][: -len(DRIFT_SUFFIX)])
        if not base:
            continue
        base["driftTune"] = {
            "price": v.get("price"),
            "priceText": v.get("priceText", ""),
            "speed": v.get("speed"),
            "url": v.get("url"),
        }
        base["drift"] = True
        merged.add(v["title"])
    print(f"    Drift-Tune-Upgrades zusammengefuehrt: {len(merged)}")
    return [v for v in vehicles if v["title"] not in merged]


# ---------------------------------------------------------------- Ablauf

def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)

    print("1/5 Fahrzeugliste (GTA Online) ...")
    titles = {t for t in cat_members(ROOT_CAT, recurse_prefix=ROOT_CAT) if "/" not in t}  # ohne Unterseiten
    print(f"    {len(titles)} Seiten")

    # Update/DLC je Seite (aus Unterkategorien "Vehicles in GTA Online: <Update>")
    dlc = {}
    for cat in categories_with_prefix("Vehicles in GTA Online:"):
        label = cat.split(":", 2)[-1].strip()
        for t in cat_members(cat):
            # Editions-Kategorien nur verwenden, wenn kein echtes Update bekannt ist
            if "Edition" in label and t in dlc:
                continue
            dlc[t] = label

    print("2/5 Eigenschaften (Kategorien) ...")
    flags = {}
    for key, cats in FLAG_CATS.items():
        s = set()
        for c in cats:
            s |= cat_members(c, recurse_prefix=c)
        flags[key] = s
        print(f"    {key}: {len(s)}")

    removed = set().union(*[cat_members(c) for c in categories_with_prefix(REMOVED_PREFIX)] or [set()])
    reinstated = set().union(*[cat_members(c) for c in categories_with_prefix(REINSTATED_PREFIX)] or [set()])
    print(f"    entfernt: {len(removed)}, wieder eingefuehrt: {len(reinstated)}")

    dealers = {}
    for cat in categories_with_prefix(DEALER_PREFIX):
        name = cat.split(DEALER_PREFIX, 1)[1]
        for t in cat_members(cat):
            dealers.setdefault(t, []).append(name)

    storage = {}
    for cat in categories_with_prefix(STORAGE_PREFIX):
        label = re.sub(r"^(a|an|the) ", "", cat.split(STORAGE_PREFIX, 1)[1])
        for t in cat_members(cat, recurse_prefix=None):  # Hangar hat Unterkategorien nach Groesse
            storage.setdefault(t, set()).add(label)
    print(f"    Lagerorte: {sorted({l for s in storage.values() for l in s})}")

    makers = {}
    for cat in categories_with_prefix(MAKER_PREFIX):
        name = re.sub(r"\s*\([^)]*\)", "", cat.split(MAKER_PREFIX, 1)[1]).strip()
        for t in cat_members(cat):
            makers.setdefault(t, []).append(name)

    print("3/5 Seiteninhalte ...")
    texts = {}
    for chunk in batched(sorted(titles)):
        for q in query_all(prop="revisions", rvprop="content", rvslots="main", titles="|".join(chunk)):
            for p in q.get("pages", []):
                revs = p.get("revisions")
                if revs:
                    texts[p["title"]] = revs[0]["slots"]["main"]["content"]

    print("4/5 Bilder ...")
    images = {}
    for chunk in batched(sorted(titles)):
        for q in query_all(prop="pageimages", piprop="thumbnail|original", pithumbsize="480", titles="|".join(chunk)):
            for p in q.get("pages", []):
                if "thumbnail" in p or "original" in p:
                    images[p["title"]] = {
                        "thumb": p.get("thumbnail", {}).get("source"),
                        "full": p.get("original", {}).get("source"),
                    }

    print("5/5 Zusammenfuehren ...")
    vehicles = []
    for t in sorted(titles):
        if t not in texts:
            continue
        v = parse_page(t, texts[t])
        if v is None:
            continue
        v["makerRaw"] = v["maker"]
        v["maker"] = pick_maker(v["maker"], makers.get(t, []))
        ee_only = v.pop("eeOnly")
        jammer = any("lock-on jammer" in d["text"].lower() for d in v["descriptions"])
        v.update({
            "url": "https://gta.wiki/w/" + urllib.parse.quote(t.replace(" ", "_")),
            "dlc": dlc.get(t, ""),
            "dealers": sorted(dealers.get(t, [])),
            "image": images.get(t, {}).get("thumb"),
            "imageFull": images.get(t, {}).get("full"),
            "weapons": t in flags["weapons"],
            "armored": t in flags["armored"],
            "drift": t in flags["drift"],
            "pegasus": t in flags["pegasus"],
            "hangar": t in flags["hangar"],
            "garage": None,  # TODO: keine verlaessliche Kategorie im Wiki gefunden
            "removed": t in removed and t not in reinstated,
            "imani": t in flags["imani"],
            "hsw": t in flags["hsw"],
            "special": t in flags["special"],
            "bulletproof": t in flags["bulletproof"],
            "bennys": t in flags["bennys"],
            "awd": t in flags["awd"],
            "ee": ee_only or t in flags["ee"],
            "storage": sorted(storage.get(t, [])),
            "jammer": jammer,  # laut Haendlerbeschreibung ("Missile Lock-On Jammer available")
            "police": t in flags["police"],
            "patrol": t in flags["police"] and v["cls"] not in NOT_PATROL_CLASSES,
        })
        vehicles.append(v)

    vehicles = merge_drift_tunes(vehicles)
    vehicles = dealers_from_price(vehicles)

    # Schreibweisen vereinheitlichen: gross/klein (z. B. Jobuilt/JoBuilt) -> haeufigste Form
    counts = {}
    for v in vehicles:
        v["maker"] = MAKER_ALIASES.get(v["maker"], v["maker"])
        counts.setdefault(v["maker"].lower(), {}).setdefault(v["maker"], 0)
        counts[v["maker"].lower()][v["maker"]] += 1
    for v in vehicles:
        forms = counts[v["maker"].lower()]
        v["maker"] = max(forms, key=forms.get)

    meta = {
        "source": "GTA Wiki (gta.wiki), CC BY-NC-SA 3.0",
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "count": len(vehicles),
    }
    payload = {"meta": meta, "vehicles": vehicles}
    (out_dir / "vehicles.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "vehicles-data.js").write_text(
        "window.VEHICLES = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Fertig: {len(vehicles)} Fahrzeuge -> {out_dir}")


if __name__ == "__main__":
    main()
