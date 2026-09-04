import re


def parse_uber_receipt(data: str) -> dict:
    """Parse an Uber receipt body into structured fields.

    Handles both layouts Uber sends:
      * Brazilian-Portuguese — "Informações da viagem", "Você viajou com",
        "Quilômetros", amounts like "R$ 13,85" (comma decimal separator).
      * English — "Trip details", "You rode with", "kilometers", amounts
        like "R$11.72" (dot decimal separator).
    Each field is matched with the PT pattern first and falls back to EN.
    Note both variants currently bill in BRL (R$), so the total stays in
    ``total_brl``; the difference is only the decimal separator.
    """

    def first(*patterns, group=1, flags=0):
        for pattern in patterns:
            m = re.search(pattern, data, flags)
            if m:
                return m.group(group).strip()
        return None

    date = first(
        r"(\d{1,2} de [a-zA-Zç]{3}\.? de \d{4})",   # PT: 10 de jun. de 2026
        r"([A-Z][a-z]{2,8} \d{1,2}, \d{4})",        # EN: Jun 26, 2026
    )
    total = first(
        r"Total\s+R\$\s*([\d.]+,\d{2})",            # PT: Total R$ 13,85
        r"Total\s+R\$\s*([\d,]+\.\d{2})",           # EN: Total R$11.72
    )
    product = first(
        r"Informações da viagem\s+(.+?)\s+[\d.,]+\s*Quil",
        r"Trip details\s+(.+?)\s+[\d.,]+\s*(?:kilometers?|miles?)",
    )
    distance = first(
        r"([\d.,]+)\s*Quil[oô]metros",
        r"([\d.,]+)\s*(?:kilometers?|miles?)",
    )
    duration = first(
        r"Quil[oô]metros,\s*(\d+)\s*min",
        r"(?:kilometers?|miles?),?\s*(\d+)\s*min",
    )

    # Scope address search to the trip block to avoid stray payment timestamps.
    trip_section = data
    for marker in ("Informações da viagem", "Trip details"):
        if marker in data:
            trip_section = data.split(marker)[-1]
            break
    # Times are "5:46" (PT) or "5:44 AM" (EN); addresses end in a CEP/ZIP.
    pairs = re.findall(
        r"(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s+(.+?\d{5}(?:-\d{3,4})?)", trip_section
    )
    pickup  = pairs[0] if len(pairs) > 0 else (None, None)
    dropoff = pairs[1] if len(pairs) > 1 else (None, None)

    driver = first(
        r"Você viajou com\s+(.+?)\s+\d\.\d{2}",
        r"You rode with\s+(.+?)\s+\d\.\d{2}",
    )
    rating = first(
        r"Você viajou com\s+.+?\s+(\d\.\d{2})",
        r"You rode with\s+.+?\s+(\d\.\d{2})",
    )

    last4 = first(r"••••\s*(\d{4})")
    card  = first(r"([A-Za-zÀ-ÿ]+(?: [A-Za-zÀ-ÿ]+)?)\s*••••")

    return {
        "date": date,
        "total_brl": total,
        "product": product,
        "distance_km": distance,
        "duration_min": duration,
        "time_start": pickup[0],
        "from_address": pickup[1],
        "time_end": dropoff[0],
        "to_address": dropoff[1],
        "driver": driver,
        "driver_rating": rating,
        "card": card,
        "card_last4": last4,
    }


def total_as_float(parsed: dict) -> float | None:
    """Convert the receipt total to a float, handling both the BR
    ('1.234,56') and English ('1,234.56' / '11.72') number formats."""
    t = parsed.get("total_brl")
    if not t:
        return None
    if t.rfind(",") > t.rfind("."):
        # comma is the decimal separator (BR): 1.234,56 -> 1234.56
        return float(t.replace(".", "").replace(",", "."))
    # dot is the decimal separator (EN): 1,234.56 -> 1234.56
    return float(t.replace(",", ""))


if __name__ == "__main__":
    import sys, json
    body = sys.stdin.read()
    print(json.dumps(parse_uber_receipt(body), ensure_ascii=False, indent=2))
