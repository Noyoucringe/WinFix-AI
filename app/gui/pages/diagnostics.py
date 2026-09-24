"""Diagnostics: detailed, live information about this PC (read-only)."""

from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.tool_registry import get_registry
from app.diagnostics.live import LiveSampler
from app.gui import icons, theme
from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page, header
from app.gui.widgets.composite import FlowGrid, KeyValueTable
from app.gui.widgets.core import Button, Card, FlowLayout, Text, font, hbox
from app.gui.widgets.status import InfoBar, ProgressBar, ProgressRing, Status
from app.gui.workers import run_async

TABS = [("system", "System", "pc"), ("performance", "Performance", "speed"),
        ("storage", "Storage", "disk"), ("network", "Network", "wifi"),
        ("services", "Services", "services"), ("devices", "Devices", "device"),
        ("events", "Events", "document")]

TAB_TOOLS = {
    "system": ["get_windows_version", "get_system_info", "get_boot_time", "get_pending_reboot"],
    "storage": ["get_disk_partitions", "get_reclaimable_space"],
    "network": ["get_network_adapters", "get_ip_configuration"],
    "services": ["get_important_services"],
    "devices": ["get_problem_devices", "get_bluetooth_devices", "get_driver_information"],
    "events": ["get_recent_system_errors", "get_recent_application_errors"],
}


def _gb(value, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f} GB"


def _uptime(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours = rem // 3600
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
    minutes = (rem % 3600) // 60
    return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} min"


class TabButton(QAbstractButton):
    def __init__(self, key: str, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key, self._text, self._icon = key, text, icon
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self._font = font("body")
        self._bold = font("body_strong")
        width = self.fontMetrics().horizontalAdvance(text) + 44
        self.setFixedSize(width, 40)

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, _event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = p.text if self.isChecked() or self.underMouse() else p.text_secondary
        painter.drawPixmap(4, 12, icons.pixmap(self._icon, QColor(color).name(), 16,
                                               self.devicePixelRatioF()))
        painter.setFont(self._bold if self.isChecked() else self._font)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(28, 0, self.width() - 28, 38),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.accent))
            mid = 28 + (self.width() - 28) / 2 - 8
            painter.drawRoundedRect(QRectF(mid, 37, 16, 3), 1.5, 1.5)
        if self.hasFocus():
            painter.setPen(QColor(p.focus))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, 36), 4, 4)
        painter.end()


class TabBar(QWidget):
    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = FlowLayout(self, spacing=16)  # wraps onto a second line when narrow
        self.buttons: dict[str, TabButton] = {}
        for key, text, icon in TABS:
            button = TabButton(key, text, icon)
            button.clicked.connect(lambda _=False, k=key: self.select(k))
            layout.addWidget(button)
            self.buttons[key] = button

    def select(self, key: str) -> None:
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        self.changed.emit(key)


class MetricCard(Card):
    """CPU / Memory / Disk card: big value, meter, and a 2x2 grid of details."""

    def __init__(self, icon: str, title: str, fields: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=(16, 16, 16, 16), spacing=8)
        self.add(hbox(IconLabel(icon, "text", 16), Text(title, "body_strong"), spacing=8,
                      stretch_at=1))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.value = Text("—", "value")
        self.unit = Text("", "caption", "secondary")
        row.addWidget(self.value)
        row.addWidget(self.unit, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        self.add(row)
        self.bar = ProgressBar(meter=True)
        self.add(self.bar)
        self.body.addSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.fields: dict[str, Text] = {}
        for i, name in enumerate(fields):
            value = Text("—", "body")
            grid.addLayout(_labelled(name, value), i // 2, i % 2)
            self.fields[name] = value
        self.add(grid)

    def set(self, value: str, unit: str, fraction: float | None, **fields) -> None:
        self.value.setText(value)
        self.unit.setText(unit)
        self.bar.set_value(fraction or 0.0)
        for name, text in fields.items():
            if name in self.fields:
                self.fields[name].setText(text)
        self.setAccessibleName(f"{value} {unit}")


def _labelled(label: str, value: QWidget) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(0)
    col.addWidget(Text(label, "caption", "secondary"))
    col.addWidget(value)
    return col


class _SortItem(QTableWidgetItem):
    def __init__(self, text: str, key) -> None:
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, key)

    def __lt__(self, other) -> bool:
        return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)


