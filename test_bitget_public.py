import requests

url = "https://api.bitget.com/api/v2/mix/market/ticker"

params = {
    "symbol": "BTCUSDT",
    "productType": "USDT-FUTURES"
}

response = requests.get(url, params=params, timeout=10)
data = response.json()

print(data)
