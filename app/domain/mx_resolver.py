import ipaddress
import time
from typing import cast

import dns.asyncresolver
import dns.exception
import dns.resolver
from aiobreaker import CircuitBreaker

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import DNS_MX_QUERIES

logger = get_logger(__name__)

# Circuit breaker opens if 5 consecutive DNS failures occur, resets after 30 seconds
dns_circuit_breaker = CircuitBreaker(fail_max=5, timeout_duration=30)

PRIVATE_IP_SUBNETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.169.254/32"),  # AWS Metadata Endpoint
    ipaddress.ip_network("::1/128"),
]

KNOWN_MX_PROVIDERS = [
    ("google", "Google Workspace"),
    ("googlemail", "Google Workspace"),
    ("outlook.com", "Microsoft 365"),
    ("protection.outlook.com", "Microsoft 365"),
    ("protonmail", "ProtonMail"),
    ("proton.ch", "ProtonMail"),
    ("icloud.com", "iCloud Mail"),
    ("mail.me.com", "iCloud Mail"),
    ("zoho", "Zoho Mail"),
    ("secureserver.net", "GoDaddy Mail"),
    ("fastmail", "Fastmail"),
    ("qq.com", "Tencent QQ Mail"),
    ("mailgun", "Mailgun Gateway"),
    ("sendgrid", "SendGrid Gateway"),
]


def is_private_ip(ip_str: str) -> bool:
    """Checks if an IP address belongs to loopback, private RFC 1918, or metadata ranges."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except ValueError:
        return False


def is_null_mx(mx_records: list[str]) -> bool:
    """Checks if domain has explicit Null MX record (RFC 7508) indicating no email accepted."""
    if not mx_records:
        return False
    for mx in mx_records:
        if mx in ("", ".", "0 ."):
            return True
    return False


def identify_mx_provider(mx_records: list[str]) -> str | None:
    """Identifies the infrastructure provider from MX records."""
    if is_null_mx(mx_records):
        return "Null MX (RFC 7508)"

    if not mx_records:
        return None

    for mx in mx_records:
        mx_lower = mx.lower()
        for keyword, provider_name in KNOWN_MX_PROVIDERS:
            if keyword in mx_lower:
                return provider_name

    return "Custom MX"


class AsyncMXResolver:
    """Async DNS MX record resolver with L1 in-memory cache, SSRF protection, and Circuit Breaker."""

    def __init__(self) -> None:
        self.resolver = dns.asyncresolver.Resolver()
        self.resolver.nameservers = settings.DNS_NAMESERVERS
        self.resolver.timeout = settings.DNS_RESOLVER_TIMEOUT
        self.resolver.lifetime = settings.DNS_RESOLVER_LIFETIME
        # L1 in-memory cache: {domain: (mx_records, expire_time)}
        self._l1_cache: dict[str, tuple[list[str], float]] = {}

    async def resolve_mx(self, domain: str) -> list[str]:
        """Resolves MX records for a domain asynchronously.

        Returns list of MX exchanger domain names.
        Uses L1 in-memory cache with 300s TTL.
        """
        # 1. Check L1 in-memory cache
        now = time.monotonic()
        if domain in self._l1_cache:
            records, expire_at = self._l1_cache[domain]
            if now < expire_at:
                return records

        try:
            # Wrap execution with circuit breaker
            res = await dns_circuit_breaker.call(self._query_dns, domain)
            mx_records: list[str] = cast(list[str], res)
            DNS_MX_QUERIES.labels(result="success" if mx_records else "no_records").inc()

            # Store in L1 cache for 300 seconds
            self._l1_cache[domain] = (mx_records, now + 300)
            return mx_records
        except dns.resolver.NoAnswer:
            DNS_MX_QUERIES.labels(result="no_records").inc()
            self._l1_cache[domain] = ([], now + 300)
            return []
        except dns.resolver.NXDOMAIN:
            DNS_MX_QUERIES.labels(result="no_records").inc()
            self._l1_cache[domain] = ([], now + 300)
            return []
        except dns.exception.Timeout:
            DNS_MX_QUERIES.labels(result="timeout").inc()
            logger.warning("DNS resolution timeout", domain=domain)
            return []
        except Exception as e:
            DNS_MX_QUERIES.labels(result="error").inc()
            logger.warning("DNS resolution error", domain=domain, error=str(e))
            return []

    async def _query_dns(self, domain: str) -> list[str]:
        answers = await self.resolver.resolve(domain, "MX")
        mx_list: list[str] = []
        for rdata in answers:
            exchange = str(rdata.exchange).rstrip(".").lower()
            # Handle Null MX (RFC 7508)
            if exchange == "." or exchange == "":
                mx_list.append(".")
                continue
            if exchange:
                # SSRF Protection: Ensure exchange does not resolve to private IP range
                if is_private_ip(exchange):
                    logger.warning("SSRF block: MX exchanger resolves to private IP", domain=domain, mx=exchange)
                    continue
                mx_list.append(exchange)
        return mx_list


async_mx_resolver = AsyncMXResolver()
