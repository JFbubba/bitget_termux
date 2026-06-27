import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.bitget.com"
REQUEST_PATH = "/api/v2/mix/account/accounts"
PRODUCT_TYPE = "USDT-FUTURES"


def load_keys():
    load_dotenv()

    api_key = os.getenv("BITGET_API_KEY")
    api_secret = os.getenv("BITGET_API_SECRET")
    passphrase = os.getenv("BITGET_API_PASSPHRASE")

    if not api_key or not api_secret or not passphrase:
        raise RuntimeError("Clés API manquantes dans .env")

    return api_key, api_secret, passphrase


def create_signature(secret_key, timestamp, method, request_path, query_string="", body=""):
    if query_string:
        message = f"{timestamp}{method.upper()}{request_path}?{query_string}{body}"
    else:
        message = f"{timestamp}{method.upper()}{request_path}{body}"

    mac = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    )

    return base64.b64encode(mac.digest()).decode("utf-8")


def get_futures_accounts():
    api_key, api_secret, passphrase = load_keys()

    method = "GET"
    params = {
        "productType": PRODUCT_TYPE,
    }

    query_string = urlencode(params)
    timestamp = str(int(time.time() * 1000))

    signature = create_signature(
        secret_key=api_secret,
        timestamp=timestamp,
        method=method,
        request_path=REQUEST_PATH,
        query_string=query_string,
        body="",
    )

    headers = {
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
        "locale": "en-US",
    }

    url = f"{BASE_URL}{REQUEST_PATH}"

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


def get_spot_assets(coin=None):
    """Avoirs SPOT par coin (available / frozen). Lecture seule (GET signé)."""
    api_key, api_secret, passphrase = load_keys()

    method = "GET"
    request_path = "/api/v2/spot/account/assets"
    params = {"coin": coin} if coin else {}
    query_string = urlencode(params)
    timestamp = str(int(time.time() * 1000))

    signature = create_signature(
        secret_key=api_secret,
        timestamp=timestamp,
        method=method,
        request_path=request_path,
        query_string=query_string,
        body="",
    )

    headers = {
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
        "locale": "en-US",
    }

    response = requests.get(
        f"{BASE_URL}{request_path}",
        headers=headers,
        params=params,
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


def main():
    print("=== BITGET BALANCE READER ===")
    print("Mode: lecture seule")
    print("Aucun ordre envoyé")
    print()

    result = get_futures_accounts()

    if result.get("code") != "00000":
        print("Erreur Bitget:")
        print(result)
        return

    accounts = result.get("data", [])

    if not accounts:
        print("Aucun compte futures trouvé.")
        return

    for account in accounts:
        margin_coin = account.get("marginCoin", "N/A")
        available = account.get("available", "N/A")
        account_equity = account.get("accountEquity", "N/A")
        usdt_equity = account.get("usdtEquity", "N/A")
        unrealized_pl = account.get("unrealizedPL", "N/A")
        crossed_risk_rate = account.get("crossedRiskRate", "N/A")

        print(f"Compte: {PRODUCT_TYPE} / {margin_coin}")
        print(f"Disponible: {available}")
        print(f"Equity compte: {account_equity}")
        print(f"Equity USDT: {usdt_equity}")
        print(f"PnL non réalisé: {unrealized_pl}")
        print(f"Risk rate cross: {crossed_risk_rate}")


if __name__ == "__main__":
    main()
