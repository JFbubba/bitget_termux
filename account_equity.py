from bitget_balance_reader import get_futures_accounts


from config import DEFAULT_PAPER_EQUITY_USDT


def get_account_equity_usdt():
    try:
        result = get_futures_accounts()

        if result.get("code") != "00000":
            return DEFAULT_PAPER_EQUITY_USDT, "PAPER_FALLBACK_API_ERROR"

        accounts = result.get("data", [])

        for account in accounts:
            if account.get("marginCoin") == "USDT":
                equity = float(account.get("usdtEquity") or account.get("accountEquity") or 0)

                if equity > 0:
                    return equity, "REAL_BITGET_EQUITY"

        return DEFAULT_PAPER_EQUITY_USDT, "PAPER_FALLBACK_ZERO_BALANCE"

    except Exception:
        return DEFAULT_PAPER_EQUITY_USDT, "PAPER_FALLBACK_EXCEPTION"


if __name__ == "__main__":
    equity, source = get_account_equity_usdt()

    print("=== ACCOUNT EQUITY ===")
    print(f"Equity utilisée: {equity} USDT")
    print(f"Source: {source}")
