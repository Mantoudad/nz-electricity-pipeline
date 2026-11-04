## WITS Market Prices API — RTD

- tradingDateTime: dispatch interval start, NZ local time with UTC offset,
  format YYYY-MM-DDTHH:MM:SS+13:00 (+13:00 NZDT summer, +12:00 NZST winter);
  observed on 5-min boundaries
- tradingPeriod: 1–48 half-hour period of the day (46/50 on DST change days)
- lastRunTime: when the price was calculated; ~1 min latency observed
- price: NZD/MWh, energy market (marketType=E)
- node: 7-char grid connection point code (GXP/GIP)
  = 3-letter substation code + 3-digit voltage in kV + 1-digit bus number
  e.g. BEN2201 = Benmore, 220 kV, bus 1; OTA2201 = Otahuhu, 220 kV, bus 1
  (low voltages are zero-padded, e.g. 011 = 11 kV, 033 = 33 kV)
- marketType: E = energy price (NZD/MWh), R = reserve price
  - reserve has two products: FIR (6-second, price6s) and SIR (60-second, price60s)
  - project focuses on E; only E is collected today (WITS_MARKET_TYPE=E), so R is not in bronze
- Fields vary by schedule (e.g. price6s/price60s not in RTD)

JSON response:  
{
  "schedule": "RTD",  
  "prices": [  
    {  
      "schedule": "RTD",  
      "runType": "D",  
      "tradingDateTime": "2026-10-19T21:50:00+13:00",  
      "tradingPeriod": 44,  
      "marketType": "E",  
      "node": "BEN2201",  
      "price": 34.4,  
      "lastRunTime": "2026-10-19T21:49:00+13:00"  
    },  
    ...
  ]
}

## Storage cost estimate (bronze layer)

- File size: ~25 KB per run (gzipped JSON, median ~3,400 RTD records across all nodes)
- Volume: 288 runs/day (every 5 min) → ~7 MB/day → ~210 MB/month (~2.5 GB/year);
  actual full days in Nov 2026 were 6.9–7.2 MB
- Storage cost: ADLS Gen2 Hot tier (LRS) is a few cents per GB-month,
  so storage costs well under US$0.01/month initially, and still only cents/month after a year
- Write operations: ~8,600 uploads/month, also only cents at current transaction pricing
- gzip keeps files small; raw JSON is estimated to be ~10x larger (to be verified)
- Future optimisation: lifecycle policy to move older raw files to the Cool tier

## Time zones in the bronze layer

- Ingestion timestamps use UTC (set in function_app.py via datetime.now(timezone.utc)):
  - folder partition: date=YYYY-MM-DD (UTC date)
  - file name: rtd_E_YYYYMMDDTHHMMSSZ.json.gz ("Z" = UTC)
  - payload field: ingestedAt (UTC, ISO 8601)
- Price data keeps the source time zone: tradingDateTime and lastRunTime are
  NZ local time with offset (+13:00 NZDT / +12:00 NZST)
- So a UTC date folder does not match an NZ calendar day:
  in NZDT the folder switches at 13:00 NZ time (12:00 in NZST)
- Silver layer will store both trading_datetime_utc and trading_datetime_nz,
  and derive the NZ trading date from tradingDateTime, not from the folder name

## Bronze data check (2026-11-05)

Full read of all RTD files. Scope: 2026-11-01 00:20 UTC to 2026-11-04 22:30 UTC.
Before that, the container only holds 2 test files from 2026-10-19.

- Runs: 1,131, no gap over 6 min between runs, no empty files
- Nodes: 246 in every interval present; no off-grid intervals
- Records per run: min 492, median 3,444, max 4,428
- 5-min slots: 76 of 1,130 missing (6.7%), spread across the day
  - longest gap: 13 slots, 2026-11-03 22:20 to 23:20 UTC (2026-11-04 11:20 to 12:20 NZDT)
  - slots stayed missing in later overlapping runs, so the API did not return them
  - cause not confirmed: could be an upstream stall, or RTD not producing every 5-min
    interval; compare with Interim/Final prices or EMI data to find out
- Freshness (run time minus newest interval): usually under 10 min, peak 65 min
  - runs kept succeeding while data was stale, so a failure alert will not catch this;
    alert on freshness instead (e.g. newest interval older than 15 min)
  - at the end of the scan the newest interval was 25 min old
- Revisions: 1,905 of 259,284 (node, interval) keys (0.73%) had more than one price
  across runs
- Duplication: ~3.98M raw rows for ~259K unique keys (15.3x)

Implications for the silver layer:

- Do not assume a complete 5-min series; aggregates must handle missing slots
- De-duplicate to the latest version per key (by lastRunTime, then ingestedAt),
  not an arbitrary row

Not checked: Function logs and Application Insights.