def _table(columns: list[str], stretch: int = 0) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setFont(font("body"))
    table.verticalHeader().setDefaultSectionSize(40)
    head = table.horizontalHeader()
    head.setFont(font("caption"))
    head.setHighlightSections(False)
    for i in range(len(columns)):
        head.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if i == stretch
                                  else QHeaderView.ResizeMode.ResizeToContents)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return table


def _fit(table: QTableWidget) -> None:
    height = table.horizontalHeader().height() + sum(table.rowHeight(r)
                                                     for r in range(table.rowCount())) + 4
    table.setFixedHeight(height)


class DiagnosticsPage(Page):
    key = nav_key = "diagnostics"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        refresh = Button("Refresh", "Standard", "refresh")
        refresh.clicked.connect(self.refresh)
        export = Button("Export", "Standard", "export")
        export.clicked.connect(self._export)
        self.add(header("Diagnostics", "Detailed information collected from this PC. "
                        "Values update every 2 seconds.", actions=[refresh, export]))
        self.add(20)
        self.tabs = TabBar()
        self.add(self.tabs)
        self.add(16)
        self.stack = QStackedWidget()
        self.add(self.stack)
        self.pages: dict[str, QWidget] = {}
        self.data: dict[str, dict] = {}
        self.sampler: LiveSampler | None = None
        self._sampling = False
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._tick)
        self.current = "performance"
        self.tabs.changed.connect(self._show_tab)

    # --- lifecycle -----------------------------------------------------------
    def _runner(self):
        """Live, read-only measurements, even in demo mode (this page shows this PC)."""
        if self.ctx.demo is not None:
            return self.ctx.demo.live_execute
        return get_registry().execute_tool

    def on_show(self, tab: str | None = None, **params) -> None:
        self.tabs.select(tab or self.current)

    def on_hide(self) -> None:
        self.timer.stop()

    def refresh(self) -> None:
        if self.current == "performance":
            self._tick()
        else:
            self._load(self.current, force=True)

    def _show_tab(self, key: str) -> None:
        self.current = key
        if key not in self.pages:
            page = self._build(key)
            self.pages[key] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(self.pages[key])
        if key == "performance":
            self._tick()
            self.timer.start()
        else:
            self.timer.stop()
            self._load(key)

    # --- performance (live) -----------------------------------------------------
    def _build(self, key: str) -> QWidget:
        if key == "performance":
            return self._build_performance()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(hbox(ProgressRing(16), Text("Collecting…", "body", "secondary")))
        return widget

    def _build_performance(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.cpu = MetricCard("cpu", "CPU", ["30-second average", "Speed", "Processes",
                                             "Up time"])
        self.mem = MetricCard("memory", "Memory", ["Available", "Committed", "Cached",
                                                   "Compressed"])
        self.disk = MetricCard("disk", "Disk (C:)", ["Free", "Capacity", "Active time",
                                                     "Read / write"])
        grid = FlowGrid(min_width=250, spacing=8)
        grid.set_items([self.cpu, self.mem, self.disk])
        layout.addWidget(grid)
        layout.addSpacing(28)
        head = QHBoxLayout()
        head.addWidget(Text("Processes using the most memory", "body_strong"))
        head.addStretch(1)
        self.sorted_by = Text("Sorted by memory", "caption", "secondary")
        head.addWidget(self.sorted_by)
        layout.addLayout(head)
        layout.addSpacing(8)
        self.proc_table = _table(["Name", "Status", "CPU", "Memory"])
        self.proc_table.setSortingEnabled(True)
        self.proc_table.horizontalHeader().sortIndicatorChanged.connect(self._sort_changed)
        layout.addWidget(self.proc_table)
        return widget

    def _sort_changed(self, column: int, _order) -> None:
        self.sorted_by.setText("Sorted by " + ["name", "status", "CPU", "memory"][column])

    def _tick(self) -> None:
        if self._sampling:
            return  # a slow sample is still running; never pile up work
        self._sampling = True
        if self.sampler is None:
            self.sampler = LiveSampler()
        sampler = self.sampler
        run_async(sampler.sample, self._show_sample, self._sample_failed)

    def _sample_failed(self, message: str, detail: str) -> None:
        self._sampling = False

    def _show_sample(self, s: dict) -> None:
        self._sampling = False
        self.data["performance"] = s
        cpu, mem, disk = s["cpu"], s["memory"], s["disk"]
        self.cpu.set(f"{cpu['usage_percent']:.0f}%", "Utilization", cpu["usage_percent"] / 100,
                     **{"30-second average": f"{cpu['average_percent']:.1f}%",
                        "Speed": f"{cpu['speed_ghz']:.2f} GHz" if cpu["speed_ghz"] else "—",
                        "Processes": str(s["processes"]["count"]),
                        "Up time": _uptime(s["uptime_s"])})
        committed = "—"
        if mem["committed_gb"] is not None:
            committed = f"{mem['committed_gb']:.1f} of {mem['commit_limit_gb']:.1f} GB"
        compressed = "—" if mem["compressed_mb"] is None else f"{mem['compressed_mb']:.0f} MB"
        self.mem.set(f"{mem['usage_percent']:.0f}%",
                     f"{mem['used_gb']:.1f} of {mem['total_gb']:.1f} GB",
                     mem["usage_percent"] / 100,
                     Available=_gb(mem["available_gb"]), Committed=committed,
                     Cached=_gb(mem["cached_gb"]), Compressed=compressed)
        rw = "—"
        if disk["read_mb_s"] is not None:
            rw = f"{disk['read_mb_s']:.1f} / {disk['write_mb_s']:.1f} MB/s"
        self.disk.set(f"{disk['usage_percent']:.1f}%", "Used", disk["usage_percent"] / 100,
                      Free=_gb(disk["free_gb"]), Capacity=_gb(disk["total_gb"], 0),
                      **{"Active time": "—" if disk["active_percent"] is None
                         else f"{disk['active_percent']:.0f}%", "Read / write": rw})
        self._fill_processes(s["processes"]["groups"])

    def _fill_processes(self, groups: list[dict]) -> None:
        table = self.proc_table
        sort_col = table.horizontalHeader().sortIndicatorSection()
        order = table.horizontalHeader().sortIndicatorOrder()
        table.setSortingEnabled(False)
        table.setRowCount(len(groups))
        p = theme.palette()
        for r, g in enumerate(groups):
            name = g["display_name"] + (f" ({g['count']})" if g["count"] > 1 else "")
            status = "Not responding" if g["not_responding"] else "Running"
            state = "caution" if g["not_responding"] else "success"
            status_item = _SortItem(status, status)
            status_item.setIcon(_status_icon(state))
            cells = [_SortItem(name, name.lower()), status_item,
                     _SortItem(f"{g['cpu_percent']:.1f}%", g["cpu_percent"]),
                     _SortItem(_size(g["memory_mb"]), g["memory_mb"])]
            for c, item in enumerate(cells):
                if c >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                if c == 3:
                    item.setFont(font("body_strong"))
                item.setForeground(QColor(p.text))
                table.setItem(r, c, item)
        table.setSortingEnabled(True)
        if sort_col < 0:
            table.sortItems(3, Qt.SortOrder.DescendingOrder)
        else:
            table.sortItems(sort_col, order)
        _fit(table)

    # --- other tabs ---------------------------------------------------------
    def _load(self, key: str, force: bool = False) -> None:
        if key in self.data and not force:
            return
        tools = TAB_TOOLS[key]
        run = self._runner()

        def collect() -> dict:
            return {t: run(t) for t in tools}

        run_async(collect, lambda results: self._render(key, results),
                  lambda m, d: self.ctx.error("Couldn't collect diagnostics", m, d))

    def _render(self, key: str, results: dict) -> None:
        self.data[key] = results
        page = self.pages[key]
        layout = page.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        renderer = getattr(self, f"_render_{key}")
        for widget in renderer(results):
            layout.addWidget(widget)
        layout.addStretch(1)

    @staticmethod
    def _unavailable(result: dict, what: str) -> QWidget | None:
        if result.get("success"):
            return None
        error = result.get("error") or {}
        if error.get("type") == "UnsupportedPlatform":
            return InfoBar("info", f"{what} isn't available on this system.")
        return InfoBar("caution", f"Couldn't read {what.lower()}.",
                       str(error.get("message", ""))[:200])

    def _kv_card(self, title: str, rows: list[tuple[str, str]]) -> Card:
        card = Card(padding=(16, 12, 16, 8))
        card.add(Text(title, "body_strong"))
        table = KeyValueTable(label_width=170)
        for i, (k, v) in enumerate(rows):
            table.add(k, v, divider=i > 0)
        card.add(table)
        return card

    def _render_system(self, r: dict) -> list[QWidget]:
        out = []
        win = r["get_windows_version"].get("data") or {}
        info = r["get_system_info"].get("data") or {}
        boot = r["get_boot_time"].get("data") or {}
        rows = [("Product", win.get("product", "—")),
                ("Edition", win.get("edition") or "—"),
                ("Version", win.get("display_version") or win.get("version", "—")),
                ("Build", f"{win.get('build')}.{win.get('ubr')}" if win.get("build") else "—")]
        out.append(self._kv_card("Windows", rows))
        out.append(self._kv_card("Device", [
            ("Processor cores", f"{info.get('cpu_count_physical', '—')} physical, "
                                f"{info.get('cpu_count_logical', '—')} logical"),
            ("Installed memory", _gb(info.get("memory_total_gb"))),
            ("Architecture", info.get("architecture", "—"))]))
        boot_time = boot.get("boot_time")
        out.append(self._kv_card("Uptime", [
            ("Last started", datetime.fromisoformat(boot_time).astimezone()
             .strftime("%b %d, %I:%M %p") if boot_time else "—"),
            ("Running for", _uptime(boot.get("uptime_seconds", 0)))]))
        pending = r["get_pending_reboot"]
        unavailable = self._unavailable(pending, "Restart status")
        if unavailable:
            out.append(unavailable)
        else:
            d = pending["data"]
            out.append(self._kv_card("Updates", [
                ("Restart pending", "Yes — " + ", ".join(d["reasons"]) if d["reboot_pending"]
                 else "No")]))
        return out

    def _render_storage(self, r: dict) -> list[QWidget]:
        out = []
        parts = r["get_disk_partitions"].get("data") or {}
        table = _table(["Drive", "File system", "Used", "Free", "Capacity"])
        rows = parts.get("partitions", [])
        table.setRowCount(len(rows))
        for i, p in enumerate(rows):
            for c, text in enumerate([p["mountpoint"], p["fstype"], f"{p['usage_percent']:.1f}%",
                                      _gb(p["free_gb"]), _gb(p["total_gb"], 0)]):
                table.setItem(i, c, QTableWidgetItem(text))
        _fit(table)
        out.append(Text("Drives", "body_strong"))
        out.append(table)
        rec = r["get_reclaimable_space"].get("data")
        if rec:
            out.append(self._kv_card("Reclaimable space", [
                ("Temporary files", _size(rec["temp_mb"])),
                ("Recycle Bin", "—" if rec["recycle_bin_mb"] is None else
                 f"{_size(rec['recycle_bin_mb'])} in {rec['recycle_bin_items']} items")]))
        return out

    def _render_network(self, r: dict) -> list[QWidget]:
        out = []
        data = r["get_network_adapters"].get("data") or {}
        adapters = [a for a in data.get("adapters", []) if not a.get("virtual")]
        table = _table(["Adapter", "Status", "Type", "Speed", "IPv4 address"])
        table.setRowCount(len(adapters))
        for i, a in enumerate(adapters):
            item = QTableWidgetItem("Connected" if a["is_up"] else "Disconnected")
            item.setIcon(_status_icon("success" if a["is_up"] else "queued"))
            cells = [QTableWidgetItem(a["name"]), item,
                     QTableWidgetItem("Wi-Fi" if a["wireless"] else "Wired/other"),
                     QTableWidgetItem(f"{a['speed_mbps']} Mbps" if a["speed_mbps"] else "—"),
                     QTableWidgetItem(", ".join(a["ipv4"]) or "—")]
            for c, cell in enumerate(cells):
                table.setItem(i, c, cell)
        _fit(table)
        out += [Text("Network adapters", "body_strong"), table]
        test = Button("Run connection tests", "Standard", "globe")
        self._net_status = Text("Tests your router, DNS and internet connection "
                                "(read-only).", "caption", "secondary")
        test.clicked.connect(self._run_network_tests)
        out.append(Card_with(hbox(test, self._net_status, spacing=12, stretch_at=1)))
        return out

    def _run_network_tests(self) -> None:
        self._net_status.setText("Testing…")
        tool = self._runner()

        def run():
            return {t: tool(t) for t in ("ping_gateway", "test_dns", "test_internet")}

        def done(results: dict) -> None:
            def ok(tool, key):
                d = results[tool].get("data") or {}
                return "OK" if d.get(key) else "Failing"
            self._net_status.setText(
                f"Router: {ok('ping_gateway', 'reachable')}   ·   DNS: "
                f"{ok('test_dns', 'dns_working')}   ·   Internet: "
                f"{ok('test_internet', 'internet_reachable')}")

        run_async(run, done)

    def _render_services(self, r: dict) -> list[QWidget]:
        result = r["get_important_services"]
        unavailable = self._unavailable(result, "Service status")
        if unavailable:
            return [unavailable]
        services = result["data"]["services"]
        table = _table(["Service", "Status", "Startup type", "Health"])
        table.setRowCount(len(services))
        for i, s in enumerate(services.values()):
            status = QTableWidgetItem(s["status_text"])
            status.setIcon(_status_icon("success" if s.get("running") else "queued"))
            health = QTableWidgetItem("Healthy" if s.get("healthy") else "Needs attention")
            health.setIcon(_status_icon("success" if s.get("healthy") else "caution"))
            for c, cell in enumerate([QTableWidgetItem(s["label"]), status,
                                      QTableWidgetItem((s.get("start_type") or "—").title()),
                                      health]):
                table.setItem(i, c, cell)
        _fit(table)
        return [table]

    def _render_devices(self, r: dict) -> list[QWidget]:
        out = []
        for tool, title in (("get_problem_devices", "Devices with problems"),
                            ("get_bluetooth_devices", "Bluetooth")):
            result = r[tool]
            unavailable = self._unavailable(result, title)
            if unavailable:
                out.append(unavailable)
                continue
            devices = result["data"].get("devices", [])
            out.append(Text(title, "body_strong"))
            if not devices:
                out.append(Status("success", "No problems reported"))
                continue
            table = _table(["Device", "Class", "Status"])
            table.setRowCount(len(devices))
            for i, d in enumerate(devices):
                status = QTableWidgetItem(d.get("status") or "—")
                status.setIcon(_status_icon("success" if d.get("status") == "OK" else "caution"))
                for c, cell in enumerate([QTableWidgetItem(d["name"]),
                                          QTableWidgetItem(d.get("class") or "—"), status]):
                    table.setItem(i, c, cell)
            _fit(table)
            out.append(table)
        drivers = r["get_driver_information"].get("data")
        if drivers:
            out.append(self._kv_card("Drivers", [
                ("Installed drivers", str(drivers["count"])),
                ("Unsigned drivers", str(drivers["unsigned_count"]))]))
        return out

    def _render_events(self, r: dict) -> list[QWidget]:
        out = []
        for tool, title in (("get_recent_system_errors", "System log"),
                            ("get_recent_application_errors", "Application log")):
            result = r[tool]
            unavailable = self._unavailable(result, title)
            if unavailable:
                out.append(unavailable)
                continue
            events = result["data"]["events"]
            out.append(Text(f"{title} · errors in the last 24 hours", "body_strong"))
            if not events:
                out.append(Status("success", "No errors recorded"))
                continue
            table = _table(["Time", "Source", "Message"], stretch=2)
            table.setRowCount(len(events))
            for i, e in enumerate(events):
                when = datetime.fromisoformat(e["time"]).strftime("%b %d %H:%M") \
                    if e.get("time") else "—"
                level = QTableWidgetItem(when)
                level.setIcon(_status_icon("critical" if e["level"] == "Critical" else "caution"))
                for c, cell in enumerate([level, QTableWidgetItem(e.get("source") or "—"),
                                          QTableWidgetItem(e.get("message") or "")]):
                    table.setItem(i, c, cell)
            _fit(table)
            out.append(table)
        return out

    # --- export ---------------------------------------------------------------
    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics",
            f"winfix-diagnostics-{datetime.now():%Y%m%d-%H%M}.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, default=str)
        except OSError as exc:
            self.ctx.error("Couldn't export diagnostics", str(exc))
            return
        self.ctx.notify("Diagnostics exported", path)


def Card_with(layout) -> Card:  # noqa: N802 - small factory
    card = Card(padding=(16, 12, 16, 12))
    card.add(layout)
    return card


def _size(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def _status_icon(state: str):
    from PySide6.QtGui import QIcon, QPixmap

    from app.gui.widgets.status import StatusIcon

    widget = StatusIcon(state, 16)
    pixmap = QPixmap(widget.size() * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap)
    widget.deleteLater()
    return QIcon(pixmap)
