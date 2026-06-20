from dotenv import load_dotenv
import os


load_dotenv()

required_vars = [
    "BITGET_API_KEY",
    "BITGET_API_SECRET",
    "BITGET_API_PASSPHRASE",
]

print("=== CHECK ENV ===")

all_ok = True

for var in required_vars:
    value = os.getenv(var)

    if value:
        print(f"{var}: OK ({len(value)} caractères)")
    else:
        print(f"{var}: MANQUANT")
        all_ok = False

print()

if all_ok:
    print("Résultat: .env chargé correctement")
else:
    print("Résultat: .env incomplet")
