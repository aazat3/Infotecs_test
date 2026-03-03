import argparse
import asyncio
import httpx
import re
import sys
import time
from statistics import mean


URL_REGEX = re.compile(r"^https://[a-zA-Z0-9.-]+(:\d+)?(/.*)?$")


def validate_url(url: str) -> bool:
    return bool(URL_REGEX.match(url))


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP benchmark tool")

    parser.add_argument(
        "-H", "--hosts",
        type=str,
        help="Comma-separated list of hosts (https://example.com)"
    )

    parser.add_argument(
        "-F", "--file",
        type=str,
        help="File with list of hosts (one per line)"
    )

    parser.add_argument(
        "-C", "--count",
        type=int,
        default=1,
        help="Number of requests per host (default: 1)"
    )

    parser.add_argument(
        "-O", "--output",
        type=str,
        help="Output file path"
    )

    args = parser.parse_args()

    if args.hosts and args.file:
        parser.error("Use either -H or -F, not both.")

    if not args.hosts and not args.file:
        parser.error("You must provide either -H or -F.")

    if args.count < 1:
        parser.error("Count must be a positive integer.")

    return args


def load_hosts(args) -> list[str]:
    hosts = []

    if args.hosts:
        hosts = args.hosts.split(",")

    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                hosts = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)

    invalid = [h for h in hosts if not validate_url(h)]
    if invalid:
        print("Invalid URL format detected:")
        for h in invalid:
            print(f"  {h}")
        sys.exit(1)

    return hosts

async def fetch(client: httpx.AsyncClient, url: str) -> tuple[str, float|None]:
    start = time.perf_counter()
    try:
        response = await client.get(url)
        elapsed = time.perf_counter() - start

        if response.is_informational:
            return "informational", elapsed
        elif response.is_success:
            return "success", elapsed
        elif response.is_redirect:
            return "redirect", elapsed
        elif response.is_client_error:
            return "client_error", elapsed
        elif response.is_server_error:
            return "server_error", elapsed
        else:
            return "error", None

    except httpx.RequestError:
        return "error", None


async def benchmark_host(url: str, count: int) -> dict:
    success = 0
    failed = 0
    errors = 0
    times = []

    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [asyncio.create_task(fetch(client, url)) for _ in range(count)]
        results = await asyncio.gather(*tasks)

    for status, elapsed in results:
        if status == "success" or status == "informational" or status == "redirect":
            success += 1
            times.append(elapsed)
        elif status == "client_error" or status == "server_error" :
            failed += 1
            times.append(elapsed)
        else:
            errors += 1

    stats = {
        "host": url,
        "success": success,
        "failed": failed,
        "errors": errors,
        "min": min(times) if times else 0,
        "max": max(times) if times else 0,
        "avg": mean(times) if times else 0,
    }

    return stats


def format_stats(stats) -> str:
    return (
        f"\n{'=' * 50}\n"
        f"Host    : {stats['host']}\n"
        f"Success : {stats['success']}\n"
        f"Failed  : {stats['failed']}\n"
        f"Errors  : {stats['errors']}\n"
        f"Min     : {stats['min']:.4f} sec\n"
        f"Max     : {stats['max']:.4f} sec\n"
        f"Avg     : {stats['avg']:.4f} sec\n"
        f"{'=' * 50}\n"
    )


async def main():
    try:
        args = parse_arguments()
        hosts = load_hosts(args)

        all_stats = []

        for host in hosts:
            stats = await benchmark_host(host, args.count)
            all_stats.append(stats)

        output = "".join(format_stats(s) for s in all_stats)

        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(output)
            except Exception as e:
                print(f"Error writing output file: {e}")
                sys.exit(1)
        else:
            print(output)

    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())