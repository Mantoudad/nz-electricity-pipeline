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
  - project focuses on E; R kept in bronze for completeness
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