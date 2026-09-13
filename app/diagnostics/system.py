import platform
import socket
import psutil
from datetime import datetime


def get_system_info():
    """
    Collect basic information about the Windows system.
    This function is read-only.
    """

    boot_time = datetime.fromtimestamp(psutil.boot_time())

    return {
        "success": True,
        "tool": "get_system_info",
        "data": {
            "operating_system": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": socket.gethostname(),
            "boot_time": boot_time.isoformat(),
            "python_version": platform.python_version()
        },
        "error": None
    }