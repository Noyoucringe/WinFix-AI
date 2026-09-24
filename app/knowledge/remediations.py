"""Plain-language descriptions of every whitelisted fix.

The tool registry decides *whether* an action exists, its risk and whether it
needs administrator rights. This catalog holds what the user is told about it:
what changes, what doesn't, how long it takes, the steps shown while it runs,
and which measurements prove it worked. Implementation lives in
``app/remediation``; nothing here can execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FixInfo:
    title: str                 # "Restart Windows Search"
    change: str                # "Restart the Windows Search service"
    summary: str               # one line for the recommendation card
    description: str           # paragraph on the Recommended fix screen
    expected_effect: str
    what_changes: str
    what_unchanged: str = "Your files, apps and settings."
    files_affected: str = "Not affected"
    estimated_time: str = "Less than a minute"
    risk_note: str = ""
    steps: tuple[str, ...] = ()
    technical: str = ""
    verify_tools: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()      # verification check ids (see verification engine)
    success_headline: str = "The problem is fixed."
    kept_note: str = ""
    settle_seconds: float = 3.0
    general_note: str = ""            # shown when proposed without direct evidence
    extra: dict = field(default_factory=dict)


def _service_fix(service: str, label: str, title: str, effect: str, headline: str,
                 verify_tool: str, check: str, **kw) -> FixInfo:
    return FixInfo(
        title=title,
        change=f"Restart the {label} service",
        summary=kw.pop("summary", f"Restarts {label}. Low risk — your files and open "
                                  "apps aren't affected."),
        description=kw.pop("description", f"Restarting the {label} service ({service}) "
                                          "clears a stuck or stopped state and starts "
                                          "it cleanly."),
        expected_effect=effect,
        what_changes=f"The {label} service ({service}) will be restarted.",
        risk_note="Restarting a service doesn't change your files, apps or settings.",
        steps=(f"Stopping the {label} service", f"Starting the {label} service"),
        technical=f"Restart-Service -Name {service} -Force",
        verify_tools=(verify_tool,),
        checks=(check,),
        success_headline=headline,
        kept_note=f"Restarting {label} is safe to keep and doesn't need to be undone.",
        **kw,
    )


FIXES: dict[str, FixInfo] = {
    "restart_windows_search": _service_fix(
        "WSearch", "Windows Search", "Restart Windows Search",
        effect=("Frees the memory held by the indexer and restores Windows Search. "
                "Search results may be incomplete for a few minutes while indexing resumes."),
        headline="Search is working again.",
        verify_tool="get_search_indexer_status", check="search_service",
        summary=("Releases the memory held by the indexer. Low risk — your files and "
                 "open apps aren't affected."),
        description=("Restarting the Windows Search service releases the memory the "
                     "indexer holds and starts indexing again."),
        extra={"also_checks": ("indexer_memory", "memory_in_use")},
    ),
    "restart_windows_update_service": _service_fix(
        "wuauserv", "Windows Update", "Restart Windows Update",
        effect="Windows Update can check for and download updates again.",
        headline="Windows Update is running again.",
        verify_tool="get_windows_update_status", check="update_service",
    ),
    "restart_bits_service": _service_fix(
        "bits", "Background Intelligent Transfer", "Restart the update download service",
        effect="Windows Update can download updates in the background again.",
        headline="Update downloads can run again.",
        verify_tool="get_windows_update_status", check="bits_service",
    ),
    "restart_print_spooler": _service_fix(
        "Spooler", "Print Spooler", "Restart the Print Spooler",
        effect=("Stuck print jobs are cleared from memory and printing can start again. "
                "You may need to print the document again."),
        headline="Printing is available again.",
        verify_tool="get_important_services", check="spooler_service",
    ),
    "restart_audio_service": _service_fix(
        "Audiosrv", "Windows Audio", "Restart Windows Audio",
        effect="Sound output restarts. Audio in open apps may pause for a moment.",
        headline="Windows Audio is running again.",
        verify_tool="get_important_services", check="audio_service",
    ),
    "restart_bluetooth_service": _service_fix(
        "bthserv", "Bluetooth Support", "Restart Bluetooth Support",
        effect=("Bluetooth discovery and pairing restart. Connected Bluetooth devices may "
                "disconnect briefly and reconnect."),
        headline="Bluetooth Support is running again.",
        verify_tool="get_important_services", check="bluetooth_service",
    ),
    "restart_wlan_service": _service_fix(
        "WlanSvc", "WLAN AutoConfig", "Restart the Wi-Fi service",
        effect="Wi-Fi reconnects to your network. You'll be offline for a few seconds.",
        headline="The Wi-Fi service is running again.",
        verify_tool="get_network_services_status", check="wlan_service",
        extra={"also_checks": ("gateway", "internet")},
    ),
    "flush_dns": FixInfo(
        title="Clear the DNS cache",
        change="Clear the list of website addresses Windows has remembered",
        summary="Clears remembered website addresses. Low risk — nothing else changes.",
        description=("Windows keeps a cache of website addresses. If an entry is wrong or "
                     "stale, sites fail to load. Clearing it makes Windows look them up "
                     "again."),
        expected_effect="Websites are looked up again the next time you visit them.",
        what_changes="The DNS resolver cache is cleared.",
        risk_note="Clearing the cache doesn't change any settings.",
        estimated_time="A few seconds",
        steps=("Clearing the DNS cache",),
        technical="ipconfig /flushdns",
        verify_tools=("test_dns", "test_internet"),
        checks=("dns", "internet"),
        success_headline="Websites resolve again.",
        kept_note="The DNS cache refills itself automatically; nothing needs undoing.",
        settle_seconds=2.0,
    ),
    "renew_ip_configuration": FixInfo(
        title="Renew your network address",
        change="Ask your router for a new network address",
        summary=("Requests a fresh address from your router. You may be offline for a "
                 "few seconds."),
        description=("Your PC gets its network address from your router. Renewing it "
                     "fixes an expired or conflicting address."),
        expected_effect="Your PC gets a fresh address and reconnects.",
        what_changes="The DHCP lease on your network adapters is renewed.",
        risk_note="You may lose connection for a few seconds.",
        estimated_time="Up to a minute",
        steps=("Requesting a new address from your router",),
        technical="ipconfig /renew",
        verify_tools=("ping_gateway", "test_internet"),
        checks=("gateway", "internet"),
        success_headline="Your connection is working again.",
        settle_seconds=5.0,
    ),
    "release_ip_configuration": FixInfo(
        title="Release your network address",
        change="Give up the current network address",
        summary="Disconnects until a new address is requested.",
        description="Releases the address your router assigned.",
        expected_effect="You will be offline until an address is renewed.",
        what_changes="The DHCP lease is released.",
        risk_note="You will be disconnected.",
        steps=("Releasing the network address",),
        technical="ipconfig /release",
        verify_tools=("get_network_adapters",),
        checks=("adapter",),
    ),
    "restart_network_adapter": FixInfo(
        title="Restart the network adapter",
        change="Turn the network adapter off and on again",
        summary="Turns the adapter off and on. You'll be offline for a few seconds.",
        description=("Restarting the network adapter resets the connection, like "
                     "unplugging and reconnecting it."),
        expected_effect="The adapter reconnects to your network.",
        what_changes="The network adapter will be disabled and then enabled again.",
        risk_note="You'll be offline for a few seconds while it reconnects.",
        steps=("Turning the network adapter off", "Turning the network adapter on",
               "Waiting for the connection"),
        technical='netsh interface set interface name="<adapter>" admin=disabled / enabled',
        verify_tools=("ping_gateway", "test_internet", "get_network_adapters"),
        checks=("gateway", "internet"),
        success_headline="Your network connection is working again.",
        settle_seconds=8.0,
    ),
    "reset_winsock": FixInfo(
        title="Reset network settings (Winsock)",
        change="Reset the Windows network stack",
        summary="Resets networking to defaults. A restart is required afterwards.",
        description=("Resets the Winsock catalog, which network apps use to connect. "
                     "This fixes corruption caused by some VPN or security software."),
        expected_effect="Network connections work again after you restart your PC.",
        what_changes="The Winsock catalog is reset to its default.",
        what_unchanged="Your files and apps. Some VPN software may need reinstalling.",
        risk_note="Higher risk: VPN or firewall software may need to be reinstalled.",
        estimated_time="A minute, plus a restart",
        steps=("Resetting the Winsock catalog",),
        technical="netsh winsock reset",
        verify_tools=("test_internet",),
        checks=("internet",),
        success_headline="Network settings were reset.",
        kept_note="Restart your PC to finish applying this change.",
    ),
    "clear_safe_temp_files": FixInfo(
        title="Delete temporary files",
        change="Delete temporary files older than a day",
        summary=("Frees space held by old temporary files. Your documents and apps "
                 "aren't affected."),
        description=("Windows and apps leave temporary files behind. Deleting those older "
                     "than a day frees space safely; newer files are left alone in case "
                     "an app is still using them."),
        expected_effect="Frees the space shown under Temporary files.",
        what_changes=("Files older than a day in your TEMP folder and the Windows TEMP "
                      "folder are deleted."),
        what_unchanged="Your documents, pictures, downloads, apps and settings.",
        files_affected="Only old temporary files",
        risk_note="Temporary files are recreated by apps when needed.",
        estimated_time="Usually under a minute",
        steps=("Deleting old temporary files",),
        technical="Delete items older than 24 hours in %TEMP% and %WINDIR%\\Temp",
        verify_tools=("get_disk_free_space", "get_reclaimable_space"),
        checks=("free_space", "temp_files"),
        success_headline="Storage space was freed.",
        settle_seconds=1.0,
    ),
    "clear_windows_update_cache_if_safe": FixInfo(
        title="Clear the Windows Update cache",
        change="Delete downloaded update files so Windows downloads them again",
        summary="Removes stuck update downloads. Windows downloads them again.",
        description=("Windows Update keeps downloaded files in a cache. A corrupt download "
                     "can block updates; clearing it forces a clean download."),
        expected_effect="Windows Update downloads fresh copies of pending updates.",
        what_changes=("Files in C:\\Windows\\SoftwareDistribution\\Download are deleted and "
                      "the update services are restarted."),
        what_unchanged="Installed updates, your files, apps and settings.",
        files_affected="Only downloaded update files",
        risk_note="Updates will need to download again.",
        estimated_time="A few minutes",
        steps=("Stopping the update services", "Deleting downloaded update files",
               "Starting the update services"),
        technical="Stop-Service wuauserv,bits; clear SoftwareDistribution\\Download; "
                  "Start-Service wuauserv,bits",
        verify_tools=("get_windows_update_status", "get_disk_free_space"),
        checks=("update_service", "free_space"),
        success_headline="The update cache was cleared.",
    ),
    "empty_recycle_bin": FixInfo(
        title="Empty the Recycle Bin",
        change="Permanently delete the items in the Recycle Bin",
        summary="Frees the space used by deleted files. They can't be recovered after.",
        description=("Files you delete go to the Recycle Bin and still use space until "
                     "it's emptied."),
        expected_effect="Frees the space shown under Recycle Bin.",
        what_changes="Items in the Recycle Bin are permanently deleted.",
        what_unchanged="Everything outside the Recycle Bin.",
        files_affected="Items in the Recycle Bin are permanently deleted",
        risk_note="Deleted files can't be restored afterwards.",
        steps=("Emptying the Recycle Bin",),
        technical="SHEmptyRecycleBinW (no confirmation dialog)",
        verify_tools=("get_disk_free_space", "get_reclaimable_space"),
        checks=("free_space", "recycle_bin"),
        success_headline="Storage space was freed.",
        settle_seconds=1.0,
    ),
    "restart_explorer": FixInfo(
        title="Restart Windows Explorer",
        change="Restart the taskbar, Start menu and File Explorer",
        summary="Restarts the taskbar and File Explorer. Open Explorer windows close.",
        description=("Windows Explorer draws the taskbar, Start and File Explorer. "
                     "Restarting it clears a frozen taskbar or desktop."),
        expected_effect="The taskbar and desktop respond again.",
        what_changes="Windows Explorer restarts; open File Explorer windows close.",
        what_unchanged="Your files and other apps.",
        steps=("Stopping Windows Explorer", "Starting Windows Explorer"),
        technical="taskkill /f /im explorer.exe; start explorer.exe",
        verify_tools=("get_running_processes",),
        checks=("explorer",),
        success_headline="Windows Explorer restarted.",
    ),
    "terminate_unresponsive_application": FixInfo(
        title="End an app that isn't responding",
        change="Close one app that has stopped responding",
        summary="Closes one frozen app. Unsaved work in that app is lost.",
        description="Ends a single app that Windows reports as not responding.",
        expected_effect="The frozen app closes.",
        what_changes="One app is closed.",
        what_unchanged="Other apps and your files.",
        files_affected="Unsaved work in that app is lost",
        steps=("Ending the app",),
        technical="TerminateProcess(pid)",
        verify_tools=("get_unresponsive_apps",),
        checks=("unresponsive",),
    ),
}


def fix_info(tool: str) -> FixInfo:
    info = FIXES.get(tool)
    if info is None:
        raise KeyError(f"No catalog entry for remediation '{tool}'")
    return info
