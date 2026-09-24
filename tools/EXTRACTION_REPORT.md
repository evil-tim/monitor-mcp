# Registry extraction report

Extracted 40 rows from `/home/hermes/wiki/queries/future-events-monitoring-dashboard-2026.md` on 2026-09-24.

## Classification

| kind | rows | meaning |
|---|---|---|
| threshold | 29 | a numeric comparator was extracted |
| event | 1 | a date was extracted |
| qualitative | 10 | neither; carries a `review_by` backstop |

## Entities

| ticker | name | feed | libram_code |
|---|---|---|---|
| ACEN | ACEN Corporation | libram | ACEN |
| AREIT | AREIT, Inc. | libram | AREIT |
| BPI | Bank of the Philippine Islands | libram | BPI |
| CREC | Citicore Renewable Energy Corp. | libram | CREC |
| CREIT | Citicore Energy REIT Corp. | libram | CREIT |
| ICTSI | International Container Terminal Services, Inc. | libram | ICT |
| MWIDE | Megawide Construction Corporation | libram | MWIDE |
| NGCP | National Grid Corp. of the Philippines (unlisted) | manual | - |
| OGP | OceanaGold (Philippines), Inc. | libram | OGP |
| PH1 | UNRESOLVED registry code — appears in rows 26 and 40, meaning not established | manual | - |
| RCR | RL Commercial REIT, Inc. | libram | RCR |
| SCC | Semirara Mining and Power Corporation | libram | SCC |

## Rows needing review

| legacy_row | slug | kind | flags |
|---|---|---|---|
| 1 | angat-dam-water-level | threshold | 4 tiers in prose; compound condition in prose |
| 2 | pagasa-el-nino-classification | qualitative | no threshold and no date: review_by placeholder |
| 3 | ngcp-reserve-margin-report | threshold | 2 tiers in prose |
| 6 | battery-storage-procurement-award | qualitative | no threshold and no date: review_by placeholder |
| 7 | wesm-average-monthly-spot-price | threshold | 2 tiers in prose |
| 12 | 2028-presidential-candidate-policy-platform | qualitative | no threshold and no date: review_by placeholder |
| 14 | denr-mgb-approval | qualitative | no threshold and no date: review_by placeholder |
| 15 | ra-12253-fiscal-regime-resolution | qualitative | no threshold and no date: review_by placeholder |
| 16 | qatar-ras-laffan-helium-repair-status | qualitative | no threshold and no date: review_by placeholder |
| 18 | gold-spot-price-support | qualitative | no threshold and no date: review_by placeholder |
| 19 | copper-spot-price-support | qualitative | no threshold and no date: review_by placeholder |
| 30 | hire-act-keep-call-centers-in-america-act | qualitative | no threshold and no date: review_by placeholder |
| 33 | capital-refinancing-adequacy | qualitative | no threshold and no date: review_by placeholder |

## Open questions for the operator

1. `PH1` is used as an entity in rows 26 and 40 but is not a recognisable code. Seeded as unresolved.
2. The registry says `ICTSI`; Libram tracks the same company as `ICT`. Recorded as `libram_code`.
3. `NGCP` is not PSE-listed. Kept as an entity because the registry names it as one.
4. `review_by` on qualitative rows is a placeholder (today + 180d), not an operator decision.
5. Tier and compound conditions survive as prose in the source; only the primary comparator was
   extracted. Tiers are carried in `tiers` and are not yet enforced.
6. Row 28 is the only row in the source with 6 cells rather than 7; its impacts live inside the
   threshold cell. The legacy table was already internally inconsistent.
