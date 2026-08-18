from prometheus_client import Counter, Gauge, Histogram

# Verification metrics
VERIFICATION_REQUESTS_TOTAL = Counter(
    "email_verifier_requests_total",
    "Total email verification requests processed",
    ["disposable", "confidence", "reason"],
)

VERIFICATION_LATENCY_SECONDS = Histogram(
    "email_verifier_latency_seconds",
    "Verification response time in seconds per pipeline tier",
    ["tier"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0),
)

# Pipeline Tier Hits/Misses
BLOOM_FILTER_LOOKUPS = Counter(
    "email_verifier_bloom_lookups_total",
    "Bloom filter lookup outcomes",
    ["result"],  # hit, miss
)

REDIS_CACHE_LOOKUPS = Counter(
    "email_verifier_redis_lookups_total",
    "Redis MX cache lookup outcomes",
    ["result"],  # hit, miss, error
)

DNS_MX_QUERIES = Counter(
    "email_verifier_dns_queries_total",
    "Async DNS MX query outcomes",
    ["result"],  # success, no_records, timeout, error, circuit_open
)

# System Health & Dataset Metrics
BLOOM_FILTER_ITEMS = Gauge(
    "email_verifier_bloom_filter_items",
    "Current number of elements indexed in the Bloom filter",
)

BLOOM_FILTER_MEMORY_BYTES = Gauge(
    "email_verifier_bloom_filter_memory_bytes",
    "Estimated memory usage of the Bloom filter in bytes",
)

REDIS_HEALTH_STATUS = Gauge(
    "email_verifier_redis_connected",
    "Redis connectivity status (1 = connected, 0 = disconnected)",
)
