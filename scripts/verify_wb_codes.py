import requests

INDICATORS = [
    "SH.DTH.MCLN",
    "SH.DTH.DEAT",
    "SH.XPD.CHEX.GD.ZS",
    "SH.POP.LIFE",
    "SH.MED.PHYS",
    "SH.SMR.MAL",
    "SH.XPD.HSTK",
    "SH.AIR.POLL",
    "SH.STA.BIRTH",
    "SH.SMR.TBC",
]

def verify():
    print(f"{'Code':<20} | {'Status':<10} | {'API Name'}")
    print("-" * 50)
    for code in INDICATORS:
        url = f"https://api.worldbank.org/v2/indicator/{code}?format=json"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1 and data[1]:
                    name = data[1][0].get("name", "N/A")
                    print(f"{code:<20} | VALID      | {name}")
                else:
                    print(f"{code:<20} | EMPTY      | N/A")
            else:
                print(f"{code:<20} | {response.status_code:<10} | N/A")
        except Exception as e:
            print(f"{code:<20} | ERROR      | {e}")

if __name__ == "__main__":
    verify()
