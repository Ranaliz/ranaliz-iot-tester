#!/usr/bin/env python3
"""
Ranaliz iOT Tester
A flexible desktop test tool for Modbus, IEC 60870-5-104, MQTT and Zigbee,
built with PySide6.
"""
import sys
import os
import csv
import time

from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QAction, QColor, QIcon, QFont, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QFileDialog,
    QMessageBox, QCheckBox, QStatusBar, QDialog, QSplitter, QSizePolicy,
    QListWidget, QListWidgetItem, QToolButton, QFrame
)

from modbus_worker import ModbusWorker, FUNCTION_MAP
from formats import (
    single_register_views, decode_modbus_value, DTYPE_REGISTER_COUNT,
    TEXT_VIEW_OPTIONS, text_view, WORD_FORMATS,
)
from excel_export import export_modbus_log_to_excel, export_table_snapshot_to_excel, export_iec104_log_to_excel
from iec104_worker import (
    Iec104ClientWorker, Iec104ServerWorker, MONITORING_TYPES, COMMAND_TYPES, HAS_C104
)
from dialogs import ModbusWriteDialog, Iec104CommandDialog, Iec104AddPointDialog
from branding import build_app_icon, flag_icon, render_logo_pixmap
from theme import (
    QSS, RANALIZ_SUCCESS, RANALIZ_ERROR, RANALIZ_TEXT_MUTED, RANALIZ_ACCENT,
    RANALIZ_CHIP_IDLE, RANALIZ_CHIP_OK_BG, RANALIZ_CHIP_ERR_BG, RANALIZ_BORDER,
)
import history_cache
from i18n import t, init_language, set_language, get_language, SUPPORTED
from mqtt_zigbee_panels import attach_mqtt_zigbee, retranslate_mqtt_zigbee

try:
    import serial.tools.list_ports as list_ports
    HAS_SERIAL_LIST = True
except Exception:
    HAS_SERIAL_LIST = False


APP_TITLE = "Ranaliz iOT Tester"
APP_VERSION = "2.0.5"

FUNCTIONS = [
    "01-Read Coils",
    "02-Read Discrete Inputs",
    "03-Read Holding Registers",
    "04-Read Input Registers",
    "05-Write Single Coil",
    "06-Write Single Register",
    "15-Write Multiple Coils",
    "16-Write Multiple Registers",
]

NUMERIC_DTYPE_OPTIONS = ["Raw (per-register)", "int16", "uint16", "int32", "uint32",
                          "float32", "int64", "uint64", "float64"]
ALL_DISPLAY_OPTIONS = NUMERIC_DTYPE_OPTIONS + TEXT_VIEW_OPTIONS


class RanalizModbusIecWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 960)
        self.setWindowIcon(build_app_icon())
        init_language()

        # ---- Modbus state ----
        self.modbus_worker = ModbusWorker()
        self.modbus_tx_count = 0
        self.modbus_error_count = 0
        self.modbus_is_connected = False
        self._modbus_connecting = False
        self.last_regs = []
        self.last_start_addr = 0
        self.modbus_log_rows = []

        # ---- IEC104 state ----
        self.iec_client_worker = Iec104ClientWorker()
        self.iec_server_worker = Iec104ServerWorker()
        self.iec_client_connected = False
        self._iec_client_connecting = False
        self.iec_server_running = False
        self._iec_server_starting = False
        self.iec_client_points = []   # [{"io_address":.., "type_name":..}]
        self.iec_server_points = []   # [{"io_address":.., "type_name":.., "initial_value":.., "report_ms":..}]
        self.iec_log_rows = []        # unified log for client updates + server activity

        self._build_ui()
        self._build_menu()
        self._wire_modbus_worker()
        self._wire_iec_workers()
        self.retranslate_ui()

    # ------------------------------------------------------------------
    # Top-level UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 12)
        body_layout.setSpacing(10)

        self.protocol_tabs = QTabWidget()
        self.protocol_tabs.addTab(self._build_modbus_tab(), "🔌  " + t("tab_modbus"))
        self.protocol_tabs.addTab(self._build_iec104_tab(), "📡  " + t("tab_iec"))
        attach_mqtt_zigbee(self)
        body_layout.addWidget(self.protocol_tabs)

        root_layout.addWidget(body)
        root_layout.addWidget(self._build_brand_footer())
        self.setStatusBar(QStatusBar())

    def _build_brand_footer(self):
        footer = QFrame()
        footer.setObjectName("BrandFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        self.brand_footer_title = QLabel(t("brand_footer_title", title=APP_TITLE))
        self.brand_footer_title.setObjectName("BrandFooterTitle")
        self.brand_footer_blurb = QLabel(t("brand_blurb"))
        self.brand_footer_blurb.setObjectName("BrandFooterBlurb")
        self.brand_footer_blurb.setWordWrap(True)
        text_col.addWidget(self.brand_footer_title)
        text_col.addWidget(self.brand_footer_blurb)
        layout.addLayout(text_col, stretch=1)

        self.brand_footer_btn = QPushButton(t("brand_visit"))
        self.brand_footer_btn.setObjectName("BrandFooterLink")
        self.brand_footer_btn.setCursor(Qt.PointingHandCursor)
        self.brand_footer_btn.clicked.connect(self.open_ranaliz_website)
        layout.addWidget(self.brand_footer_btn, alignment=Qt.AlignVCenter)
        return footer

    def open_ranaliz_website(self):
        QDesktopServices.openUrl(QUrl("https://ranaliz.com"))

    def _build_header(self):
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(58)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 6, 16, 6)

        logo_label = QLabel()
        logo_label.setPixmap(render_logo_pixmap(height=34))
        layout.addWidget(logo_label)

        layout.addSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(APP_TITLE)
        title.setObjectName("HeaderTitle")
        self.header_subtitle = QLabel(t("app_subtitle"))
        self.header_subtitle.setObjectName("HeaderSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.header_subtitle)
        layout.addLayout(title_box)

        layout.addStretch()

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet("color:#7C93A8; font-size:11px;")
        layout.addWidget(version_label)

        layout.addSpacing(10)
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("HeaderLangCombo")
        self.lang_combo.setFixedWidth(158)
        self.lang_combo.setMinimumHeight(28)
        self.lang_combo.setMaxVisibleItems(3)
        self.lang_combo.view().setMinimumWidth(158)
        # Store language codes as item data; display flag + native labels
        self._lang_combo_codes = ("en", "tr", "ar")
        self._sync_lang_combo(block_signal=True)
        self.lang_combo.currentIndexChanged.connect(self._on_header_lang_changed)
        layout.addWidget(self.lang_combo)
        return header

    def _sync_lang_combo(self, block_signal=False):
        if not hasattr(self, "lang_combo"):
            return
        labels = {
            "en": " English",
            "tr": " Türkçe",
            "ar": " العربية",
        }
        if block_signal:
            self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        current = get_language()
        for code in self._lang_combo_codes:
            self.lang_combo.addItem(flag_icon(code), labels[code], code)
        idx = self._lang_combo_codes.index(current) if current in self._lang_combo_codes else 0
        self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.setMaxVisibleItems(3)
        if block_signal:
            self.lang_combo.blockSignals(False)

    def _on_header_lang_changed(self, index):
        if index < 0:
            return
        code = self.lang_combo.itemData(index)
        if code and code != get_language():
            self.change_language(code)

    def _chip(self, text, color=None):
        lbl = QLabel(text)
        lbl.setProperty("class", "StatusChip")
        lbl.setStyleSheet(
            f"padding:2px 8px; border-radius:8px; background-color:{RANALIZ_CHIP_IDLE}; "
            f"font-weight:600; font-size:11px;" + (f" color:{color};" if color else "")
        )
        return lbl

    def _chip_style(self, kind="idle"):
        if kind == "ok":
            return (
                f"padding:2px 8px; border-radius:8px; background-color:{RANALIZ_CHIP_OK_BG}; "
                f"color:{RANALIZ_SUCCESS}; font-weight:600; font-size:11px;"
            )
        if kind == "err":
            return (
                f"padding:2px 8px; border-radius:8px; background-color:{RANALIZ_CHIP_ERR_BG}; "
                f"color:{RANALIZ_ERROR}; font-weight:600; font-size:11px;"
            )
        return (
            f"padding:2px 8px; border-radius:8px; background-color:{RANALIZ_CHIP_IDLE}; "
            f"color:{RANALIZ_TEXT_MUTED}; font-weight:600; font-size:11px;"
        )

    def _schedule_worker_cleanup(self, worker, grace_ms=500):
        """Release a worker without blocking the GUI thread on QThread.wait()."""
        if worker is None:
            return
        try:
            worker.blockSignals(True)
        except RuntimeError:
            return
        try:
            worker.stop()
        except Exception:
            pass

        try:
            running = worker.isRunning()
        except RuntimeError:
            return

        if not running:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            return

        try:
            worker.finished.connect(worker.deleteLater)
        except (RuntimeError, TypeError):
            pass

        def _force_terminate():
            try:
                if worker.isRunning():
                    worker.terminate()
            except RuntimeError:
                pass

        QTimer.singleShot(grace_ms, _force_terminate)

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.clear()

        self.file_menu = menubar.addMenu(t("menu_file"))
        self.act_export_csv = QAction(t("menu_export_modbus_csv"), self)
        self.act_export_csv.triggered.connect(self.export_modbus_csv)
        self.file_menu.addAction(self.act_export_csv)

        self.act_export_xlsx = QAction(t("menu_export_modbus_xlsx"), self)
        self.act_export_xlsx.triggered.connect(self.export_modbus_excel)
        self.file_menu.addAction(self.act_export_xlsx)

        self.act_export_table = QAction(t("menu_export_table"), self)
        self.act_export_table.triggered.connect(self.export_current_table_excel)
        self.file_menu.addAction(self.act_export_table)

        self.file_menu.addSeparator()
        self.act_export_iec = QAction(t("menu_export_iec"), self)
        self.act_export_iec.triggered.connect(self.export_iec104_excel)
        self.file_menu.addAction(self.act_export_iec)

        self.file_menu.addSeparator()
        self.act_exit = QAction(t("menu_exit"), self)
        self.act_exit.triggered.connect(self.close)
        self.file_menu.addAction(self.act_exit)

        self.setup_menu = menubar.addMenu(t("menu_settings"))
        self.act_reset = QAction(t("menu_reset_counters"), self)
        self.act_reset.triggered.connect(self.reset_counters)
        self.setup_menu.addAction(self.act_reset)

        self.functions_menu = menubar.addMenu(t("menu_functions"))
        for f in FUNCTIONS:
            act = QAction(f, self)
            act.triggered.connect(lambda checked=False, name=f: self.function_combo.setCurrentText(name))
            self.functions_menu.addAction(act)

        self.display_menu = menubar.addMenu(t("menu_display"))
        for label in ["Raw (per-register)", "int32", "uint32", "float32",
                      "Hex (per-register)", "Binary", "ASCII", "UTF-8"]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, d=label: self.dtype_combo.setCurrentText(d))
            self.display_menu.addAction(act)

        self.about_menu = menubar.addMenu(t("menu_about"))
        self.act_about = QAction(t("menu_about_action"), self)
        self.act_about.triggered.connect(self.show_about)
        self.about_menu.addAction(self.act_about)

    def change_language(self, code):
        set_language(code)
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(Qt.RightToLeft if code == "ar" else Qt.LeftToRight)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(APP_TITLE)
        if hasattr(self, "header_subtitle"):
            self.header_subtitle.setText(t("app_subtitle"))
        if hasattr(self, "brand_footer_title"):
            self.brand_footer_title.setText(t("brand_footer_title", title=APP_TITLE))
        if hasattr(self, "brand_footer_blurb"):
            self.brand_footer_blurb.setText(t("brand_blurb"))
        if hasattr(self, "brand_footer_btn"):
            self.brand_footer_btn.setText(t("brand_visit"))
        self._sync_lang_combo(block_signal=True)
        self._build_menu()

        if hasattr(self, "_history_popup_btns"):
            for btn in self._history_popup_btns:
                btn.setToolTip(t("tip_recent"))

        self.protocol_tabs.setTabText(0, "🔌  " + t("tab_modbus"))
        self.protocol_tabs.setTabText(1, "📡  " + t("tab_iec"))
        retranslate_mqtt_zigbee(self)
        if hasattr(self, "conn_group"):
            self.conn_group.setTitle(t("group_connection"))
        if hasattr(self, "modbus_group"):
            self.modbus_group.setTitle(t("group_modbus"))
        if hasattr(self, "values_group"):
            self.values_group.setTitle(t("group_values"))
        if hasattr(self, "conn_tabs"):
            self.conn_tabs.setTabText(0, t("tab_tcp"))
            self.conn_tabs.setTabText(1, t("tab_serial"))

        for attr, key in (
            ("lbl_protocol", "lbl_protocol"), ("lbl_ip", "lbl_ip"), ("lbl_port", "lbl_port"),
            ("lbl_timeout", "lbl_timeout"), ("lbl_delay", "lbl_delay"),
            ("lbl_com", "lbl_com"), ("lbl_baud", "lbl_baud"), ("lbl_data", "lbl_data"),
            ("lbl_parity", "lbl_parity"), ("lbl_stop", "lbl_stop"),
            ("lbl_timeout_short", "lbl_timeout_short"), ("lbl_delay_short", "lbl_delay_short"),
            ("lbl_function", "lbl_function"), ("lbl_slave", "lbl_slave"), ("lbl_start", "lbl_start"),
            ("lbl_count", "lbl_count"), ("lbl_poll", "lbl_poll"), ("lbl_view", "lbl_view"),
            ("lbl_word", "lbl_word"), ("lbl_rtu_ip", "lbl_rtu_ip"),
            ("lbl_iec_port", "lbl_port"), ("lbl_common_addr", "lbl_common_addr"),
            ("lbl_server_port", "lbl_port"), ("lbl_server_ca", "lbl_common_addr"),
        ):
            w = getattr(self, attr, None)
            if w is not None:
                w.setText(t(key))

        if hasattr(self, "connect_btn"):
            if self.modbus_is_connected or self._modbus_connecting:
                self.connect_btn.setText(t("btn_disconnect"))
            else:
                self.connect_btn.setText(t("btn_connect"))
        if hasattr(self, "write_once_btn"):
            self.write_once_btn.setText(t("btn_write"))
        if hasattr(self, "export_xlsx_btn"):
            self.export_xlsx_btn.setText("📊 " + t("btn_export_excel"))
        if hasattr(self, "refresh_ports_btn"):
            self.refresh_ports_btn.setText(t("btn_refresh"))

        self.tx_chip.setText(t("chip_tx", n=self.modbus_tx_count))
        self.err_chip.setText(t("chip_err", n=self.modbus_error_count))
        if self.modbus_is_connected:
            self.conn_chip.setText(t("chip_connected"))
            self.conn_chip.setStyleSheet(self._chip_style("ok"))
        elif self._modbus_connecting:
            self.conn_chip.setText(t("chip_connecting"))
            self.conn_chip.setStyleSheet(self._chip_style("idle"))
        else:
            self.conn_chip.setText(t("chip_idle"))
            self.conn_chip.setStyleSheet(self._chip_style("idle"))

        if hasattr(self, "iec_sub_tabs"):
            self.iec_sub_tabs.setTabText(0, t("tab_iec_client"))
            self.iec_sub_tabs.setTabText(1, t("tab_iec_server"))
        if hasattr(self, "iec_conn_group"):
            self.iec_conn_group.setTitle(t("group_iec_conn_client"))
        if hasattr(self, "iec_points_group"):
            self.iec_points_group.setTitle(t("group_iec_points"))
        if hasattr(self, "iec_log_group"):
            self.iec_log_group.setTitle(t("group_iec_log"))
        if hasattr(self, "iec_server_conn_group"):
            self.iec_server_conn_group.setTitle(t("group_iec_server"))
        if hasattr(self, "iec_server_points_group"):
            self.iec_server_points_group.setTitle(t("group_iec_sim_points"))
        if hasattr(self, "iec_server_log_group"):
            self.iec_server_log_group.setTitle(t("group_iec_server_log"))

        if hasattr(self, "iec_client_connect_btn"):
            if self.iec_client_connected or self._iec_client_connecting:
                self.iec_client_connect_btn.setText(t("btn_disconnect"))
            else:
                self.iec_client_connect_btn.setText(t("btn_connect"))
        if hasattr(self, "iec_gi_btn"):
            self.iec_gi_btn.setText(t("btn_gi"))
        if hasattr(self, "iec_add_point_btn"):
            self.iec_add_point_btn.setText(t("btn_add_point"))
        if hasattr(self, "iec_remove_point_btn"):
            self.iec_remove_point_btn.setText(t("btn_remove"))
        if hasattr(self, "iec_send_cmd_btn"):
            self.iec_send_cmd_btn.setText(t("btn_send_cmd"))
        if hasattr(self, "iec_export_btn"):
            self.iec_export_btn.setText("📊 " + t("btn_export_excel"))

        if hasattr(self, "iec_server_toggle_btn"):
            if self.iec_server_running or self._iec_server_starting:
                self.iec_server_toggle_btn.setText(t("btn_stop_server"))
            else:
                self.iec_server_toggle_btn.setText(t("btn_start_server"))
        if hasattr(self, "iec_server_add_btn"):
            self.iec_server_add_btn.setText(t("btn_add_point"))
        if hasattr(self, "iec_server_remove_btn"):
            self.iec_server_remove_btn.setText(t("btn_remove"))
        if hasattr(self, "iec_server_push_btn"):
            self.iec_server_push_btn.setText(t("btn_push_value"))

        if hasattr(self, "iec_client_chip"):
            if self.iec_client_connected:
                self.iec_client_chip.setText(t("chip_connected"))
            elif self._iec_client_connecting:
                self.iec_client_chip.setText(t("chip_connecting"))
            else:
                self.iec_client_chip.setText(t("chip_idle"))
        if hasattr(self, "iec_server_chip"):
            if self.iec_server_running:
                # keep message part if present
                self.iec_server_chip.setText(t("chip_running", msg=""))
            elif self._iec_server_starting:
                self.iec_server_chip.setText(t("chip_starting"))
            else:
                self.iec_server_chip.setText(t("chip_stopped"))

        if hasattr(self, "c104_warn_label") and self.c104_warn_label is not None:
            self.c104_warn_label.setText("⚠️  " + t("status_c104_missing"))

        if hasattr(self, "iec_log_table"):
            self.iec_log_table.setHorizontalHeaderLabels([
                t("hdr_time"), t("hdr_ca"), t("hdr_io"), t("hdr_type"),
                t("hdr_value"), t("hdr_quality"), t("hdr_cot"),
            ])
        if hasattr(self, "iec_server_log_table"):
            self.iec_server_log_table.setHorizontalHeaderLabels([
                t("hdr_time"), t("hdr_ca"), t("hdr_io"), t("hdr_type"),
                t("hdr_value"), t("hdr_quality"), t("hdr_event"),
            ])

    def show_about(self):
        c104_status = t("c104_ok") if HAS_C104 else t("c104_missing")
        box = QMessageBox(self)
        box.setWindowTitle(t("menu_about").replace("&", ""))
        box.setTextFormat(Qt.RichText)
        box.setText(t("about_body", title=APP_TITLE, version=APP_VERSION, c104=c104_status))
        visit_btn = box.addButton(t("brand_visit"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is visit_btn:
            self.open_ranaliz_website()

    def reset_counters(self):
        self.modbus_tx_count = 0
        self.modbus_error_count = 0
        self.tx_chip.setText(t("chip_tx", n=0))
        self.err_chip.setText(t("chip_err", n=0))

    # ==================================================================
    # MODBUS TAB
    # ==================================================================
    def _build_modbus_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- compact top panel (status + connection + settings) ----
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.tx_chip = self._chip(t("chip_tx", n=0))
        self.err_chip = self._chip(t("chip_err", n=0))
        self.conn_chip = self._chip(t("chip_idle"), color=RANALIZ_TEXT_MUTED)
        for c in (self.tx_chip, self.err_chip, self.conn_chip):
            status_row.addWidget(c)
        status_row.addStretch()
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self._set_status_dot(False)
        status_row.addWidget(self.status_dot)
        top_layout.addLayout(status_row)

        self.conn_group = QGroupBox(t("group_connection"))
        conn_layout = QHBoxLayout(self.conn_group)
        conn_layout.setContentsMargins(6, 4, 6, 4)
        conn_layout.setSpacing(8)

        self.conn_tabs = QTabWidget()
        self.conn_tabs.addTab(self._build_ip_tab(), t("tab_tcp"))
        self.conn_tabs.addTab(self._build_serial_tab(), t("tab_serial"))
        conn_layout.addWidget(self.conn_tabs, stretch=1)

        # Inline connect — no side column / no vertical stretch waste
        self.connect_btn = QPushButton(t("btn_connect"))
        self.connect_btn.setObjectName("PrimaryAction")
        self.connect_btn.setMinimumHeight(32)
        self.connect_btn.setMaximumHeight(32)
        self.connect_btn.setMinimumWidth(100)
        self.connect_btn.setMaximumWidth(120)
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn, 0, Qt.AlignVCenter)

        top_layout.addWidget(self.conn_group)

        self.modbus_group = QGroupBox(t("group_modbus"))
        modbus_layout = QGridLayout(self.modbus_group)
        modbus_layout.setContentsMargins(6, 4, 6, 4)
        modbus_layout.setHorizontalSpacing(10)
        modbus_layout.setVerticalSpacing(1)

        col = 0
        self.lbl_function = self._field_label(t("lbl_function"))
        modbus_layout.addWidget(self.lbl_function, 0, col)
        self.function_combo = QComboBox()
        self.function_combo.addItems(FUNCTIONS)
        self.function_combo.setCurrentText("03-Read Holding Registers")
        self.function_combo.currentTextChanged.connect(self.on_function_changed)
        modbus_layout.addWidget(self.function_combo, 1, col)

        col += 1
        self.write_once_btn = QPushButton(t("btn_write"))
        self.write_once_btn.setObjectName("SecondaryAction")
        self.write_once_btn.clicked.connect(self.open_write_dialog)
        self.write_once_btn.setVisible(False)
        modbus_layout.addWidget(self.write_once_btn, 1, col)

        col += 1
        self.lbl_slave = self._field_label(t("lbl_slave"))
        modbus_layout.addWidget(self.lbl_slave, 0, col)
        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(0, 247)
        self.slave_spin.setValue(1)
        modbus_layout.addWidget(self.slave_spin, 1, col)

        col += 1
        self.lbl_start = self._field_label(t("lbl_start"))
        modbus_layout.addWidget(self.lbl_start, 0, col)
        self.start_addr_combo = QComboBox()
        self.start_addr_combo.setEditable(True)
        self._fill_history_combo(self.start_addr_combo, "start_addresses", "0")
        modbus_layout.addWidget(self._wrap_history_combo(self.start_addr_combo), 1, col)

        col += 1
        self.lbl_count = self._field_label(t("lbl_count"))
        modbus_layout.addWidget(self.lbl_count, 0, col)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 125)
        self.count_spin.setValue(10)
        modbus_layout.addWidget(self.count_spin, 1, col)

        col += 1
        self.lbl_poll = self._field_label(t("lbl_poll"))
        modbus_layout.addWidget(self.lbl_poll, 0, col)
        self.poll_rate_spin = QSpinBox()
        self.poll_rate_spin.setRange(50, 60000)
        self.poll_rate_spin.setSingleStep(50)
        self.poll_rate_spin.setValue(1000)
        modbus_layout.addWidget(self.poll_rate_spin, 1, col)

        col += 1
        self.lbl_view = self._field_label(t("lbl_view"))
        modbus_layout.addWidget(self.lbl_view, 0, col)
        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems(ALL_DISPLAY_OPTIONS)
        self.dtype_combo.currentTextChanged.connect(self.rebuild_table_headers)
        modbus_layout.addWidget(self.dtype_combo, 1, col)

        col += 1
        self.lbl_word = self._field_label(t("lbl_word"))
        modbus_layout.addWidget(self.lbl_word, 0, col)
        self.word_order_combo = QComboBox()
        self.word_order_combo.addItems(list(WORD_FORMATS))
        self.word_order_combo.setCurrentIndex(0)  # ABCD (BIG_ENDIAN) — Ranaliz API default
        self.word_order_combo.setToolTip(
            "ABCD = BIG_ENDIAN (Ranaliz API). "
            "Wrong layout (e.g. BADC) can turn ~50 Hz into ~199588."
        )
        self.word_order_combo.currentTextChanged.connect(self.rebuild_table_headers)
        modbus_layout.addWidget(self.word_order_combo, 1, col)

        for w in (self.slave_spin, self.count_spin, self.poll_rate_spin):
            w.valueChanged.connect(self.apply_poll_settings)
        self.start_addr_combo.currentTextChanged.connect(self.apply_poll_settings)

        top_layout.addWidget(self.modbus_group)

        # ---- values table (dominant area) ----
        self.values_group = QGroupBox(t("group_values"))
        values_layout = QVBoxLayout(self.values_group)
        values_layout.setContentsMargins(6, 4, 6, 6)
        values_layout.setSpacing(4)

        table_toolbar = QHBoxLayout()
        table_toolbar.addStretch()
        self.export_xlsx_btn = QPushButton("📊 " + t("btn_export_excel"))
        self.export_xlsx_btn.setObjectName("SecondaryAction")
        self.export_xlsx_btn.clicked.connect(self.export_modbus_excel)
        table_toolbar.addWidget(self.export_xlsx_btn)
        values_layout.addLayout(table_toolbar)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Adres", "Register Değeri", "Big Endian (BE)", "Little Endian (LE)",
             "BE Swapped", "LE Swapped"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.setMinimumHeight(320)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        values_layout.addWidget(self.table, stretch=1)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_panel)
        splitter.addWidget(self.values_group)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([160, 760])
        layout.addWidget(splitter)

        return tab

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{RANALIZ_TEXT_MUTED}; font-size:10px; font-weight:600;")
        return lbl

    def _wrap_history_combo(self, combo):
        """Editable combo + visible history popup button."""
        combo.setObjectName("HistoryCombo")
        combo.setMaxVisibleItems(10)
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(combo, stretch=1)
        btn = QToolButton()
        btn.setObjectName("HistoryPopupBtn")
        btn.setText("⏱")
        btn.setToolTip(t("tip_recent"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(combo.showPopup)
        row.addWidget(btn)
        if not hasattr(self, "_history_popup_btns"):
            self._history_popup_btns = []
        self._history_popup_btns.append(btn)
        return wrap

    def _fill_history_combo(self, combo, key, default=""):
        items = history_cache.get(key)
        combo.blockSignals(True)
        combo.clear()
        seen = set()
        for item in items:
            if item and item not in seen:
                combo.addItem(item)
                seen.add(item)
        if default and default not in seen:
            combo.insertItem(0, default)
        elif combo.count() == 0 and default:
            combo.addItem(default)
        if combo.count() == 0:
            combo.addItem(default or "")
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _start_address(self):
        try:
            return max(0, min(65535, int(str(self.start_addr_combo.currentText()).strip())))
        except (ValueError, TypeError):
            return 0

    def _remember_modbus_connection(self):
        if self.conn_tabs.currentIndex() == 0:
            history_cache.push("modbus_ips", self.ip_edit.currentText())
            self._fill_history_combo(self.ip_edit, "modbus_ips", self.ip_edit.currentText().strip() or "127.0.0.1")
        else:
            history_cache.push("com_ports", self.com_combo.currentText())
        history_cache.push("start_addresses", str(self._start_address()))
        cur = str(self._start_address())
        self._fill_history_combo(self.start_addr_combo, "start_addresses", cur)
        self.start_addr_combo.setCurrentText(cur)

    def _remember_iec_connection(self):
        history_cache.push("iec_ips", self.iec_client_ip_edit.currentText())
        self._fill_history_combo(
            self.iec_client_ip_edit, "iec_ips",
            self.iec_client_ip_edit.currentText().strip() or "127.0.0.1",
        )


    def _build_ip_tab(self):
        w = QWidget()
        layout = QGridLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(1)

        self.lbl_protocol = self._field_label(t("lbl_protocol"))
        layout.addWidget(self.lbl_protocol, 0, 0)
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["TCP", "UDP"])
        layout.addWidget(self.protocol_combo, 1, 0)

        self.lbl_ip = self._field_label(t("lbl_ip"))
        layout.addWidget(self.lbl_ip, 0, 1)
        self.ip_edit = QComboBox()
        self.ip_edit.setEditable(True)
        self._fill_history_combo(self.ip_edit, "modbus_ips", "127.0.0.1")
        layout.addWidget(self._wrap_history_combo(self.ip_edit), 1, 1)

        self.lbl_port = self._field_label(t("lbl_port"))
        layout.addWidget(self.lbl_port, 0, 2)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        layout.addWidget(self.port_spin, 1, 2)

        self.lbl_timeout = self._field_label(t("lbl_timeout"))
        layout.addWidget(self.lbl_timeout, 0, 3)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 60000)
        self.timeout_spin.setSingleStep(100)
        self.timeout_spin.setValue(3000)
        layout.addWidget(self.timeout_spin, 1, 3)

        self.lbl_delay = self._field_label(t("lbl_delay"))
        layout.addWidget(self.lbl_delay, 0, 4)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60000)
        self.delay_spin.setValue(25)
        layout.addWidget(self.delay_spin, 1, 4)

        layout.setColumnStretch(1, 1)
        return w

    def _build_serial_tab(self):
        w = QWidget()
        layout = QGridLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(1)

        self.lbl_com = self._field_label(t("lbl_com"))
        layout.addWidget(self.lbl_com, 0, 0)
        self.com_combo = QComboBox()
        self.com_combo.setEditable(True)
        self._refresh_serial_ports()
        layout.addWidget(self._wrap_history_combo(self.com_combo), 1, 0)

        self.refresh_ports_btn = QPushButton(t("btn_refresh"))
        self.refresh_ports_btn.setObjectName("SecondaryAction")
        self.refresh_ports_btn.clicked.connect(self._refresh_serial_ports)
        layout.addWidget(self.refresh_ports_btn, 1, 1)

        self.lbl_baud = self._field_label(t("lbl_baud"))
        layout.addWidget(self.lbl_baud, 0, 2)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["1200", "2400", "4800", "9600", "19200",
                                   "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("9600")
        layout.addWidget(self.baud_combo, 1, 2)

        self.lbl_data = self._field_label(t("lbl_data"))
        layout.addWidget(self.lbl_data, 0, 3)
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        layout.addWidget(self.databits_combo, 1, 3)

        self.lbl_parity = self._field_label(t("lbl_parity"))
        layout.addWidget(self.lbl_parity, 0, 4)
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd"])
        layout.addWidget(self.parity_combo, 1, 4)

        self.lbl_stop = self._field_label(t("lbl_stop"))
        layout.addWidget(self.lbl_stop, 0, 5)
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        layout.addWidget(self.stopbits_combo, 1, 5)

        self.lbl_timeout_short = self._field_label(t("lbl_timeout_short"))
        layout.addWidget(self.lbl_timeout_short, 0, 6)
        self.serial_timeout_spin = QSpinBox()
        self.serial_timeout_spin.setRange(100, 60000)
        self.serial_timeout_spin.setSingleStep(100)
        self.serial_timeout_spin.setValue(1000)
        layout.addWidget(self.serial_timeout_spin, 1, 6)

        self.lbl_delay_short = self._field_label(t("lbl_delay_short"))
        layout.addWidget(self.lbl_delay_short, 0, 7)
        self.serial_delay_spin = QSpinBox()
        self.serial_delay_spin.setRange(0, 60000)
        self.serial_delay_spin.setValue(25)
        layout.addWidget(self.serial_delay_spin, 1, 7)

        layout.setColumnStretch(0, 1)
        return w

    def _refresh_serial_ports(self):
        current = self.com_combo.currentText().strip() if self.com_combo.count() or self.com_combo.isEditable() else ""
        discovered = []
        if HAS_SERIAL_LIST:
            discovered = [p.device for p in list_ports.comports()]
        hist = history_cache.get("com_ports")
        merged = []
        for p in hist + discovered:
            if p and p not in merged:
                merged.append(p)
        self.com_combo.blockSignals(True)
        self.com_combo.clear()
        self.com_combo.addItems(merged if merged else ["/dev/ttyUSB0"])
        if current:
            idx = self.com_combo.findText(current)
            if idx >= 0:
                self.com_combo.setCurrentIndex(idx)
            else:
                self.com_combo.setEditText(current)
        self.com_combo.blockSignals(False)
        if hasattr(self, "zigbee_com_combo"):
            from mqtt_zigbee_panels import refresh_zigbee_ports
            refresh_zigbee_ports(self)

    def _set_status_dot(self, connected):
        color = RANALIZ_SUCCESS if connected else RANALIZ_TEXT_MUTED
        self.status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 5px; border: 1px solid {RANALIZ_BORDER};"
        )

    def _wire_modbus_worker(self):
        self.modbus_worker.connected_signal.connect(self.on_modbus_connected)
        self.modbus_worker.disconnected_signal.connect(self.on_modbus_disconnected)
        self.modbus_worker.data_signal.connect(self.on_modbus_data)
        self.modbus_worker.error_signal.connect(self.on_modbus_error)
        self.modbus_worker.tx_count_signal.connect(self.on_modbus_tx_count)

    # ---------------- connection lifecycle ----------------
    def toggle_connection(self):
        # Allow cancel while still connecting to an unreachable host
        if self.modbus_is_connected or self._modbus_connecting:
            self.connect_btn.setEnabled(False)
            self.connect_btn.setText(t("btn_disconnecting"))
            self._modbus_connecting = False
            self._teardown_modbus_worker()
            self.on_modbus_disconnected()
        else:
            self.start_modbus_connection()

    def _teardown_modbus_worker(self):
        old_worker = getattr(self, "modbus_worker", None)
        self.modbus_worker = None
        self._schedule_worker_cleanup(old_worker)

    def start_modbus_connection(self):
        self._teardown_modbus_worker()

        tab_index = self.conn_tabs.currentIndex()
        self.modbus_worker = ModbusWorker()
        self._wire_modbus_worker()

        if tab_index == 0:
            self.modbus_worker.configure_tcp(
                self.ip_edit.currentText().strip(),
                self.port_spin.value(),
                self.timeout_spin.value(),
                self.delay_spin.value(),
                protocol=self.protocol_combo.currentText(),
            )
        else:
            parity_map = {"None": "N", "Even": "E", "Odd": "O"}
            stopbits_map = {"1": 1, "1.5": 1.5, "2": 2}
            self.modbus_worker.configure_serial(
                self.com_combo.currentText(),
                self.baud_combo.currentText(),
                self.databits_combo.currentText(),
                parity_map[self.parity_combo.currentText()],
                stopbits_map[self.stopbits_combo.currentText()],
                self.serial_timeout_spin.value(),
                self.serial_delay_spin.value(),
            )

        self.apply_poll_settings()
        self._remember_modbus_connection()
        self._modbus_connecting = True
        # Keep button enabled so the user can cancel a hanging connect immediately
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText(t("btn_disconnect"))
        self.connect_btn.setObjectName("DangerAction")
        self._repolish(self.connect_btn)
        self.conn_chip.setText(t("chip_connecting"))
        self.conn_chip.setStyleSheet(self._chip_style("idle"))
        self.modbus_worker.start()

    def apply_poll_settings(self):
        if self.modbus_worker is None:
            return
        self.modbus_worker.configure_poll(
            self.function_combo.currentText(),
            self.slave_spin.value(),
            self._start_address(),
            self.count_spin.value(),
            self.poll_rate_spin.value(),
        )

    def on_modbus_connected(self, ok, message):
        self._modbus_connecting = False
        self.connect_btn.setEnabled(True)
        if ok:
            self.modbus_is_connected = True
            self.connect_btn.setText(t("btn_disconnect"))
            self.connect_btn.setObjectName("DangerAction")
            self.connect_btn.setStyleSheet("")  # force re-polish
            self.conn_chip.setText(t("chip_connected"))
            self.conn_chip.setStyleSheet(self._chip_style("ok"))
            self._set_status_dot(True)
            self.statusBar().showMessage(message, 3000)
        else:
            self.modbus_is_connected = False
            self.connect_btn.setText(t("btn_connect"))
            self.connect_btn.setObjectName("PrimaryAction")
            self.connect_btn.setStyleSheet("")
            self.conn_chip.setText(t("chip_error"))
            self.conn_chip.setStyleSheet(self._chip_style("err"))
            self._set_status_dot(False)
            QMessageBox.warning(self, t("msg_conn_failed"), message)
        self._repolish(self.connect_btn)

    def _repolish(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def on_modbus_disconnected(self):
        self._modbus_connecting = False
        self.modbus_is_connected = False
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText(t("btn_connect"))
        self.connect_btn.setObjectName("PrimaryAction")
        self._repolish(self.connect_btn)
        self.conn_chip.setText(t("chip_idle"))
        self.conn_chip.setStyleSheet(self._chip_style("idle"))
        self._set_status_dot(False)

    def on_modbus_error(self, msg):
        self.modbus_error_count += 1
        self.err_chip.setText(t("chip_err", n=self.modbus_error_count))
        self.statusBar().showMessage(msg, 4000)

    def on_modbus_tx_count(self, count):
        self.tx_chip.setText(t("chip_tx", n=count))

    # ---------------- function / write handling ----------------
    def on_function_changed(self, text):
        kind = FUNCTION_MAP.get(text)
        is_write_only = kind in ("write_coil", "write_register", "write_coils", "write_registers")
        self.write_once_btn.setVisible(is_write_only)
        self.apply_poll_settings()

    def open_write_dialog(self):
        kind = FUNCTION_MAP.get(self.function_combo.currentText())
        dlg = ModbusWriteDialog(self, kind, self.slave_spin.value(), self._start_address())
        if dlg.exec() == QDialog.Accepted:
            try:
                slave, addr, val = dlg.get_values()
            except ValueError:
                QMessageBox.warning(self, t("msg_invalid"), t("msg_check_values"))
                return
            if not self.modbus_is_connected:
                QMessageBox.warning(self, t("msg_not_connected"), t("msg_connect_first"))
                return
            self.modbus_worker.slave_id = slave
            self.modbus_worker.queue_write(kind, addr, val)
            self.statusBar().showMessage(t("msg_write_queued", kind=kind, addr=addr, val=val), 3000)

    # ---------------- data / table handling ----------------
    def rebuild_table_headers(self):
        display = self.dtype_combo.currentText()
        if display == "Raw (per-register)":
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels(
                ["Adres", "Register Değeri", "Big Endian (BE)", "Little Endian (LE)",
                 "BE Swapped", "LE Swapped"]
            )
        elif display in TEXT_VIEW_OPTIONS:
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Başlangıç Adresi", "Adet", f"Değer ({display})"])
        else:
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(
                ["Başlangıç Adresi", "Kullanılan Register", f"Değer ({display})", "Registers", "Hex"]
            )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self.last_regs:
            self.render_table(self.last_regs, self.last_start_addr)

    def on_modbus_data(self, values, start_addr):
        self.last_regs = values
        self.last_start_addr = start_addr
        self.render_table(values, start_addr)
        self.record_history(values, start_addr)

    def render_table(self, values, start_addr):
        kind = FUNCTION_MAP.get(self.function_combo.currentText())
        display = self.dtype_combo.currentText()

        if kind in ("coils", "discrete"):
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Adres", "Değer"])
            self.table.setRowCount(len(values))
            for i, v in enumerate(values):
                self.table.setItem(i, 0, QTableWidgetItem(str(start_addr + i)))
                item = QTableWidgetItem("1 (ON)" if v else "0 (OFF)")
                item.setForeground(QColor(RANALIZ_SUCCESS if v else RANALIZ_TEXT_MUTED))
                self.table.setItem(i, 1, item)
            return

        if display == "Raw (per-register)":
            self.table.setRowCount(len(values))
            for i, reg in enumerate(values):
                views = single_register_views(reg)
                addr = start_addr + i
                row_items = [str(addr), str(reg), str(views["be"]), str(views["le"]),
                             str(views["be_swapped"]), str(views["le_swapped"])]
                for c, text in enumerate(row_items):
                    self.table.setItem(i, c, QTableWidgetItem(text))

        elif display in TEXT_VIEW_OPTIONS:
            # text views operate on the whole block as one string, but we also
            # show a per-register breakdown row-by-row for hex/binary for convenience
            self.table.setRowCount(1)
            rendered = text_view(values, display)
            self.table.setItem(0, 0, QTableWidgetItem(str(start_addr)))
            self.table.setItem(0, 1, QTableWidgetItem(str(len(values))))
            item = QTableWidgetItem(rendered)
            item.setFont(QFont("Consolas, Menlo, monospace", 10))
            self.table.setItem(0, 2, item)

        else:
            reg_count = DTYPE_REGISTER_COUNT.get(display, 1)
            word_format = self.word_order_combo.currentText()
            rows = []
            i = 0
            while i + reg_count <= len(values):
                chunk = values[i:i + reg_count]
                val = decode_modbus_value(chunk, display, word_format=word_format)
                hex_str = " ".join(f"{r:04X}" for r in chunk)
                raw_dec = ", ".join(str(int(r) & 0xFFFF) for r in chunk)
                rows.append((start_addr + i, reg_count, val, raw_dec, hex_str))
                i += reg_count
            self.table.setRowCount(len(rows))
            for r, (addr, cnt, val, raw_dec, hex_str) in enumerate(rows):
                self.table.setItem(r, 0, QTableWidgetItem(str(addr)))
                self.table.setItem(r, 1, QTableWidgetItem(str(cnt)))
                self.table.setItem(r, 2, QTableWidgetItem(str(val)))
                self.table.setItem(r, 3, QTableWidgetItem(raw_dec))
                self.table.setItem(r, 4, QTableWidgetItem(hex_str))

    def record_history(self, values, start_addr):
        self.modbus_log_rows.append((time.strftime("%Y-%m-%d %H:%M:%S"), start_addr, list(values)))
        if len(self.modbus_log_rows) > 20000:
            self.modbus_log_rows.pop(0)

    def show_table_context_menu(self, pos):
        menu = QMenu(self)
        numeric_menu = menu.addMenu("Sayısal Format")
        for label in NUMERIC_DTYPE_OPTIONS:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, d=label: self.dtype_combo.setCurrentText(d))
            numeric_menu.addAction(act)
        text_menu = menu.addMenu("Metin / Hex / Binary")
        for label in TEXT_VIEW_OPTIONS:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, d=label: self.dtype_combo.setCurrentText(d))
            text_menu.addAction(act)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---------------- export ----------------
    def export_modbus_csv(self):
        if not self.modbus_log_rows:
            QMessageBox.information(self, t("msg_no_data"), t("msg_no_modbus_log"))
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV Olarak Dışa Aktar", "modbus_log.csv", "CSV Dosyaları (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Zaman Damgası", "Başlangıç Adresi", "Değerler"])
            for ts, addr, vals in self.modbus_log_rows:
                writer.writerow([ts, addr, ";".join(map(str, vals))])
        QMessageBox.information(self, t("msg_exported"), t("msg_exported_to", path=path))

    def export_modbus_excel(self):
        if not self.modbus_log_rows:
            QMessageBox.information(self, t("msg_no_data"), t("msg_no_modbus_log"))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Excel Olarak Dışa Aktar", "modbus_log.xlsx", "Excel Dosyaları (*.xlsx)")
        if not path:
            return
        meta = {
            "Protokol": self.protocol_combo.currentText() if self.conn_tabs.currentIndex() == 0 else "Serial (RTU)",
            "IP/Port veya COM": self.ip_edit.currentText() if self.conn_tabs.currentIndex() == 0 else self.com_combo.currentText(),
            "Fonksiyon": self.function_combo.currentText(),
            "Slave Id": self.slave_spin.value(),
            "Başlangıç Adresi": self._start_address(),
            "Adet": self.count_spin.value(),
            "Poll Aralığı (ms)": self.poll_rate_spin.value(),
            "Kayıt Sayısı": len(self.modbus_log_rows),
        }
        try:
            export_modbus_log_to_excel(path, self.modbus_log_rows, meta=meta)
            QMessageBox.information(self, t("msg_exported"), t("msg_excel_created", path=path))
        except Exception as e:
            QMessageBox.critical(self, t("msg_error"), t("msg_excel_error", e=e))

    def export_current_table_excel(self):
        if self.table.rowCount() == 0:
            QMessageBox.information(self, t("msg_no_data"), t("msg_no_table"))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Tabloyu Excel'e Aktar", "modbus_snapshot.xlsx", "Excel Dosyaları (*.xlsx)")
        if not path:
            return
        headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]
        rows = []
        for r in range(self.table.rowCount()):
            row = []
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                row.append(item.text() if item else "")
            rows.append(row)
        try:
            export_table_snapshot_to_excel(path, headers, rows)
            QMessageBox.information(self, t("msg_exported"), t("msg_excel_created", path=path))
        except Exception as e:
            QMessageBox.critical(self, t("msg_error"), t("msg_excel_error", e=e))


    # ==================================================================
    # IEC 60870-5-104 TAB
    # ==================================================================
    def _build_iec104_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        self.c104_warn_label = None
        if not HAS_C104:
            self.c104_warn_label = QLabel("⚠️  " + t("status_c104_missing"))
            self.c104_warn_label.setStyleSheet(
                "background:#3A2A10; color:#FBBF24; padding:12px; border-radius:8px; font-weight:600;"
            )
            layout.addWidget(self.c104_warn_label)

        self.iec_sub_tabs = QTabWidget()
        self.iec_sub_tabs.addTab(self._build_iec_client_tab(), t("tab_iec_client"))
        self.iec_sub_tabs.addTab(self._build_iec_server_tab(), t("tab_iec_server"))
        layout.addWidget(self.iec_sub_tabs, stretch=1)

        return tab

    # ---------------- IEC 104 Client sub-tab ----------------
    def _build_iec_client_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        status_row = QHBoxLayout()
        self.iec_client_chip = self._chip(t("chip_idle"), color=RANALIZ_TEXT_MUTED)
        status_row.addWidget(self.iec_client_chip)
        status_row.addStretch()
        top_layout.addLayout(status_row)

        self.iec_conn_group = QGroupBox(t("group_iec_conn_client"))
        conn_layout = QGridLayout(self.iec_conn_group)
        conn_layout.setContentsMargins(6, 4, 6, 4)
        conn_layout.setHorizontalSpacing(10)
        conn_layout.setVerticalSpacing(1)

        self.lbl_rtu_ip = self._field_label(t("lbl_rtu_ip"))
        conn_layout.addWidget(self.lbl_rtu_ip, 0, 0)
        self.iec_client_ip_edit = QComboBox()
        self.iec_client_ip_edit.setEditable(True)
        self._fill_history_combo(self.iec_client_ip_edit, "iec_ips", "127.0.0.1")
        conn_layout.addWidget(self._wrap_history_combo(self.iec_client_ip_edit), 1, 0)

        self.lbl_iec_port = self._field_label(t("lbl_port"))
        conn_layout.addWidget(self.lbl_iec_port, 0, 1)
        self.iec_client_port_spin = QSpinBox()
        self.iec_client_port_spin.setRange(1, 65535)
        self.iec_client_port_spin.setValue(2404)
        conn_layout.addWidget(self.iec_client_port_spin, 1, 1)

        self.lbl_common_addr = self._field_label(t("lbl_common_addr"))
        conn_layout.addWidget(self.lbl_common_addr, 0, 2)
        self.iec_client_ca_spin = QSpinBox()
        self.iec_client_ca_spin.setRange(1, 65534)
        self.iec_client_ca_spin.setValue(1)
        conn_layout.addWidget(self.iec_client_ca_spin, 1, 2)

        # IP column ~25% more horizontal share than equal columns
        conn_layout.setColumnStretch(0, 5)
        conn_layout.setColumnStretch(1, 2)
        conn_layout.setColumnStretch(2, 2)
        conn_layout.setColumnStretch(3, 1)

        self.iec_client_connect_btn = QPushButton(t("btn_connect"))
        self.iec_client_connect_btn.setObjectName("PrimaryAction")
        self.iec_client_connect_btn.setMinimumHeight(32)
        self.iec_client_connect_btn.setMaximumHeight(32)
        self.iec_client_connect_btn.clicked.connect(self.toggle_iec_client_connection)
        conn_layout.addWidget(self.iec_client_connect_btn, 1, 4)

        self.iec_gi_btn = QPushButton(t("btn_gi"))
        self.iec_gi_btn.setObjectName("SecondaryAction")
        self.iec_gi_btn.setMinimumHeight(32)
        self.iec_gi_btn.setMaximumHeight(32)
        self.iec_gi_btn.clicked.connect(self.send_general_interrogation)
        conn_layout.addWidget(self.iec_gi_btn, 1, 5)

        top_layout.addWidget(self.iec_conn_group)

        self.iec_points_group = QGroupBox(t("group_iec_points"))
        points_layout = QVBoxLayout(self.iec_points_group)
        points_layout.setContentsMargins(6, 4, 6, 4)
        points_layout.setSpacing(2)

        points_toolbar = QHBoxLayout()
        self.iec_add_point_btn = QPushButton(t("btn_add_point"))
        self.iec_add_point_btn.setObjectName("SecondaryAction")
        self.iec_add_point_btn.clicked.connect(self.add_iec_client_point)
        self.iec_remove_point_btn = QPushButton(t("btn_remove"))
        self.iec_remove_point_btn.setObjectName("SecondaryAction")
        self.iec_remove_point_btn.clicked.connect(self.remove_iec_client_point)
        self.iec_send_cmd_btn = QPushButton(t("btn_send_cmd"))
        self.iec_send_cmd_btn.setObjectName("PrimaryAction")
        self.iec_send_cmd_btn.setMinimumHeight(32)
        self.iec_send_cmd_btn.setMaximumHeight(32)
        self.iec_send_cmd_btn.clicked.connect(self.open_iec_command_dialog)
        points_toolbar.addWidget(self.iec_add_point_btn)
        points_toolbar.addWidget(self.iec_remove_point_btn)
        points_toolbar.addStretch()
        points_toolbar.addWidget(self.iec_send_cmd_btn)
        points_layout.addLayout(points_toolbar)

        self.iec_client_points_list = QListWidget()
        self.iec_client_points_list.setMaximumHeight(56)
        points_layout.addWidget(self.iec_client_points_list)

        top_layout.addWidget(self.iec_points_group)

        self.iec_log_group = QGroupBox(t("group_iec_log"))
        log_layout = QVBoxLayout(self.iec_log_group)
        log_layout.setContentsMargins(6, 4, 6, 6)
        log_layout.setSpacing(4)

        log_toolbar = QHBoxLayout()
        log_toolbar.addStretch()
        self.iec_export_btn = QPushButton("📊 " + t("btn_export_excel"))
        self.iec_export_btn.setObjectName("SecondaryAction")
        self.iec_export_btn.clicked.connect(self.export_iec104_excel)
        log_toolbar.addWidget(self.iec_export_btn)
        log_layout.addLayout(log_toolbar)

        self.iec_log_table = QTableWidget()
        self.iec_log_table.setAlternatingRowColors(True)
        self.iec_log_table.setColumnCount(7)
        self.iec_log_table.setHorizontalHeaderLabels(
            [t("hdr_time"), t("hdr_ca"), t("hdr_io"), t("hdr_type"),
             t("hdr_value"), t("hdr_quality"), t("hdr_cot")]
        )
        self.iec_log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.iec_log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.iec_log_table.setMinimumHeight(320)
        self.iec_log_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.iec_log_table, stretch=1)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_panel)
        splitter.addWidget(self.iec_log_group)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([160, 760])
        layout.addWidget(splitter)

        return tab

    def _build_iec_server_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        status_row = QHBoxLayout()
        self.iec_server_chip = self._chip(t("chip_stopped"), color=RANALIZ_TEXT_MUTED)
        status_row.addWidget(self.iec_server_chip)
        status_row.addStretch()
        top_layout.addLayout(status_row)

        self.iec_server_conn_group = QGroupBox(t("group_iec_server"))
        conn_layout = QGridLayout(self.iec_server_conn_group)
        conn_layout.setContentsMargins(6, 4, 6, 4)
        conn_layout.setHorizontalSpacing(10)
        conn_layout.setVerticalSpacing(1)

        self.lbl_server_port = self._field_label(t("lbl_port"))
        conn_layout.addWidget(self.lbl_server_port, 0, 0)
        self.iec_server_port_spin = QSpinBox()
        self.iec_server_port_spin.setRange(1, 65535)
        self.iec_server_port_spin.setValue(2404)
        conn_layout.addWidget(self.iec_server_port_spin, 1, 0)

        self.lbl_server_ca = self._field_label(t("lbl_common_addr"))
        conn_layout.addWidget(self.lbl_server_ca, 0, 1)
        self.iec_server_ca_spin = QSpinBox()
        self.iec_server_ca_spin.setRange(1, 65534)
        self.iec_server_ca_spin.setValue(1)
        conn_layout.addWidget(self.iec_server_ca_spin, 1, 1)

        conn_layout.setColumnStretch(2, 1)

        self.iec_server_toggle_btn = QPushButton(t("btn_start_server"))
        self.iec_server_toggle_btn.setObjectName("PrimaryAction")
        self.iec_server_toggle_btn.setMinimumHeight(32)
        self.iec_server_toggle_btn.setMaximumHeight(32)
        self.iec_server_toggle_btn.clicked.connect(self.toggle_iec_server)
        conn_layout.addWidget(self.iec_server_toggle_btn, 1, 3)

        top_layout.addWidget(self.iec_server_conn_group)

        self.iec_server_points_group = QGroupBox(t("group_iec_sim_points"))
        points_layout = QVBoxLayout(self.iec_server_points_group)
        points_layout.setContentsMargins(6, 4, 6, 4)
        points_layout.setSpacing(2)

        points_toolbar = QHBoxLayout()
        self.iec_server_add_btn = QPushButton(t("btn_add_point"))
        self.iec_server_add_btn.setObjectName("SecondaryAction")
        self.iec_server_add_btn.clicked.connect(self.add_iec_server_point)
        self.iec_server_remove_btn = QPushButton(t("btn_remove"))
        self.iec_server_remove_btn.setObjectName("SecondaryAction")
        self.iec_server_remove_btn.clicked.connect(self.remove_iec_server_point)
        self.iec_server_push_btn = QPushButton(t("btn_push_value"))
        self.iec_server_push_btn.setObjectName("PrimaryAction")
        self.iec_server_push_btn.setMinimumHeight(32)
        self.iec_server_push_btn.setMaximumHeight(32)
        self.iec_server_push_btn.clicked.connect(self.push_iec_server_value)
        points_toolbar.addWidget(self.iec_server_add_btn)
        points_toolbar.addWidget(self.iec_server_remove_btn)
        points_toolbar.addStretch()
        points_toolbar.addWidget(self.iec_server_push_btn)
        points_layout.addLayout(points_toolbar)

        self.iec_server_points_list = QListWidget()
        self.iec_server_points_list.setMaximumHeight(56)
        points_layout.addWidget(self.iec_server_points_list)

        top_layout.addWidget(self.iec_server_points_group)

        self.iec_server_log_group = QGroupBox(t("group_iec_server_log"))
        log_layout = QVBoxLayout(self.iec_server_log_group)
        log_layout.setContentsMargins(6, 4, 6, 6)
        log_layout.setSpacing(4)
        self.iec_server_log_table = QTableWidget()
        self.iec_server_log_table.setAlternatingRowColors(True)
        self.iec_server_log_table.setColumnCount(7)
        self.iec_server_log_table.setHorizontalHeaderLabels(
            [t("hdr_time"), t("hdr_ca"), t("hdr_io"), t("hdr_type"),
             t("hdr_value"), t("hdr_quality"), t("hdr_event")]
        )
        self.iec_server_log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.iec_server_log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.iec_server_log_table.setMinimumHeight(320)
        self.iec_server_log_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.iec_server_log_table, stretch=1)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_panel)
        splitter.addWidget(self.iec_server_log_group)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([160, 760])
        layout.addWidget(splitter)

        return tab

    def _wire_iec_workers(self):
        self.iec_client_worker.connected_signal.connect(self.on_iec_client_connected)
        self.iec_client_worker.disconnected_signal.connect(self.on_iec_client_disconnected)
        self.iec_client_worker.point_update_signal.connect(self.on_iec_client_update)
        self.iec_client_worker.error_signal.connect(self.on_iec_error)
        self.iec_client_worker.log_signal.connect(self.on_iec_log)

        self.iec_server_worker.started_signal.connect(self.on_iec_server_started)
        self.iec_server_worker.stopped_signal.connect(self.on_iec_server_stopped)
        self.iec_server_worker.activity_signal.connect(self.on_iec_server_activity)
        self.iec_server_worker.error_signal.connect(self.on_iec_error)

    def on_iec_error(self, msg):
        self.statusBar().showMessage(f"IEC104: {msg}", 5000)

    def on_iec_log(self, msg):
        self.statusBar().showMessage(f"IEC104: {msg}", 4000)

    # ---------------- Client point management ----------------
    def add_iec_client_point(self):
        dlg = Iec104AddPointDialog(self, MONITORING_TYPES, is_server=False)
        if dlg.exec() == QDialog.Accepted:
            type_label, io_addr = dlg.get_values()
            type_name = MONITORING_TYPES[type_label]
            self.iec_client_points.append({"io_address": io_addr, "type_name": type_name})
            self.iec_client_points_list.addItem(QListWidgetItem(f"IO {io_addr}  —  {type_label}"))

    def remove_iec_client_point(self):
        row = self.iec_client_points_list.currentRow()
        if row >= 0:
            self.iec_client_points_list.takeItem(row)
            del self.iec_client_points[row]

    def toggle_iec_client_connection(self):
        if self.iec_client_connected or self._iec_client_connecting:
            self._iec_client_connecting = False
            self._teardown_iec_client_worker()
            self.on_iec_client_disconnected()
        else:
            if not self.iec_client_points:
                QMessageBox.warning(self, t("msg_no_points"), t("msg_add_point_first"))
                return
            self._teardown_iec_client_worker()
            self.iec_client_worker = Iec104ClientWorker()
            self.iec_client_worker.connected_signal.connect(self.on_iec_client_connected)
            self.iec_client_worker.disconnected_signal.connect(self.on_iec_client_disconnected)
            self.iec_client_worker.point_update_signal.connect(self.on_iec_client_update)
            self.iec_client_worker.error_signal.connect(self.on_iec_error)
            self.iec_client_worker.log_signal.connect(self.on_iec_log)
            self.iec_client_worker.configure(
                self.iec_client_ip_edit.currentText().strip(),
                self.iec_client_port_spin.value(),
                self.iec_client_ca_spin.value(),
                list(self.iec_client_points),
            )
            self._remember_iec_connection()
            self._iec_client_connecting = True
            self.iec_client_connect_btn.setEnabled(True)
            self.iec_client_connect_btn.setText(t("btn_disconnect"))
            self.iec_client_connect_btn.setObjectName("DangerAction")
            self._repolish(self.iec_client_connect_btn)
            self.iec_client_chip.setText(t("chip_connecting"))
            self.iec_client_chip.setStyleSheet(self._chip_style("idle"))
            self.iec_client_worker.start()

    def _teardown_iec_client_worker(self):
        old_worker = getattr(self, "iec_client_worker", None)
        self.iec_client_worker = None
        self._schedule_worker_cleanup(old_worker)

    def on_iec_client_connected(self, ok, message):
        self._iec_client_connecting = False
        self.iec_client_connect_btn.setEnabled(True)
        if ok:
            self.iec_client_connected = True
            self.iec_client_connect_btn.setText(t("btn_disconnect"))
            self.iec_client_connect_btn.setObjectName("DangerAction")
            self.iec_client_chip.setText(t("chip_connected"))
            self.iec_client_chip.setStyleSheet(self._chip_style("ok"))
        else:
            self.iec_client_connected = False
            self.iec_client_connect_btn.setText(t("btn_connect"))
            self.iec_client_connect_btn.setObjectName("PrimaryAction")
            self.iec_client_chip.setText(t("chip_error"))
            self.iec_client_chip.setStyleSheet(self._chip_style("err"))
            QMessageBox.warning(self, t("msg_conn_failed"), message)
        self._repolish(self.iec_client_connect_btn)

    def on_iec_client_disconnected(self):
        self._iec_client_connecting = False
        self.iec_client_connected = False
        self.iec_client_connect_btn.setEnabled(True)
        self.iec_client_connect_btn.setText(t("btn_connect"))
        self.iec_client_connect_btn.setObjectName("PrimaryAction")
        self._repolish(self.iec_client_connect_btn)
        self.iec_client_chip.setText(t("chip_idle"))
        self.iec_client_chip.setStyleSheet(self._chip_style("idle"))

    def on_iec_client_update(self, entry):
        self.iec_log_rows.append(entry)
        if len(self.iec_log_rows) > 20000:
            self.iec_log_rows.pop(0)
        self._append_iec_log_row(self.iec_log_table, entry)

    def _append_iec_log_row(self, table, entry):
        row = table.rowCount()
        table.insertRow(row)
        values = [entry.get("timestamp", ""), entry.get("common_address", ""),
                  entry.get("io_address", ""), entry.get("type", ""),
                  str(entry.get("value", "")), entry.get("quality", ""), entry.get("cot", "")]
        for c, v in enumerate(values):
            table.setItem(row, c, QTableWidgetItem(str(v)))
        table.scrollToBottom()
        # cap displayed rows to keep UI snappy
        while table.rowCount() > 500:
            table.removeRow(0)

    def send_general_interrogation(self):
        if not self.iec_client_connected:
            QMessageBox.warning(self, t("msg_not_connected"), t("msg_connect_rtu"))
            return
        self.iec_client_worker.queue_interrogation()

    def open_iec_command_dialog(self):
        if not self.iec_client_connected:
            QMessageBox.warning(self, t("msg_not_connected"), t("msg_connect_rtu"))
            return
        dlg = Iec104CommandDialog(self, COMMAND_TYPES)
        if dlg.exec() == QDialog.Accepted:
            type_label, io_addr, value = dlg.get_values()
            type_name = COMMAND_TYPES[type_label]
            self.iec_client_worker.queue_command(io_addr, type_name, value)

    # ---------------- Server point management ----------------
    def add_iec_server_point(self):
        combined_types = {**MONITORING_TYPES, **COMMAND_TYPES}
        dlg = Iec104AddPointDialog(self, combined_types, is_server=True)
        if dlg.exec() == QDialog.Accepted:
            type_label, io_addr, initial_value, report_ms = dlg.get_values()
            type_name = combined_types[type_label]
            self.iec_server_points.append({
                "io_address": io_addr, "type_name": type_name,
                "initial_value": initial_value, "report_ms": report_ms,
            })
            extra = f"  (başlangıç={initial_value}, rapor={report_ms}ms)" if initial_value is not None or report_ms else ""
            self.iec_server_points_list.addItem(QListWidgetItem(f"IO {io_addr}  —  {type_label}{extra}"))

    def remove_iec_server_point(self):
        row = self.iec_server_points_list.currentRow()
        if row >= 0:
            self.iec_server_points_list.takeItem(row)
            del self.iec_server_points[row]

    def toggle_iec_server(self):
        if self.iec_server_running or self._iec_server_starting:
            self._iec_server_starting = False
            self._teardown_iec_server_worker()
            self.on_iec_server_stopped()
        else:
            if not self.iec_server_points:
                QMessageBox.warning(self, t("msg_no_points"), t("msg_add_sim_point"))
                return
            self._teardown_iec_server_worker()
            self.iec_server_worker = Iec104ServerWorker()
            self.iec_server_worker.started_signal.connect(self.on_iec_server_started)
            self.iec_server_worker.stopped_signal.connect(self.on_iec_server_stopped)
            self.iec_server_worker.activity_signal.connect(self.on_iec_server_activity)
            self.iec_server_worker.error_signal.connect(self.on_iec_error)
            self.iec_server_worker.configure(
                self.iec_server_port_spin.value(),
                self.iec_server_ca_spin.value(),
                list(self.iec_server_points),
            )
            self._iec_server_starting = True
            self.iec_server_toggle_btn.setEnabled(True)
            self.iec_server_toggle_btn.setText(t("btn_stop_server"))
            self.iec_server_toggle_btn.setObjectName("DangerAction")
            self._repolish(self.iec_server_toggle_btn)
            self.iec_server_chip.setText(t("chip_starting"))
            self.iec_server_chip.setStyleSheet(self._chip_style("idle"))
            self.iec_server_worker.start()

    def _teardown_iec_server_worker(self):
        old_worker = getattr(self, "iec_server_worker", None)
        self.iec_server_worker = None
        self._schedule_worker_cleanup(old_worker)

    def on_iec_server_started(self, ok, message):
        self._iec_server_starting = False
        self.iec_server_toggle_btn.setEnabled(True)
        if ok:
            self.iec_server_running = True
            self.iec_server_toggle_btn.setText(t("btn_stop_server"))
            self.iec_server_toggle_btn.setObjectName("DangerAction")
            self.iec_server_chip.setText(t("chip_running", msg=message))
            self.iec_server_chip.setStyleSheet(self._chip_style("ok"))
        else:
            self.iec_server_running = False
            self.iec_server_toggle_btn.setText(t("btn_start_server"))
            self.iec_server_toggle_btn.setObjectName("PrimaryAction")
            self.iec_server_chip.setText(t("chip_error"))
            self.iec_server_chip.setStyleSheet(self._chip_style("err"))
            QMessageBox.warning(self, t("msg_start_failed"), message)
        self._repolish(self.iec_server_toggle_btn)

    def on_iec_server_stopped(self):
        self._iec_server_starting = False
        self.iec_server_running = False
        self.iec_server_toggle_btn.setEnabled(True)
        self.iec_server_toggle_btn.setText(t("btn_start_server"))
        self.iec_server_toggle_btn.setObjectName("PrimaryAction")
        self._repolish(self.iec_server_toggle_btn)
        self.iec_server_chip.setText(t("chip_stopped"))
        self.iec_server_chip.setStyleSheet(self._chip_style("idle"))

    def on_iec_server_activity(self, entry):
        self.iec_log_rows.append(entry)
        if len(self.iec_log_rows) > 20000:
            self.iec_log_rows.pop(0)
        self._append_iec_log_row(self.iec_server_log_table, entry)

    def push_iec_server_value(self):
        if not self.iec_server_running:
            QMessageBox.warning(self, t("msg_server_not_running"), t("msg_start_server_first"))
            return
        row = self.iec_server_points_list.currentRow()
        if row < 0 or row >= len(self.iec_server_points):
            QMessageBox.warning(self, t("msg_no_point_selected"), t("msg_select_point"))
            return
        point_cfg = self.iec_server_points[row]
        dlg = Iec104CommandDialog(self, {"Seçili Nokta": point_cfg["type_name"]})
        dlg.setWindowTitle("Değer Gönder (Spontane)")
        dlg.io_spin.setValue(point_cfg["io_address"])
        dlg.io_spin.setEnabled(False)
        dlg.type_combo.setEnabled(False)
        if dlg.exec() == QDialog.Accepted:
            _, io_addr, value = dlg.get_values()
            self.iec_server_worker.set_point_value(io_addr, value)

    # ---------------- IEC104 export ----------------
    def export_iec104_excel(self):
        if not self.iec_log_rows:
            QMessageBox.information(self, t("msg_no_data"), t("msg_no_iec_log"))
            return
        path, _ = QFileDialog.getSaveFileName(self, "IEC 104 Kaydını Excel'e Aktar", "iec104_log.xlsx", "Excel Dosyaları (*.xlsx)")
        if not path:
            return
        meta = {
            "Client IP": self.iec_client_ip_edit.currentText(),
            "Client Port": self.iec_client_port_spin.value(),
            "Server Port": self.iec_server_port_spin.value(),
            "Kayıt Sayısı": len(self.iec_log_rows),
        }
        try:
            export_iec104_log_to_excel(path, self.iec_log_rows, meta=meta)
            QMessageBox.information(self, t("msg_exported"), t("msg_excel_created", path=path))
        except Exception as e:
            QMessageBox.critical(self, t("msg_error"), t("msg_excel_error", e=e))

    # ==================================================================
    # Shutdown
    # ==================================================================
    def closeEvent(self, event):
        workers = []
        for attr in ("modbus_worker", "iec_client_worker", "iec_server_worker",
                     "mqtt_worker", "zigbee_worker"):
            w = getattr(self, attr, None)
            setattr(self, attr, None)
            if w is not None:
                workers.append(w)
                try:
                    w.blockSignals(True)
                    w.stop()
                except Exception:
                    pass
        # On quit, force-kill any still-blocked connect() threads quickly
        for w in workers:
            try:
                if w.isRunning():
                    w.terminate()
                    w.wait(150)
            except RuntimeError:
                pass
            try:
                w.deleteLater()
            except RuntimeError:
                pass
        event.accept()


def main():
    lang = init_language()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft if lang == "ar" else Qt.LeftToRight)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(build_app_icon())
    win = RanalizModbusIecWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
