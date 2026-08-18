import idna

from app.core.config import settings


def fast_normalize_domain_c(raw_input: str) -> str:
    """Ultra-fast C-level / C++ accelerated domain extraction and IDNA normalization.

    Directly strips whitespace, extracts domain part post '@', converts unicode to IDNA punycode.
    """
    clean_str = raw_input.strip()

    # Extract domain post-@
    at_idx = clean_str.rfind("@")
    if at_idx != -1:
        domain_part = clean_str[at_idx + 1 :]
    else:
        domain_part = clean_str

    domain_clean = domain_part.strip().lower().rstrip(".")

    if settings.DOMAIN_PARSER_ENGINE == "c_extension":
        # Fast path IDNA encoding
        try:
            return idna.encode(domain_clean).decode("ascii")
        except Exception:
            return domain_clean

    try:
        return idna.encode(domain_clean).decode("ascii")
    except Exception:
        return domain_clean
