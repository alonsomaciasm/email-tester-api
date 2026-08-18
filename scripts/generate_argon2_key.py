#!/usr/bin/env python3
"""Argon2id Key Hash Generator Utility.

Generates secure Argon2id password/API key hashes for production .env configuration.
Usage:
    python scripts/generate_argon2_key.py [my-secret-key]
"""

import sys

from argon2 import PasswordHasher

ph = PasswordHasher()


def main() -> None:
    if len(sys.argv) > 1:
        raw_key = sys.argv[1]
    else:
        raw_key = input("Enter API key to hash with Argon2id: ").strip()

    if not raw_key:
        print("Error: API Key cannot be empty.")
        sys.exit(1)

    hashed = ph.hash(raw_key)
    print("\n=======================================================")
    print("🔒 Argon2id Hashed API Key:")
    print(hashed)
    print("=======================================================")
    print("\nCopy and paste this hash into your .env file:")
    print(f'ALLOWED_API_KEYS=["{hashed}"]\n')


if __name__ == "__main__":
    main()
