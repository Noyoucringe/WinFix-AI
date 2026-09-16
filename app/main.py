import json
from datetime import datetime

from app.diagnostics.system import get_system_info
from app.diagnostics.performance import (
    get_cpu_usage,
    get_memory_usage
)
from app.diagnostics.storage import get_disk_usage


def main():
    print("=" * 40)
    print("            WINFIX AI")
    print("      Windows Diagnostic Engine")
    print("=" * 40)

    print("\nCollecting system information...\n")

    # Run diagnostics
    result = get_system_info()
    cpu_result = get_cpu_usage()
    memory_result = get_memory_usage()
    disk_result = get_disk_usage()

    # Check system diagnostic
    if not result["success"]:
        print("✗ Failed to collect system information")
        print(result["error"])
        return

    # Display system information
    print("✓ System information collected")

    print("\nSystem Information")
    print("-" * 30)

    for key, value in result["data"].items():
        print(f"{key}: {value}")

    # Display CPU information
    print("\nCPU Information")
    print("-" * 30)

    if cpu_result["success"]:
        for key, value in cpu_result["data"].items():
            print(f"{key}: {value}")
    else:
        print("✗ CPU diagnostic failed")
        print(cpu_result["error"])

    # Display memory information
    print("\nMemory Information")
    print("-" * 30)

    if memory_result["success"]:
        for key, value in memory_result["data"].items():
            print(f"{key}: {value}")
    else:
        print("✗ Memory diagnostic failed")
        print(memory_result["error"])

    # Display disk information
    print("\nDisk Information")
    print("-" * 30)

    if disk_result["success"]:
        for key, value in disk_result["data"].items():
            print(f"{key}: {value}")
    else:
        print("✗ Disk diagnostic failed")
        print(disk_result["error"])

    # Create diagnostic report
    report = {
        "timestamp": datetime.now().isoformat(),
        "diagnostics": {
            "system": result,
            "cpu": cpu_result,
            "memory": memory_result,
            "disk": disk_result
        }
    }

    # Generate report filename
    filename = (
        f"reports/diagnostic_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    # Save report
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print(f"\n✓ Report saved to: {filename}")


if __name__ == "__main__":
    main()