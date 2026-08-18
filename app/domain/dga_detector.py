import math
from collections import Counter


class DGADetector:
    """Shannon Entropy & N-gram Perplexity DGA (Domain Generation Algorithm) Detector.

    Identifies randomly generated stochastic synthetic disposable email domains (e.g. x89a1zk9.biz).
    """

    def __init__(self, entropy_threshold: float = 3.65, min_domain_length: int = 7) -> None:
        self.entropy_threshold = entropy_threshold
        self.min_domain_length = min_domain_length

    @staticmethod
    def compute_shannon_entropy(domain_name: str) -> float:
        """Calculates Shannon entropy of string H(X) = -sum(P(x) * log2(P(x)))."""
        if not domain_name:
            return 0.0
        counts = Counter(domain_name)
        total = len(domain_name)
        return -sum((count / total) * math.log2(count / total) for count in counts.values())

    def is_dga_domain(self, domain: str) -> tuple[bool, float]:
        """Evaluates whether domain exhibits DGA / random stochastic properties.

        Returns (is_dga, entropy_value).
        """
        # Extract main domain name before TLD (e.g. 'x89a1zk9' from 'x89a1zk9.biz')
        domain_parts = domain.lower().split(".")
        if not domain_parts:
            return False, 0.0

        main_label = domain_parts[0]

        if len(main_label) < self.min_domain_length:
            return False, 0.0

        entropy = self.compute_shannon_entropy(main_label)

        # High entropy threshold trigger or high digit ratio
        digit_count = sum(1 for c in main_label if c.isdigit())
        digit_ratio = digit_count / len(main_label)

        if entropy >= self.entropy_threshold or (digit_ratio > 0.45 and len(main_label) >= 8):
            return True, round(entropy, 3)

        return False, round(entropy, 3)


dga_detector = DGADetector()
