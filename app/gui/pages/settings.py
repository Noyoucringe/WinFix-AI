"""Settings, and its AI provider and Privacy subpages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

from app import ENGINE_VERSION, __version__
from app.core import autostart, credentials
from app.core.config import get_settings, user_data_dir
from app.core.logging_setup import get_logger
from app.core.privacy import ITEM_EVENTS, ITEM_MEASUREMENTS, ITEM_PROCESS_NAMES
from app.core.user_settings import (
    DEFAULT_ENDPOINTS,
    DEFAULT_MODELS,
    PROVIDER_LABELS,
    EndpointError,
    get_store,
    validate_endpoint,
)
from app.gui import theme
from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page, header
from app.gui.widgets.composite import Breadcrumb, Footnote, ListCard, SettingsRow
from app.gui.widgets.core import (
    Button,
    Card,
    ComboBox,
    RadioButton,
    Text,
    ToggleSwitch,
    hbox,
    text_field,
    vbox,
)
from app.gui.widgets.dialog import ContentDialog
from app.gui.widgets.status import InfoBar, Status
from app.gui.workers import run_async

logger = get_logger(__name__)

THEMES = [("Light", "light"), ("Dark", "dark"), ("Use Windows setting", "system")]
DEPTHS = [("Quick", "quick"), ("Standard", "standard"), ("Thorough", "thorough")]
DEPTH_HELP = {
    "quick": "Runs only the most important checks for your problem.",
    "standard": "Runs the checks for your problem plus general health checks.",
    "thorough": "Adds deeper checks such as event logs and drivers. Takes longer.",
}


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _section(page: Page, title: str, first: bool = False) -> None:
    if not first:
        page.add(20)
    page.add(Text(title, "body_strong"))
    page.add(8)


def _row(page: Page, row: QWidget) -> None:
    page.add(row)
    page.add(4)


def _sub_header(page: Page, title: str) -> None:
    crumb = Breadcrumb(["Settings", title])
    crumb.navigate.connect(lambda _i: page.ctx.navigate("settings"))
    page.add(header(crumb))
    page.add(20)


# --- Settings ----------------------------------------------------------------
class SettingsPage(Page):
    key = nav_key = "settings"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        store = get_store()
        current = store.load()
        self.add(Text("Settings", "title"))
        self.add(20)

        _section(self, "Appearance", first=True)
        self.theme = ComboBox(THEMES)
        self.theme.setMinimumWidth(200)
        self.theme.setAccessibleName("App theme")
        self.theme.set_value(current.theme)
        self.theme.currentIndexChanged.connect(self._theme_changed)
        _row(self, SettingsRow("theme", "App theme", "Select which app theme to display",
                               self.theme))

        _section(self, "Troubleshooting")
        self.ai_row = SettingsRow("pc", "AI provider",
                                  "Choose where diagnostic evidence is analyzed",
                                  chevron=True, value="Local")
        self.ai_row.clicked.connect(lambda: ctx.navigate("settings_ai"))
        _row(self, self.ai_row)
        privacy = SettingsRow("privacy", "Privacy",
                              "Diagnostic information is processed locally unless cloud AI "
                              "analysis is enabled.", chevron=True)
        privacy.clicked.connect(lambda: ctx.navigate("settings_privacy"))
        _row(self, privacy)
        self.depth = ComboBox(DEPTHS)
        self.depth.setMinimumWidth(200)
        self.depth.setAccessibleName("Diagnostic depth")
        self.depth.set_value(current.diagnostic_depth)
        self.depth.currentIndexChanged.connect(self._depth_changed)
        self.depth_row = SettingsRow("diagnostics", "Diagnostic depth",
                                     "How much information WinFix collects during an "
                                     "investigation", self.depth)
        self.depth.setToolTip(DEPTH_HELP[current.diagnostic_depth])
        _row(self, self.depth_row)

        _section(self, "General")
        self.notify = ToggleSwitch(current.notifications)
        self.notify.setAccessibleName("Notifications")
        self.notify.toggled.connect(lambda on: store.update(notifications=on))
        _row(self, SettingsRow("bell", "Notifications",
                               "Notify me when a session needs my approval or finishes",
                               self.notify))
        self.autostart = ToggleSwitch(autostart.is_enabled())
        self.autostart.setAccessibleName("Start with Windows")
        self.autostart.setEnabled(autostart.supported())
        self.autostart.toggled.connect(self._autostart_changed)
        _row(self, SettingsRow("power", "Start with Windows",
                               "Run a quick health check when I sign in"
                               if autostart.supported() else
                               "Available when WinFix runs on Windows", self.autostart))

        _section(self, "About")
        about = SettingsRow("", "About WinFix AI",
                            f"Version {__version__} · Diagnostics engine {ENGINE_VERSION}",
                            chevron=True, icon_widget=_AppGlyph())
        about.clicked.connect(lambda: ctx.navigate("about"))
        _row(self, about)

    def on_show(self, **params) -> None:
        current = get_store().load()
        self.ai_row.value.setText("Cloud" if current.analysis == "cloud" else "Local")
        self.autostart.blockSignals(True)
        self.autostart.setChecked(autostart.is_enabled())
        self.autostart.blockSignals(False)

    def _theme_changed(self) -> None:
        mode = self.theme.value()
        get_store().update(theme=mode)
        theme.manager().apply(mode)

    def _depth_changed(self) -> None:
        depth = self.depth.value()
        get_store().update(diagnostic_depth=depth)
        self.depth.setToolTip(DEPTH_HELP[depth])

    def _autostart_changed(self, on: bool) -> None:
        ok, message = autostart.set_enabled(on)
        if ok:
            get_store().update(start_with_windows=on)
            return
        self.autostart.blockSignals(True)
        self.autostart.setChecked(not on)
        self.autostart.blockSignals(False)
        self.ctx.error("Couldn't change this setting", message)


class _AppGlyph(QWidget):
    """The app icon at 20 px, for the About row."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(20, 20)

    def paintEvent(self, _event) -> None:
        from PySide6.QtGui import QPainter

        from app.gui.branding import app_icon

        painter = QPainter(self)
        app_icon().paint(painter, self.rect())
        painter.end()


