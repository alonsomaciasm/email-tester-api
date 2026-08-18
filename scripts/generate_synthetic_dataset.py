"""Synthetic Test Dataset Generator for email-tester-api.

Generates a highly diverse 10,000 synthetic email test dataset covering the full spectrum of possibilities:
1. High-reputation clean domains (Gmail, Outlook, Yahoo, Proton)
2. Known disposable domains (Mailinator, 10MinuteMail, GuerrillaMail)
3. Domain typo variations (gmai.com, outlok.com, hotmial.com)
4. Non-existent MX / Null MX RFC 7508 domains
5. Internationalized / Homograph Punycode evasion attacks (xn--)
6. Suspicious keyword & risky TLD synthetic domains (.tk, .xyz, .top)
"""

import csv
import json
import os
import random

OUTPUT_JSON = "data/synthetic_test_emails.json"
OUTPUT_CSV = "data/synthetic_test_emails.csv"
TOTAL_SAMPLES = 10000

CLEAN_DOMAINS = [
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
    "yahoo.com", "ymail.com", "icloud.com", "protonmail.com",
    "proton.me", "zoho.com", "aol.com", "fastmail.com", "tutanota.com",
    "gmx.com", "mail.com", "posteo.de", "mailbox.org", "naver.com"
]

DISPOSABLE_DOMAINS = [
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "10minutemail.com",
    "yopmail.com", "dispostable.com", "maildrop.cc", "sharklasers.com",
    "getnada.com", "trashmail.com", "fakeinbox.com", "mohmal.com",
    "inboxkitten.com", "crazymailing.com", "throwawaymail.com"
]

TYPO_PATTERNS = [
    ("gmai.com", "gmail.com"),
    ("outlok.com", "outlook.com"),
    ("hotmial.com", "hotmail.com"),
    ("yaho.com", "yahoo.com"),
    ("icoud.com", "icloud.com"),
    ("portonmail.com", "protonmail.com"),
]

HOMOGRAPH_PUNYCODE_DOMAINS = [
    "xn--gm-yqa.com",  # gmaıl.com
    "xn--microsft-pza.com",
    "xn--yaho-pza.com",
]

NO_MX_SYNTHETIC_DOMAINS = [
    "domain-without-mx-records-synth.com",
    "null-mx-domain-rfc7508-synth.org",
    "non-existent-mail-server-991.net",
]

SUSPICIOUS_KEYWORD_DOMAINS = [
    "temp-disposable-mail-app.tk",
    "fake-trash-email-box.xyz",
    "random-burner-inbox-99.top",
    "disposable-temp-inbox-service.site",
]

PREFIXES = [
    "user", "admin", "contact", "info", "dev", "test", "sales", "support",
    "alex", "maria", "john", "carlos", "security", "team", "billing"
]


def generate_synthetic_dataset(num_samples: int = TOTAL_SAMPLES) -> list[dict]:
    dataset = []
    random.seed(42)  # Deterministic seed for scientific reproducibility

    weights = {
        "clean": 0.30,
        "disposable": 0.30,
        "typo": 0.15,
        "no_mx": 0.10,
        "homograph": 0.07,
        "suspicious_keyword": 0.08,
    }

    for i in range(num_samples):
        cat = random.choices(list(weights.keys()), weights=list(weights.values()))[0]
        prefix = f"{random.choice(PREFIXES)}_{i}_{random.randint(100, 999)}"

        if cat == "clean":
            dom = random.choice(CLEAN_DOMAINS)
            expected_disposable = False
            expected_risk_category = "clean"
        elif cat == "disposable":
            dom = random.choice(DISPOSABLE_DOMAINS)
            expected_disposable = True
            expected_risk_category = "known_provider"
        elif cat == "typo":
            typo_tuple = random.choice(TYPO_PATTERNS)
            dom = typo_tuple[0]
            expected_disposable = False
            expected_risk_category = "typo"
        elif cat == "no_mx":
            dom = random.choice(NO_MX_SYNTHETIC_DOMAINS)
            expected_disposable = True
            expected_risk_category = "no_mx"
        elif cat == "homograph":
            dom = random.choice(HOMOGRAPH_PUNYCODE_DOMAINS)
            expected_disposable = True
            expected_risk_category = "homograph_punycode"
        else:
            dom = random.choice(SUSPICIOUS_KEYWORD_DOMAINS)
            expected_disposable = True
            expected_risk_category = "suspicious_keyword"

        email = f"{prefix}@{dom}"
        dataset.append({
            "id": i + 1,
            "email": email,
            "domain": dom,
            "category": cat,
            "expected_disposable": expected_disposable,
            "expected_risk_category": expected_risk_category,
        })

    return dataset


def save_dataset(dataset: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)

    # Save JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    # Save CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "email", "domain", "category", "expected_disposable", "expected_risk_category"]
        )
        writer.writeheader()
        writer.writerows(dataset)

    print(f"✅ Generated {len(dataset)} synthetic email samples.")
    print(f"📄 Saved JSON: {OUTPUT_JSON}")
    print(f"📄 Saved CSV:  {OUTPUT_CSV}")


if __name__ == "__main__":
    ds = generate_synthetic_dataset()
    save_dataset(ds)
