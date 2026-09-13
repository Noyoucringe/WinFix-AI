import json
from datetime import datetime

from app.diagnostics.system import get_system_info


def main():
    print("=" * 40)
    print("            WINFIX AI")
    print("      Windows Diagnostic Engine")
    print("=" * 40)

    print("\nCollecting system information...\n")

    result = get_system_info()

    if result["success"]:
        print("✓ System information collected")

        print("\nSystem Information")
        print("-" * 30)

        for key, value in result["data"].items():
            print(f"{key}: {value}")

        report = {
            "timestamp": datetime.now().isoformat(),
            "diagnostics": {
                "system": result
            }
        }

        filename = (
            f"reports/diagnostic_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(filename, "w", encoding="utf-8") as file:
            json.dump(report, file, indent=4)

        print(f"\n✓ Report saved to: {filename}")

    else:
        print("✗ Failed to collect system information")
        print(result["error"])


if __name__ == "__main__":
    main()