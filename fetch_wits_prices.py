"""
Fetch NZ wholesale electricity prices from the WITS Market Prices API
and save the raw JSON response locally (future "bronze" layer).

Auth: OAuth 2.0 client credentials (Client ID + Secret -> Bearer token)
Usage:
    python fetch_wits_prices.py                 # list available schedules
    python fetch_wits_prices.py RTP             # real-time dispatch prices
    python fetch_wits_prices.py RTP BEN2201,OTA2201
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

API_HOST = "https://api.electricityinfo.co.nz"
TOKEN_URL = f"{API_HOST}/login/oauth2/token"
BASE_URL = f"{API_HOST}/api/market-prices/v1"
RAW_DIR = Path("data/raw/wits")


def get_access_token(client_id: str, client_secret: str) -> str:
    """Exchange client credentials for a short-lived access token."""
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),  # HTTP Basic auth
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def api_get(path: str, token: str, params: dict | None = None):
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if not resp.ok:
        print(f"Request failed ({resp.status_code}): {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json()


def save_raw(data, name: str) -> Path:
    """Save the untouched API response, partitioned by UTC date."""
    now = datetime.now(timezone.utc)
    out_dir = RAW_DIR / name / f"date={now:%Y-%m-%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}_{now:%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    load_dotenv()
    client_id = os.getenv("WITS_CLIENT_ID")
    client_secret = os.getenv("WITS_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Missing WITS_CLIENT_ID / WITS_CLIENT_SECRET in .env")

    token = get_access_token(client_id, client_secret)
    print("Got access token")

    if len(sys.argv) == 1:
        schedules = api_get("/schedules", token)
        print(json.dumps(schedules, indent=2)[:2000])
        return

    schedule = sys.argv[1].upper()
    nodes = sys.argv[2] if len(sys.argv) > 2 else "BEN2201,OTA2201"
    params = {"marketType": "E", "nodes": nodes, "back": 1}

    data = api_get(f"/schedules/{schedule}/prices", token, params)
    path = save_raw(data, schedule.lower())
    print(f"Saved -> {path}")
    print(json.dumps(data, indent=2)[:1500])


if __name__ == "__main__":
    main()
