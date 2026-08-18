import os
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment Stage & Service Metadata
    ENVIRONMENT: str = Field(default="production", description="Environment stage (development, staging, production)")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    LOG_LEVEL: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    SERVICE_NAME: str = Field(default="email-tester-api", description="Service identifier")
    SECRET_SALT: str = Field(
        default_factory=lambda: os.urandom(32).hex(),
        description="Daily rotating secret salt for zero-PII rate limiting",
    )

    # Global High-Performance Preset Shortcut
    PERFORMANCE_PRESET: Literal["ultra_combined", "baseline_python", "custom"] = Field(
        default="ultra_combined",
        description="Global performance preset (ultra_combined: all C/Rust/L1 optimizations combined, baseline_python: pure Python, custom: individual flags)",
    )

    # High-Performance Engine Feature Flags
    JSON_SERIALIZER_ENGINE: Literal["orjson", "msgpack", "std_json"] = Field(
        default="orjson",
        description="Serializer backend (orjson for Rust-backed JSON, msgpack for binary serialization, std_json for standard python json)",
    )
    TYPO_ENGINE_BACKEND: Literal["rapidfuzz", "python_native"] = Field(
        default="rapidfuzz",
        description="Typo distance backend (rapidfuzz for C++ accelerated Levenshtein, python_native for pure Python)",
    )
    REDIS_PARSER: Literal["hiredis", "python"] = Field(
        default="hiredis",
        description="Redis protocol parser (hiredis for C-extension parser, python for pure Python parser)",
    )
    BLOOM_OR_CUCKOO_ENGINE: Literal["bloom", "cuckoo"] = Field(
        default="bloom",
        description="Probabilistic filter engine (bloom for standard Bloom filter, cuckoo for 20% lower RAM and dynamic deletion support)",
    )
    DOMAIN_PARSER_ENGINE: Literal["c_extension", "python_native"] = Field(
        default="c_extension",
        description="Domain parser engine (c_extension for C-level fast domain extraction, python_native for pure Python parsing)",
    )

    @model_validator(mode="after")
    def apply_performance_preset(self) -> "Settings":
        """Enforces preset shortcuts if PERFORMANCE_PRESET is specified."""
        if self.PERFORMANCE_PRESET == "ultra_combined":
            self.JSON_SERIALIZER_ENGINE = "orjson"
            self.TYPO_ENGINE_BACKEND = "rapidfuzz"
            self.REDIS_PARSER = "hiredis"
            self.BLOOM_OR_CUCKOO_ENGINE = "cuckoo"
            self.DOMAIN_PARSER_ENGINE = "c_extension"
        elif self.PERFORMANCE_PRESET == "baseline_python":
            self.JSON_SERIALIZER_ENGINE = "std_json"
            self.TYPO_ENGINE_BACKEND = "python_native"
            self.REDIS_PARSER = "python"
            self.BLOOM_OR_CUCKOO_ENGINE = "bloom"
            self.DOMAIN_PARSER_ENGINE = "python_native"
        return self

    # Redis Configuration
    REDIS_HOST: str = Field(default="redis", description="Redis hostname")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database index")
    REDIS_PASSWORD: str | None = Field(default=None, description="Redis password")
    REDIS_MAX_CONNECTIONS: int = Field(default=20, description="Max connections in pool")
    REDIS_CACHE_TTL_MX_SECONDS: int = Field(default=86400, description="TTL for MX DNS cache in Redis (24 hours)")

    # Security & Auth
    API_KEY_HEADER_NAME: str = Field(default="X-API-Key", description="Header name for API key authentication")
    ALLOWED_API_KEYS: list[str] = Field(
        default=["secret-api-key-change-me-in-production"],
        description="List of valid API Keys or Argon2id hashes",
    )
    REQUIRE_API_KEY: bool = Field(default=False, description="Enforce API key validation")

    # Rate Limiting & Whitelisting
    RATE_LIMIT_IP_REQUESTS: int = Field(default=100, description="Max requests per window per IP")
    RATE_LIMIT_APIKEY_REQUESTS: int = Field(default=1000, description="Max requests per window per API Key")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, description="Sliding window size in seconds")
    WHITELISTED_DOMAINS: list[str] = Field(
        default=["gmail.com", "outlook.com", "yahoo.com", "hotmial.com", "icloud.com"],
        description="Explicit domain whitelist to override any disposable checks",
    )
    WHITELIST_FILE_PATH: str = Field(
        default="config/whitelist.txt",
        description="Optional local text file path containing one whitelisted domain per line",
    )

    # DNS Resolver Settings
    DNS_RESOLVER_TIMEOUT: float = Field(default=1.5, description="Timeout in seconds for DNS queries")
    DNS_RESOLVER_LIFETIME: float = Field(default=2.0, description="Lifetime in seconds for DNS query retry")
    DNS_NAMESERVERS: list[str] = Field(
        default=["127.0.0.1", "1.1.1.1", "8.8.8.8"],
        description="Custom upstream DNS resolvers (prioritizes 127.0.0.1 local resolver daemon)",
    )

    # Bloom / Cuckoo Filter Dataset Settings
    BLOOM_FILTER_EXPECTED_ITEMS: int = Field(default=500000, description="Capacity N for Bloom/Cuckoo filter")
    BLOOM_FILTER_ERROR_RATE: float = Field(default=0.001, description="Target false-positive rate P")
    DATASET_SOURCE_URLS: list[str] = Field(
        default=[
            "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf",
            "https://raw.githubusercontent.com/ivolo/disposable-email-domains/master/index.json",
        ],
        description="Public raw URLs to fetch open-source disposable email domain blocklists",
    )


settings = Settings()
