import rapidfuzz.distance.Levenshtein

from app.core.config import settings

SUSPICIOUS_DOMAIN_KEYWORDS = [
    "temp",
    "trash",
    "fake",
    "disposable",
    "throwaway",
    "10min",
    "guerrilla",
    "sharklasers",
    "mailnesia",
    "dispostable",
    "getnada",
    "yopmail",
    "maildrop",
    "inboxkitten",
    "crazymailing",
    "mohmal",
    "tempmail",
]

KNOWN_DISPOSABLE_MX_SUFFIXES = [
    "mailinator.com",
    "guerrillamail.com",
    "temp-mail.org",
    "yopmail.com",
    "dispostable.com",
    "maildrop.cc",
    "sharklasers.com",
    "getnada.com",
]

POPULAR_DOMAINS = [
    "gmail.com",
    "hotmail.com",
    "yahoo.com",
    "outlook.com",
    "icloud.com",
    "live.com",
    "protonmail.com",
    "proton.me",
    "aol.com",
    "zoho.com",
    "gmx.com",
]


def levenshtein_distance_python_native(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings s1 and s2 using pure Python."""
    if len(s1) < len(s2):
        return levenshtein_distance_python_native(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def compute_levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein distance using either RapidFuzz (C++) or pure Python based on TYPO_ENGINE_BACKEND."""
    if settings.TYPO_ENGINE_BACKEND == "rapidfuzz":
        return int(rapidfuzz.distance.Levenshtein.distance(s1, s2))
    return levenshtein_distance_python_native(s1, s2)


class HeuristicsEngine:
    """Secondary heuristics analyzer for detecting disposable email traits, typos, and risk scoring."""

    def evaluate_domain(self, domain: str, mx_records: list[str]) -> tuple[bool, str]:
        """Evaluates domain and its MX records against heuristics.

        Returns (is_disposable, reason_detail).
        """
        normalized_domain = domain.lower()

        # 1. Homograph / Punycode check
        if normalized_domain.startswith("xn--"):
            return True, "punycode_homograph"

        # 2. Domain keyword heuristics
        for keyword in SUSPICIOUS_DOMAIN_KEYWORDS:
            if keyword in normalized_domain:
                return True, "heuristic_keyword"

        # 3. DGA / High Shannon Entropy check
        from app.domain.dga_detector import dga_detector
        is_dga, entropy_val = dga_detector.is_dga_domain(normalized_domain)
        if is_dga:
            return True, "heuristic_dga"

        # 4. Known disposable MX host check
        for mx in mx_records:
            mx_lower = mx.lower()
            for suffix in KNOWN_DISPOSABLE_MX_SUFFIXES:
                if mx_lower.endswith(suffix):
                    return True, "disposable_mx_target"

        return False, "clean"

    def detect_typo(self, domain: str) -> str | None:
        """Detects possible domain typo against popular legitimate providers."""
        norm = domain.lower()
        if norm in POPULAR_DOMAINS:
            return None

        for target in POPULAR_DOMAINS:
            dist = compute_levenshtein_distance(norm, target)
            # Match if 1 edit difference, or 2 edits if length > 7
            if dist == 1 or (dist == 2 and len(norm) >= 8 and norm[:3] == target[:3]):
                return target
        return None

    def compute_risk_score(
        self,
        disposable: bool,
        reason: str,
        confidence: str,
        mx_provider: str | None = None,
        did_you_mean: str | None = None,
    ) -> int:
        """Calculates a risk score from 0 (very safe) to 100 (disposable/malicious)."""
        if disposable:
            if reason == "known_provider":
                return 100
            if reason == "disposable_mx_target":
                return 95
            if reason in ("heuristic_keyword", "heuristic_dga", "punycode_homograph"):
                return 90
            return 85

        if reason == "no_mx":
            return 80  # Cannot receive email

        if did_you_mean is not None:
            return 60  # High probability of typo / non-existent inbox

        if mx_provider in ("Google Workspace", "Microsoft 365", "ProtonMail", "iCloud Mail"):
            return 0  # Reputable enterprise provider

        return 10  # Clean / unknown custom domain


heuristics_engine = HeuristicsEngine()
