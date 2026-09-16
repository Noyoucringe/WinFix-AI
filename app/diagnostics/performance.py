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


def get_memory_usage():
    """
    Collect current memory usage.
    This function is read-only.
    """

    try:
        memory = psutil.virtual_memory()

        return {
            "success": True,
            "tool": "get_memory_usage",
            "data": {
                "usage_percent": memory.percent,
                "total_gb": round(memory.total / (1024 ** 3), 2),
                "available_gb": round(memory.available / (1024 ** 3), 2),
                "used_gb": round(memory.used / (1024 ** 3), 2)
            },
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "get_memory_usage",
            "data": None,
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }


if __name__ == "__main__":
    cpu_result = get_cpu_usage()
    memory_result = get_memory_usage()

    print(cpu_result)
    print(memory_result)