# --- AI provider -------------------------------------------------------------------
class _ChoiceRow(QWidget):
    """A radio row inside a list card: radio, icon, title and description."""

    def __init__(self, icon: str, title: str, description: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        self.radio = RadioButton()
        self.radio.setAccessibleName(title)
        self.radio.setAccessibleDescription(description)
        layout.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(IconLabel(icon, "text", 20), 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(vbox(Text(title, "body"),
                              Text(description, "caption", "secondary", wrap=True),
                              spacing=2), 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled():
            self.radio.setChecked(True)
            self.radio.clicked.emit(True)
        super().mouseReleaseEvent(event)


class AIProviderPage(Page):
    key = "settings_ai"
    nav_key = "settings"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self._loading = False
        _sub_header(self, "AI provider")
        self.banner_host = vbox(spacing=0)
        self.add(self.banner_host)
        self.add(20)

        self.add(Text("Analysis", "body_strong"))
        self.add(8)
        choices = ListCard()
        self.local = _ChoiceRow("pc", "Local", "Runs on this PC. Nothing leaves your device.")
        self.cloud = _ChoiceRow("cloud", "Cloud", "Uses a cloud AI provider for deeper "
                                "analysis. Only the items you allow below are sent.")
        group = QButtonGroup(self)
        for choice in (self.local, self.cloud):
            group.addButton(choice.radio)
            choices.add_row(choice)
        self.local.radio.clicked.connect(lambda: self._set_analysis("local"))
        self.cloud.radio.clicked.connect(lambda: self._set_analysis("cloud"))
        self.add(choices)

        # Cloud provider details
        self.provider_section = QWidget()
        section = vbox(spacing=4)
        self.provider_section.setLayout(section)
        section.addSpacing(20)
        section.addWidget(Text("Cloud provider", "body_strong"))
        section.addSpacing(4)
        self.format = ComboBox([(label, key) for key, label in PROVIDER_LABELS.items()])
        self.format.setMinimumWidth(240)
        self.format.setAccessibleName("API format")
        self.format.currentIndexChanged.connect(self._format_changed)
        section.addWidget(SettingsRow("puzzle_piece", "API format",
                                      "The request format your provider accepts", self.format))
        self.endpoint = text_field("https://api.example.com/v1", width=240,
                                   accessible_name="Endpoint")
        self.endpoint.editingFinished.connect(self._save_endpoint)
        self.endpoint.textChanged.connect(lambda _t: self._endpoint_error(""))
        self.endpoint_row = SettingsRow("globe", "Endpoint", "The address of your AI provider",
                                        self.endpoint)
        section.addWidget(self.endpoint_row)
        self.model = text_field("", width=240, accessible_name="Model")
        self.model.editingFinished.connect(self._save_model)
        section.addWidget(SettingsRow("developer_board", "Model",
                                      "The model name your provider uses", self.model))
        self.key_field = text_field("Paste your API key", password=True, width=240,
                                    accessible_name="API key")
        self.key_field.returnPressed.connect(self._save_key)
        self.key_button = Button("Save key", "Standard")
        self.key_button.clicked.connect(self._key_action)
        self.remove_key = Button("Remove", "Subtle")
        self.remove_key.clicked.connect(self._remove_key)
        key_controls = QWidget()
        key_controls.setLayout(hbox(self.key_field, self.key_button, self.remove_key,
                                    spacing=8))
        self.key_row = SettingsRow("key", "API key", "No key saved.", key_controls)
        section.addWidget(self.key_row)
        self.test = Button("Test connection", "Standard")
        self.test.clicked.connect(self._test)
        self.test_status = Status("info", "", "caption", 12)
        self.test_status.hide()
        section.addSpacing(4)
        section.addLayout(hbox(self.test, self.test_status, spacing=12, stretch_at=-1))
        section.addSpacing(4)
        section.addWidget(Footnote(
            f"API keys are stored in {credentials.store_name()}, never in WinFix's "
            "settings, logs or history. The connection test sends only a fixed test "
            "message, no diagnostic data."))

        section.addSpacing(20)
        section.addWidget(Text("Sent to the cloud provider", "body_strong"))
        section.addSpacing(4)
        measurements = ToggleSwitch(True)
        measurements.setEnabled(False)
        measurements.setAccessibleName(ITEM_MEASUREMENTS)
        section.addWidget(SettingsRow("diagnostics", ITEM_MEASUREMENTS,
                                      "CPU, memory, disk and service status. Required for "
                                      "cloud analysis.", measurements))
        self.send_names = ToggleSwitch()
        self.send_names.setAccessibleName(ITEM_PROCESS_NAMES)
        self.send_names.toggled.connect(
            lambda on: self._loading or get_store().update(send_process_names=on))
        section.addWidget(SettingsRow("list", ITEM_PROCESS_NAMES,
                                      "Helps identify the apps involved", self.send_names))
        self.send_events = ToggleSwitch()
        self.send_events.setAccessibleName(ITEM_EVENTS)
        self.send_events.toggled.connect(
            lambda on: self._loading or get_store().update(send_event_excerpts=on))
        section.addWidget(SettingsRow("document", ITEM_EVENTS,
                                      "May include device and user names", self.send_events))
        section.addSpacing(4)
        section.addWidget(Footnote(
            "WinFix removes user names, the PC name, file paths, network addresses and "
            "anything that looks like a password or key before sending. Passwords, "
            "browser data and personal files are never sent."))
        self.add(self.provider_section)

    # --- state -------------------------------------------------------------
    def on_show(self, **params) -> None:
        self._loading = True
        current = get_store().load()
        (self.cloud if current.analysis == "cloud" else self.local).radio.setChecked(True)
        self.format.set_value(current.provider_type)
        self.endpoint.setText(current.endpoint)
        self.model.setText(current.model)
        self.send_names.setChecked(current.send_process_names)
        self.send_events.setChecked(current.send_event_excerpts)
        self._loading = False
        self.test_status.hide()
        self._refresh()

    def _refresh(self) -> None:
        current = get_store().load()
        provider = current.provider_type
        cloud = current.analysis == "cloud"
        self.provider_section.setEnabled(cloud)
        self.endpoint.setPlaceholderText(DEFAULT_ENDPOINTS[provider])
        self.model.setPlaceholderText(DEFAULT_MODELS[provider])
        has_key = bool(credentials.get_api_key(provider))
        self.key_row.set_description(credentials.describe(provider))
        self.key_field.setReadOnly(has_key)
        self.key_field.setText(credentials.masked(provider) if has_key else "")
        self.key_field.setPlaceholderText("" if has_key else "Paste your API key")
        self.key_button.setText("Replace key" if has_key else "Save key")
        self.remove_key.setVisible(has_key)
        self.test.setEnabled(has_key)

        while self.banner_host.count():
            item = self.banner_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not cloud:
            bar = InfoBar("info", "Cloud analysis is off.",
                          "All diagnostic information is processed on this PC.")
        elif not has_key:
            bar = InfoBar("caution", "Add an API key to use cloud analysis.",
                          "Until then WinFix analyzes everything on this PC.")
        else:
            bar = InfoBar("info", "Cloud analysis is on.",
                          "Diagnostic information is processed locally unless cloud AI "
                          "analysis is enabled.")
        self.banner_host.addWidget(bar)

    def _set_analysis(self, analysis: str) -> None:
        if self._loading:
            return
        get_store().update(analysis=analysis)
        logger.info("analysis mode changed", extra={"component": "settings",
                                                    "event": analysis})
        self._refresh()

    def _format_changed(self) -> None:
        if self._loading:
            return
        get_store().update(provider_type=self.format.value(), endpoint="", model="")
        self._loading = True
        self.endpoint.clear()
        self.model.clear()
        self._loading = False
        self.test_status.hide()
        self._refresh()

    def _endpoint_error(self, message: str) -> None:
        self.endpoint.set_error(bool(message))
        self.endpoint_row.set_description(message or "The address of your AI provider",
                                          "critical" if message else "secondary")

    def _save_endpoint(self) -> None:
        if self._loading:
            return
        try:
            url = validate_endpoint(self.endpoint.text())
        except EndpointError as exc:
            self._endpoint_error(str(exc))
            return
        get_store().update(endpoint=url)
        self.endpoint.setText(url)

    def _save_model(self) -> None:
        if not self._loading:
            get_store().update(model=self.model.text().strip()[:120])

    def _key_action(self) -> None:
        if self.key_field.isReadOnly():  # Replace key
            self.key_field.setReadOnly(False)
            self.key_field.clear()
            self.key_field.setPlaceholderText("Paste your new API key")
            self.key_button.setText("Save key")
            self.key_field.setFocus()
            return
        self._save_key()

    def _save_key(self) -> None:
        provider = get_store().load().provider_type
        key = self.key_field.text()
        self.key_field.clear()
        persisted, message = credentials.set_api_key(provider, key)
        if not persisted and not credentials.get_api_key(provider):
            self.ctx.error("Couldn't save the API key", message)
        elif not persisted:
            self.ctx.notify("API key", message)
        self._refresh()

    def _remove_key(self) -> None:
        dialog = ContentDialog(self.window(), "Remove the API key?",
                               "WinFix will stop using cloud analysis until you add a key "
                               "again. The key is deleted from "
                               f"{credentials.store_name()}.", primary="Remove",
                               secondary="Cancel")

        def done(accepted: bool) -> None:
            if accepted:
                credentials.delete_api_key(get_store().load().provider_type)
                self._refresh()
        dialog.open_async(done)

    def _test(self) -> None:
        from app.llm.provider import get_provider

        current = get_store().load().model_copy(update={"analysis": "cloud"})
        provider = get_provider(current)
        self.test.setEnabled(False)
        self.test_status.set("running", "Testing...")
        self.test_status.show()

        def done(result) -> None:
            ok, message = result
            self.test.setEnabled(True)
            self.test_status.set("success" if ok else "critical", message)

        def failed(message: str, _detail: str) -> None:
            self.test.setEnabled(True)
            self.test_status.set("critical", "The connection test failed.")

        run_async(provider.test_connection, done, failed)


# --- Privacy -------------------------------------------------------------------
class PrivacyPage(Page):
    key = "settings_privacy"
    nav_key = "settings"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        _sub_header(self, "Privacy")
        self.banner_host = vbox(spacing=0)
        self.add(self.banner_host)
        self.add(20)

        self.add(Text("Stored on this PC", "body_strong"))
        self.add(8)
        self.history_row = SettingsRow("history", "Troubleshooting history",
                                       "Problems you described, evidence collected and "
                                       "changes made.", value="")
        _row(self, self.history_row)
        data = Button("Open data folder", "Standard", "folder")
        data.clicked.connect(lambda: open_folder(user_data_dir()))
        _row(self, SettingsRow("folder", "Data folder", str(user_data_dir()), data))
        logs = Button("Open logs", "Standard", "folder")
        logs.clicked.connect(lambda: open_folder(get_settings().logs_dir))
        _row(self, SettingsRow("document", "Logs",
                               "Technical logs for troubleshooting WinFix itself. Keys, "
                               "tokens and passwords are never logged.", logs))
        _row(self, SettingsRow("key", "API keys",
                               f"Kept in {credentials.store_name()}, never in files "
                               "WinFix writes."))

        self.add(20)
        self.add(Text("Cloud analysis", "body_strong"))
        self.add(8)
        self.cloud_row = SettingsRow("cloud", "What is sent", "", chevron=True, value="Off")
        self.cloud_row.clicked.connect(lambda: ctx.navigate("settings_ai"))
        _row(self, self.cloud_row)
        never = Card(padding=(16, 14, 16, 14), spacing=6)
        never.add(hbox(IconLabel("shield_check", "text", 20),
                       Text("Never sent", "body"), spacing=16, stretch_at=-1))
        for line in ("Passwords, tokens and API keys", "Browser cookies and saved logins",
                     "Your documents and personal files",
                     "Your user name, PC name, file paths and network addresses"):
            label = Text(f"•  {line}", "caption", "secondary")
            label.setContentsMargins(36, 0, 0, 0)
            never.add(label)
        _row(self, never)

        self.add(20)
        self.add(Text("Clear data", "body_strong"))
        self.add(8)
        clear = Button("Clear history", "Standard", "delete")
        clear.clicked.connect(self._clear_history)
        _row(self, SettingsRow("delete", "Clear troubleshooting history",
                               "Permanently deletes every saved session on this PC.", clear))

    def on_show(self, **params) -> None:
        current = get_store().load()
        cloud = current.analysis == "cloud"
        self.cloud_row.value.setText("On" if cloud else "Off")
        if cloud:
            items = [ITEM_MEASUREMENTS]
            if current.send_process_names:
                items.append(ITEM_PROCESS_NAMES.lower())
            if current.send_event_excerpts:
                items.append(ITEM_EVENTS.lower())
            self.cloud_row.set_description(
                f"{', '.join(items)} are sent to {current.effective_endpoint}.")
        else:
            self.cloud_row.set_description("Nothing is sent. Analysis runs on this PC.")
        while self.banner_host.count():
            item = self.banner_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.banner_host.addWidget(InfoBar(
            "info", "Local first.",
            "Diagnostic information is processed locally unless cloud AI analysis is "
            "enabled."))
        run_async(self.ctx.history.count, self._show_count,
                  lambda m, d: self.history_row.value.setText(""))

    def _show_count(self, count: int) -> None:
        self.history_row.value.setText(f"{count} session{'s' if count != 1 else ''}")

    def _clear_history(self) -> None:
        dialog = ContentDialog(self.window(), "Clear troubleshooting history?",
                               "This permanently deletes every saved session, including its "
                               "evidence and the list of changes WinFix made. It doesn't undo "
                               "any changes.", primary="Clear history", secondary="Cancel")

        def done(accepted: bool) -> None:
            if accepted:
                run_async(self.ctx.history.delete_all,
                          lambda _n: (self._show_count(0),
                                      self.ctx.notify("History cleared",
                                                      "All troubleshooting sessions were "
                                                      "deleted.")),
                          lambda m, d: self.ctx.error("Couldn't clear history", m, d))
        dialog.open_async(done)
