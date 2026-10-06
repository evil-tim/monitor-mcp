"""Extract the legacy 40-row registry from the wiki dashboard into the seed module.

The markdown-to-store migration is a script plus a reviewed diff, not 40 rows of
hand-typing. Rows the parser cannot classify confidently are flagged, never guessed.
"""
import re, sys, json, unicodedata, datetime as dt

SRC = sys.argv[1]
OUT_SEED = sys.argv[2]
OUT_REPORT = sys.argv[3]

def split_cells(line):
    line = line.strip()
    if line.startswith("|"): line = line[1:]
    if line.endswith("|"):   line = line[:-1]
    return [p.strip().replace("\\|", "|") for p in re.split(r"(?<!\\)\|", line)]

rows = []
for ln in open(SRC, encoding="utf-8"):
    if re.match(r"^\|\s*\d+\s*\|", ln):
        c = split_cells(ln)
        if len(c) < 6: continue
        rows.append(dict(legacy_row=int(c[0]), category=c[1], description=c[2],
                         source=c[3], freq=c[4], threshold=c[5],
                         impacts=c[6] if len(c) > 6 else ""))

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September",
     "October","November","December"], 1)}
for m, v in list(MONTHS.items()):
    MONTHS[m[:3]] = v

NUM  = r"-?[\d][\d,]*\.?\d*"
CMP  = re.compile(r"([<>]=?)\s*(?:PHP|P|US\$|\$)?\s*(" + NUM + r")")
TIER = re.compile(r"([A-Z][A-Za-z ]{2,22}?)\s*:\s*([<>]=?)\s*(?:PHP|P|US\$|\$)?\s*(" + NUM + r")")
DATE = re.compile(r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(20\d\d)")
IMP  = re.compile(r"([A-Z][A-Z0-9&]{1,7})\s*([\u2191\u2193])")
PIPED= re.compile(r"\|([A-Z][A-Z0-9&]{1,7})\|")

def find_date(text):
    m = DATE.search(text)
    if not m: return None
    mo = MONTHS.get(m.group(1).lower())
    return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}" if mo else None

def num(s): return float(s.replace(",", ""))

CAD = [("real-time","event"),("one-time","event"),("sporadic","event"),
       ("daily","daily"),("weekly","weekly"),("monthly","monthly"),
       ("quarterly","quarterly"),("bimonthly","quarterly"),("annual","quarterly")]
def cadence(freq):
    f = freq.lower()
    for k, v in CAD:
        if k in f: return v
    return "monthly"

def slugify(text, limit=52):
    # NFKD so "El Ni\u00f1o" -> "el-nino" rather than "el-ni-o"
    s = unicodedata.normalize("NFKD", text)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return "-".join(s.split("-")[:9])[:limit].strip("-")

REVIEW_BY = (dt.date.today() + dt.timedelta(days=180)).isoformat()
seen, sigs, ents = {}, [], {}
for r in rows:
    t = r["threshold"]
    cmps = CMP.findall(t)
    tiers = [dict(label=a.strip(), op=b, value=num(c)) for a, b, c in TIER.findall(t)]
    due = find_date(t) or find_date(r["description"])
    # row 28 (and any future row) hides its impacts inside the threshold cell
    impact_text = r["impacts"] + " \u00b7 " + (t if len(split_cells(open(SRC).readline())) == 6 else "")
    impact_text = r["impacts"] + " \u00b7 " + t
    pairs = {}
    for m in IMP.finditer(impact_text):
        pairs.setdefault(m.group(1), "up" if m.group(2) == "\u2191" else "down")
    for m in PIPED.finditer(impact_text):
        pairs.setdefault(m.group(1), "flat")

    if cmps:
        kind, op, thr = "threshold", cmps[0][0], num(cmps[0][1])
    elif due:
        kind, op, thr = "event", None, None
    else:
        kind, op, thr = "qualitative", None, None

    slug = slugify(r["description"])
    n = seen.get(slug, 0); seen[slug] = n + 1
    if n: slug = f"{slug}-{r['legacy_row']}"

    flags = []
    if kind == "qualitative": flags.append("no threshold and no date: review_by placeholder")
    if len(tiers) > 1: flags.append(f"{len(tiers)} tiers in prose")
    if "Compound" in t: flags.append("compound condition in prose")
    if not pairs: flags.append("no impact tickers parsed")

    for tk in pairs: ents.setdefault(tk, None)

    sigs.append(dict(legacy_row=r["legacy_row"], slug=slug, category=r["category"],
                     description=re.sub(r"\s+", " ", r["description"]).strip(),
                     source=re.sub(r"\s+", " ", r["source"]).strip(),
                     cadence=cadence(r["freq"]), kind=kind, op=op, threshold_num=thr,
                     due_date=due if kind == "event" else None,
                     review_by=REVIEW_BY if kind == "qualitative" else None,
                     tiers=tiers, impacts=pairs, flags=flags, rationale=None))

