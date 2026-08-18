import argparse
import asyncio
import json
import time

import httpx


async def run_worker(
    client: httpx.AsyncClient,
    url: str,
    emails: list[str],
    results: list[float],
) -> None:
    for email in emails:
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, json={"email": email})
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                results.append(elapsed_ms)
        except Exception:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="Empirical benchmark runner for Disposable Email API")
    parser.add_argument("--url", default="http://localhost:8000/v1/verify-email", help="Target API endpoint")
    parser.add_argument("--requests", type=int, default=500, help="Total requests to execute")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent async workers")
    args = parser.parse_args()

    sample_emails = [
        "user1@mailinator.com",
        "user2@guerrillamail.com",
        "user3@gmail.com",
        "user4@tempmail.com",
        "user5@yahoo.com",
    ] * (args.requests // 5 + 1)
    sample_emails = sample_emails[: args.requests]

    chunk_size = len(sample_emails) // args.concurrency
    chunks = [sample_emails[i : i + chunk_size] for i in range(0, len(sample_emails), chunk_size)]

    results: list[float] = []
    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [run_worker(client, args.url, chunk, results) for chunk in chunks]
        await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time
    if not results:
        print("Error: No successful requests recorded.")
        return

    results.sort()
    n = len(results)
    p50 = results[int(n * 0.50)]
    p90 = results[int(n * 0.90)]
    p99 = results[int(n * 0.99)]
    rps = n / total_time

    summary = {
        "total_requests": n,
        "concurrency": args.concurrency,
        "total_duration_sec": round(total_time, 3),
        "throughput_rps": round(rps, 2),
        "p50_latency_ms": round(p50, 3),
        "p90_latency_ms": round(p90, 3),
        "p99_latency_ms": round(p99, 3),
        "min_latency_ms": round(results[0], 3),
        "max_latency_ms": round(results[-1], 3),
    }

    print("\n--- EMPIRICAL BENCHMARK RESULTS ---")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
