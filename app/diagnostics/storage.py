import psutil


def get_disk_usage():
    """
    Collect disk usage for the Windows system drive.
    This function is read-only.
    """

    try:
        disk = psutil.disk_usage("C:\\")

        return {
            "success": True,
            "tool": "get_disk_usage",
            "data": {
                "drive": "C:",
                "usage_percent": disk.percent,
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "free_gb": round(disk.free / (1024 ** 3), 2)
            },
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "get_disk_usage",
            "data": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }


if __name__ == "__main__":
    result = get_disk_usage()
    print(result)