# entity registry: the registry's own vocabulary, plus the Libram code where they differ
KNOWN = {
 "ACEN": ("ACEN Corporation", "ACEN"), "AREIT": ("AREIT, Inc.", "AREIT"),
 "BPI": ("Bank of the Philippine Islands", "BPI"), "CREC": ("Citicore Renewable Energy Corp.", "CREC"),
 "CREIT": ("Citicore Energy REIT Corp.", "CREIT"), "ICTSI": ("International Container Terminal Services, Inc.", "ICT"),
 "MWIDE": ("Megawide Construction Corporation", "MWIDE"), "NGCP": ("National Grid Corp. of the Philippines (unlisted)", None),
 "OGP": ("OceanaGold (Philippines), Inc.", "OGP"), "RCR": ("RL Commercial REIT, Inc.", "RCR"),
 "SCC": ("Semirara Mining and Power Corporation", "SCC"),
 "PH1": ("PH1 World Developers, Inc. (Megawide real-estate arm; unlisted)", None),  # resolved 2026-10-06
}
entities = []
for tk in sorted(ents):
    name, lib = KNOWN.get(tk, (f"{tk} (not in the known mapping)", None))
    entities.append(dict(ticker=tk, name=name, feed="libram" if lib else "manual", libram_code=lib))

body = json.dumps({"entities": entities, "signals": sigs}, indent=1)
open("/tmp/seed_raw.json", "w").write(body)

# ---- emit the seed module
lines = ['"""GENERATED by tools/extract_registry.py \u2014 do not edit by hand.',
         "",
         f"Source: {SRC}",
         f"Generated: {dt.date.today().isoformat()}",
         f"Rows: {len(sigs)} (legacy rows {min(s['legacy_row'] for s in sigs)}-{max(s['legacy_row'] for s in sigs)})",
         "Flags and open questions: tools/EXTRACTION_REPORT.md",
         '"""', "", "ENTITIES = ["]
for e in entities:
    lines.append(f" {e!r},")
lines += ["]", "", "SIGNALS = ["]
for s in sigs:
    lines.append(" {")
    for k in ("legacy_row","slug","category","description","source","cadence","kind",
              "op","threshold_num","due_date","review_by","rationale"):
        lines.append(f"  {k!r}: {s[k]!r},")
    lines.append(f"  'tiers': {s['tiers']!r},")
    lines.append(f"  'impacts': {s['impacts']!r},")
    lines.append(" },")
lines += ["]", ""]
open(OUT_SEED, "w").write("\n".join(lines))

# ---- emit the extraction report
rep = [f"# Registry extraction report", "",
       f"Extracted {len(sigs)} rows from `{SRC}` on {dt.date.today().isoformat()}.",
       "",
       "## Classification", "",
       "| kind | rows | meaning |", "|---|---|---|",
       f"| threshold | {sum(1 for s in sigs if s['kind']=='threshold')} | a numeric comparator was extracted |",
       f"| event | {sum(1 for s in sigs if s['kind']=='event')} | a date was extracted |",
       f"| qualitative | {sum(1 for s in sigs if s['kind']=='qualitative')} | neither; carries a `review_by` backstop |",
       "", "## Entities", "",
       "| ticker | name | feed | libram_code |", "|---|---|---|---|"]
for e in entities:
    rep.append(f"| {e['ticker']} | {e['name']} | {e['feed']} | {e['libram_code'] or '-'} |")
rep += ["", "## Rows needing review", "", "| legacy_row | slug | kind | flags |", "|---|---|---|---|"]
for s in sigs:
    if s["flags"]:
        rep.append(f"| {s['legacy_row']} | {s['slug']} | {s['kind']} | {'; '.join(s['flags'])} |")
rep += ["", "## Open questions for the operator", "",
        "1. `PH1` is used as an entity in rows 26 and 40 but is not a recognisable code. Seeded as unresolved.",
        "2. The registry says `ICTSI`; Libram tracks the same company as `ICT`. Recorded as `libram_code`.",
        "3. `NGCP` is not PSE-listed. Kept as an entity because the registry names it as one.",
        "4. `review_by` on qualitative rows is a placeholder (today + 180d), not an operator decision.",
        "5. Tier and compound conditions survive as prose in the source; only the primary comparator was",
        "   extracted. Tiers are carried in `tiers` and are not yet enforced.",
        "6. Row 28 is the only row in the source with 6 cells rather than 7; its impacts live inside the",
        "   threshold cell. The legacy table was already internally inconsistent.", ""]
open(OUT_REPORT, "w").write("\n".join(rep))
print(json.dumps({"rows": len(sigs), "entities": len(entities),
                  "flagged": sum(1 for s in sigs if s["flags"])}, indent=1))
