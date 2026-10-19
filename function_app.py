"""
Azure Function: ingest NZ wholesale electricity prices from the WITS
Market Prices API into the data lake (bronze layer).

Runs every 5 minutes. Each run:
  1. exchanges client credentials for an OAuth2 access token
  2. pulls the latest prices for each configured schedule (all nodes, paginated)
  3. writes the untouched response as gzipped JSON to
     <container>/wits/<schedule>/date=YYYY-MM-DD/<schedule>_<UTC timestamp>.json.gz

The `back` window overlaps consecutive runs on purpose, so a late or failed run
loses nothing; duplicates are removed later in the silver layer.
"""

import gzip
import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func
import requests
from azure.storage.blob import BlobServiceClient, ContentSettings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_HOST = "https://api.electricityinfo.co.nz"
TOKEN_URL = f"{API_HOST}/login/oauth2/token"
BASE_URL = f"{API_HOST}/api/market-prices/v1"
PAGE_SIZE = 10_000  # API maximum per request

app = func.FunctionApp()


def _session() -> requests.Session:
    """HTTP session that retries transient failures (429/5xx) with backoff."""
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def get_access_token(session: requests.Session) -> str:
    resp = session.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(os.environ["WITS_CLIENT_ID"], os.environ["WITS_CLIENT_SECRET"]),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_schedule_prices(session, token, schedule, market_type, back) -> list:
    """Fetch all pages of prices for one schedule."""
    headers = {"Authorization": f"Bearer {token}"}
    prices, offset = [], 0
    while True:
        params = {"marketType": market_type, "back": back, "offset": offset}
        resp = session.get(
            f"{BASE_URL}/schedules/{schedule}/prices",
            headers=headers,
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json().get("prices", [])
        prices.extend(batch)
        if len(batch) < PAGE_SIZE:
            return prices
        offset += PAGE_SIZE


def write_to_lake(records: list, schedule: str, market_type: str, run_at: datetime) -> str:
    """Write one run's raw records as gzipped JSON, partitioned by UTC date."""
    container = os.environ.get("LAKE_CONTAINER", "bronze")
    blob_path = (
        f"wits/{schedule.lower()}/date={run_at:%Y-%m-%d}/"
        f"{schedule.lower()}_{market_type}_{run_at:%Y%m%dT%H%M%SZ}.json.gz"
    )
    payload = {
        "source": "WITS Market Prices API",
        "schedule": schedule,
        "marketType": market_type,
        "ingestedAt": run_at.isoformat(),
        "recordCount": len(records),
        "prices": records,
    }
    body = gzip.compress(json.dumps(payload).encode("utf-8"))

    service = BlobServiceClient.from_connection_string(os.environ["LAKE_CONNECTION_STRING"])
    service.get_blob_client(container, blob_path).upload_blob(
        body,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json", content_encoding="gzip"),
    )
    return f"{container}/{blob_path}"


@app.timer_trigger(
    schedule="0 */5 * * * *",  # NCRONTAB: second minute hour day month weekday
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def ingest_wits_prices(timer: func.TimerRequest) -> None:
    run_at = datetime.now(timezone.utc)
    schedules = [s.strip().upper() for s in os.environ.get("WITS_SCHEDULES", "RTD").split(",")]
    market_type = os.environ.get("WITS_MARKET_TYPE", "E")
    back = int(os.environ.get("WITS_BACK_PERIODS", "2"))

    if timer.past_due:
        logging.warning("Timer is past due; running now")

    session = _session()
    token = get_access_token(session)

    for schedule in schedules:
        records = fetch_schedule_prices(session, token, schedule, market_type, back)
        path = write_to_lake(records, schedule, market_type, run_at)
        logging.info("Wrote %d %s records to %s", len(records), schedule, path)
