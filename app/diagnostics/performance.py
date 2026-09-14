import psutil


def get_cpu_usage():
    """
    Collect current CPU usage.
    This function is read-only.
    """

    try:
        cpu_usage = psutil.cpu_percent(interval=1)

        return {
            "success": True,
            "tool": "get_cpu_usage",
            "data": {
                "usage_percent": cpu_usage
            },
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "get_cpu_usage",
            "data": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }


if __name__ == "__main__":
    result = get_cpu_usage()
    print(result)