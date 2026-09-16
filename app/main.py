import json
from datetime import datetime

from app.diagnostics.system import get_system_info
from app.diagnostics.performance import (
    get_cpu_usage,
    get_memory_usage
)


def main():
    print("=" * 40)
    print("            WINFIX AI")
    print("      Windows Diagnostic Engine")
    print("=" * 40)

    print("\nCollecting system information...\n")

    result = get_system_info()
    cpu_result = get_cpu_usage()
    memory_result = get_memory_usage()

    if not result["success"]:
        print("✗ Failed to collect system information")
        print(result["error"])
        return

    print("✓ System information collected")

    print("\nSystem Information")
    print("-" * 30)

    for key, value in result["data"].items():
        print(f"{key}: {value}")

    print("\nCPU Information")
    print("-" * 30)

    for key, value in cpu_result["data"].items():
        print(f"{key}: {value}")

    print("\nMemory Information")
    print("-" * 30)

    for key, value in memory_result["data"].items():
        print(f"{key}: {value}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "diagnostics": {
            "system": result,
            "cpu": cpu_result,
            "memory": memory_result
        }
    }

    filename = (
        f"reports/diagnostic_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print(f"\n✓ Report saved to: {filename}")


if __name__ == "__main__":
    main()