"""
MQTT and Zigbee protocol tab builders + handlers mixed into the main window.
Call attach_mqtt_zigbee(window) after core UI widgets exist.
"""
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QComboBox, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QSplitter, QListWidget, QListWidgetItem, QPlainTextEdit,
    QMessageBox, QAbstractItemView,
)

from i18n import t
from theme import RANALIZ_TEXT_MUTED, RANALIZ_BORDER
import history_cache
from mqtt_worker import MqttWorker, HAS_PAHO
from zigbee_worker import ZigbeeWorker, HAS_ZIGPY, DEFAULT_BAUD, probe_radios

try:
    import serial.tools.list_ports as list_ports
    HAS_SERIAL_LIST = True
except Exception:
    HAS_SERIAL_LIST = False


def attach_mqtt_zigbee(win):
    """Create workers, build tabs, wire signals. Mutates win in place."""
    win.mqtt_worker = MqttWorker()
    win.zigbee_worker = ZigbeeWorker()
    win.mqtt_connected = False
    win._mqtt_connecting = False
    win.zigbee_connected = False
    win._zigbee_connecting = False
    win._zigbee_devices = []

    win.protocol_tabs.addTab(build_mqtt_tab(win), "📨  " + t("tab_mqtt"))
    win.protocol_tabs.addTab(build_zigbee_tab(win), "📡  " + t("tab_zigbee"))
    wire_mqtt_worker(win)
    wire_zigbee_worker(win)


def build_mqtt_tab(win):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setSpacing(8)

    if not HAS_PAHO:
        warn = QLabel("⚠️  " + t("status_paho_missing"))
        warn.setObjectName("MqttWarn")
        warn.setStyleSheet(
            "background:#3A2A10; color:#FBBF24; padding:12px; border-radius:8px; font-weight:600;"
        )
        win.mqtt_warn_label = warn
        layout.addWidget(warn)
    else:
        win.mqtt_warn_label = None

    status_row = QHBoxLayout()
    win.mqtt_chip = win._chip(t("chip_idle"), color=RANALIZ_TEXT_MUTED)
    status_row.addWidget(win.mqtt_chip)
    status_row.addStretch()
    layout.addLayout(status_row)

    win.mqtt_conn_group = QGroupBox(t("group_mqtt_conn"))
    conn = QGridLayout(win.mqtt_conn_group)
    conn.setContentsMargins(6, 4, 6, 4)
    conn.setHorizontalSpacing(10)
    conn.setVerticalSpacing(1)

    win.lbl_mqtt_host = win._field_label(t("lbl_ip"))
    conn.addWidget(win.lbl_mqtt_host, 0, 0)
    win.mqtt_host_edit = QComboBox()
    win.mqtt_host_edit.setEditable(True)
    win._fill_history_combo(win.mqtt_host_edit, "mqtt_hosts", "127.0.0.1")
    conn.addWidget(win._wrap_history_combo(win.mqtt_host_edit), 1, 0)

    win.lbl_mqtt_port = win._field_label(t("lbl_port"))
    conn.addWidget(win.lbl_mqtt_port, 0, 1)
    win.mqtt_port_spin = QSpinBox()
    win.mqtt_port_spin.setRange(1, 65535)
    win.mqtt_port_spin.setValue(1883)
    conn.addWidget(win.mqtt_port_spin, 1, 1)

    win.lbl_mqtt_client_id = win._field_label(t("lbl_client_id"))
    conn.addWidget(win.lbl_mqtt_client_id, 0, 2)
    win.mqtt_client_id_edit = QLineEdit("ranaliz-mqtt")
    conn.addWidget(win.mqtt_client_id_edit, 1, 2)

    win.lbl_mqtt_user = win._field_label(t("lbl_username"))
    conn.addWidget(win.lbl_mqtt_user, 0, 3)
    win.mqtt_user_edit = QLineEdit()
    conn.addWidget(win.mqtt_user_edit, 1, 3)

    win.lbl_mqtt_pass = win._field_label(t("lbl_password"))
    conn.addWidget(win.lbl_mqtt_pass, 0, 4)
    win.mqtt_pass_edit = QLineEdit()
    win.mqtt_pass_edit.setEchoMode(QLineEdit.Password)
    conn.addWidget(win.mqtt_pass_edit, 1, 4)

    win.mqtt_tls_check = QCheckBox(t("lbl_tls"))
    conn.addWidget(win.mqtt_tls_check, 1, 5)

    win.mqtt_connect_btn = QPushButton(t("btn_connect"))
    win.mqtt_connect_btn.setObjectName("PrimaryAction")
    win.mqtt_connect_btn.setMinimumHeight(32)
    win.mqtt_connect_btn.clicked.connect(lambda: toggle_mqtt_connection(win))
    conn.addWidget(win.mqtt_connect_btn, 1, 6)

    conn.setColumnStretch(0, 4)
    layout.addWidget(win.mqtt_conn_group)

    mid = QHBoxLayout()
    win.mqtt_sub_group = QGroupBox(t("group_mqtt_sub"))
    sub_l = QVBoxLayout(win.mqtt_sub_group)
    sub_row = QHBoxLayout()
    win.lbl_mqtt_sub_topic = win._field_label(t("lbl_topic"))
    win.mqtt_sub_topic_edit = QLineEdit("#")
    win.lbl_mqtt_sub_qos = win._field_label(t("lbl_qos"))
    win.mqtt_sub_qos_spin = QSpinBox()
    win.mqtt_sub_qos_spin.setRange(0, 2)
    win.mqtt_sub_btn = QPushButton(t("btn_subscribe"))
    win.mqtt_sub_btn.setObjectName("SecondaryAction")
    win.mqtt_sub_btn.clicked.connect(lambda: mqtt_subscribe(win))
    win.mqtt_unsub_btn = QPushButton(t("btn_unsubscribe"))
    win.mqtt_unsub_btn.setObjectName("SecondaryAction")
    win.mqtt_unsub_btn.clicked.connect(lambda: mqtt_unsubscribe(win))
    sub_row.addWidget(win.mqtt_sub_topic_edit, stretch=1)
    sub_row.addWidget(win.mqtt_sub_qos_spin)
    sub_row.addWidget(win.mqtt_sub_btn)
    sub_row.addWidget(win.mqtt_unsub_btn)
    sub_l.addLayout(sub_row)
    win.mqtt_sub_list = QListWidget()
    win.mqtt_sub_list.setMaximumHeight(100)
    sub_l.addWidget(win.mqtt_sub_list)
    mid.addWidget(win.mqtt_sub_group, stretch=1)

    win.mqtt_pub_group = QGroupBox(t("group_mqtt_pub"))
    pub_l = QGridLayout(win.mqtt_pub_group)
    win.lbl_mqtt_pub_topic = win._field_label(t("lbl_topic"))
    pub_l.addWidget(win.lbl_mqtt_pub_topic, 0, 0)
    win.mqtt_pub_topic_edit = QLineEdit("ranaliz/test")
    pub_l.addWidget(win.mqtt_pub_topic_edit, 1, 0)
    win.lbl_mqtt_payload = win._field_label(t("lbl_payload"))
    pub_l.addWidget(win.lbl_mqtt_payload, 0, 1)
    win.mqtt_payload_edit = QLineEdit("hello")
    pub_l.addWidget(win.mqtt_payload_edit, 1, 1)
    win.lbl_mqtt_pub_qos = win._field_label(t("lbl_qos"))
    pub_l.addWidget(win.lbl_mqtt_pub_qos, 0, 2)
    win.mqtt_pub_qos_spin = QSpinBox()
    win.mqtt_pub_qos_spin.setRange(0, 2)
    pub_l.addWidget(win.mqtt_pub_qos_spin, 1, 2)
    win.mqtt_retain_check = QCheckBox(t("lbl_retain"))
    pub_l.addWidget(win.mqtt_retain_check, 1, 3)
    win.mqtt_pub_btn = QPushButton(t("btn_publish"))
    win.mqtt_pub_btn.setObjectName("PrimaryAction")
    win.mqtt_pub_btn.clicked.connect(lambda: mqtt_publish(win))
    pub_l.addWidget(win.mqtt_pub_btn, 1, 4)
    pub_l.setColumnStretch(0, 2)
    pub_l.setColumnStretch(1, 3)
    mid.addWidget(win.mqtt_pub_group, stretch=1)
    layout.addLayout(mid)

    win.mqtt_msg_group = QGroupBox(t("group_mqtt_msg"))
    msg_l = QVBoxLayout(win.mqtt_msg_group)
    win.mqtt_msg_table = QTableWidget(0, 5)
    win.mqtt_msg_table.setHorizontalHeaderLabels(
        [t("hdr_time"), t("hdr_topic"), t("hdr_qos"), t("hdr_retain"), t("hdr_payload")]
    )
    win.mqtt_msg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    win.mqtt_msg_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
    win.mqtt_msg_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    win.mqtt_msg_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    msg_l.addWidget(win.mqtt_msg_table)
    layout.addWidget(win.mqtt_msg_group, stretch=1)
    return tab


def build_zigbee_tab(win):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setSpacing(8)

    radios = probe_radios()
    if not any(radios.values()):
        warn = QLabel("⚠️  " + t("status_zigpy_missing"))
        warn.setStyleSheet(
            "background:#3A2A10; color:#FBBF24; padding:12px; border-radius:8px; font-weight:600;"
        )
        win.zigbee_warn_label = warn
        layout.addWidget(warn)
    else:
        win.zigbee_warn_label = None

    status_row = QHBoxLayout()
    win.zigbee_chip = win._chip(t("chip_idle"), color=RANALIZ_TEXT_MUTED)
    status_row.addWidget(win.zigbee_chip)
    status_row.addStretch()
    layout.addLayout(status_row)

    win.zigbee_conn_group = QGroupBox(t("group_zigbee_conn"))
    conn = QGridLayout(win.zigbee_conn_group)
    conn.setContentsMargins(6, 4, 6, 4)
    conn.setHorizontalSpacing(10)
    conn.setVerticalSpacing(1)

    win.lbl_zigbee_radio = win._field_label(t("lbl_radio"))
    conn.addWidget(win.lbl_zigbee_radio, 0, 0)
    win.zigbee_radio_combo = QComboBox()
    for key, label in (
        ("znp", "ZNP (CC2652/CC2531)"),
        ("ezsp", "EZSP (Silicon Labs)"),
        ("deconz", "deCONZ (ConBee)"),
    ):
        win.zigbee_radio_combo.addItem(label, key)
        if not radios.get(key):
            # still list, connect will fail clearly
            pass
    win.zigbee_radio_combo.currentIndexChanged.connect(lambda *_: _zigbee_radio_changed(win))
    conn.addWidget(win.zigbee_radio_combo, 1, 0)

    win.lbl_zigbee_com = win._field_label(t("lbl_com"))
    conn.addWidget(win.lbl_zigbee_com, 0, 1)
    win.zigbee_com_combo = QComboBox()
    win.zigbee_com_combo.setEditable(True)
    conn.addWidget(win.zigbee_com_combo, 1, 1)

    win.zigbee_refresh_ports_btn = QPushButton(t("btn_refresh"))
    win.zigbee_refresh_ports_btn.setObjectName("SecondaryAction")
    win.zigbee_refresh_ports_btn.clicked.connect(lambda: refresh_zigbee_ports(win))
    conn.addWidget(win.zigbee_refresh_ports_btn, 1, 2)

    win.lbl_zigbee_baud = win._field_label(t("lbl_baud"))
    conn.addWidget(win.lbl_zigbee_baud, 0, 3)
    win.zigbee_baud_combo = QComboBox()
    win.zigbee_baud_combo.addItems(["38400", "57600", "115200", "230400"])
    conn.addWidget(win.zigbee_baud_combo, 1, 3)

    win.lbl_zigbee_permit = win._field_label(t("lbl_permit_s"))
    conn.addWidget(win.lbl_zigbee_permit, 0, 4)
    win.zigbee_permit_spin = QSpinBox()
    win.zigbee_permit_spin.setRange(1, 254)
    win.zigbee_permit_spin.setValue(60)
    conn.addWidget(win.zigbee_permit_spin, 1, 4)

    win.zigbee_permit_btn = QPushButton(t("btn_permit_join"))
    win.zigbee_permit_btn.setObjectName("SecondaryAction")
    win.zigbee_permit_btn.clicked.connect(lambda: zigbee_permit_join(win))
    conn.addWidget(win.zigbee_permit_btn, 1, 5)

    win.zigbee_refresh_dev_btn = QPushButton(t("btn_refresh_devices"))
    win.zigbee_refresh_dev_btn.setObjectName("SecondaryAction")
    win.zigbee_refresh_dev_btn.clicked.connect(lambda: zigbee_refresh_devices(win))
    conn.addWidget(win.zigbee_refresh_dev_btn, 1, 6)

    win.zigbee_connect_btn = QPushButton(t("btn_connect"))
    win.zigbee_connect_btn.setObjectName("PrimaryAction")
    win.zigbee_connect_btn.setMinimumHeight(32)
    win.zigbee_connect_btn.clicked.connect(lambda: toggle_zigbee_connection(win))
    conn.addWidget(win.zigbee_connect_btn, 1, 7)

    layout.addWidget(win.zigbee_conn_group)
    refresh_zigbee_ports(win)
    _zigbee_radio_changed(win)

    split = QSplitter(Qt.Vertical)

    win.zigbee_dev_group = QGroupBox(t("group_zigbee_devices"))
    dev_l = QVBoxLayout(win.zigbee_dev_group)
    win.zigbee_dev_table = QTableWidget(0, 5)
    win.zigbee_dev_table.setHorizontalHeaderLabels(
        [t("hdr_ieee"), t("hdr_nwk"), t("hdr_mfr"), t("hdr_model"), t("hdr_endpoints")]
    )
    win.zigbee_dev_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    win.zigbee_dev_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    win.zigbee_dev_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    win.zigbee_dev_table.itemSelectionChanged.connect(lambda: zigbee_device_selected(win))
    dev_l.addWidget(win.zigbee_dev_table)
    split.addWidget(win.zigbee_dev_group)

    bottom = QWidget()
    bottom_l = QHBoxLayout(bottom)
    bottom_l.setContentsMargins(0, 0, 0, 0)

    win.zigbee_attr_group = QGroupBox(t("group_zigbee_attr"))
    attr = QGridLayout(win.zigbee_attr_group)
    win.lbl_zigbee_ep = win._field_label(t("lbl_endpoint"))
    attr.addWidget(win.lbl_zigbee_ep, 0, 0)
    win.zigbee_ep_spin = QSpinBox()
    win.zigbee_ep_spin.setRange(1, 255)
    win.zigbee_ep_spin.setValue(1)
    attr.addWidget(win.zigbee_ep_spin, 1, 0)
    win.lbl_zigbee_cluster = win._field_label(t("lbl_cluster"))
    attr.addWidget(win.lbl_zigbee_cluster, 0, 1)
    win.zigbee_cluster_edit = QLineEdit("0x0000")
    attr.addWidget(win.zigbee_cluster_edit, 1, 1)
    win.lbl_zigbee_attr = win._field_label(t("lbl_attr"))
    attr.addWidget(win.lbl_zigbee_attr, 0, 2)
    win.zigbee_attr_edit = QLineEdit("0x0004")
    attr.addWidget(win.zigbee_attr_edit, 1, 2)
    win.lbl_zigbee_val = win._field_label(t("lbl_attr_value"))
    attr.addWidget(win.lbl_zigbee_val, 0, 3)
    win.zigbee_value_edit = QLineEdit()
    attr.addWidget(win.zigbee_value_edit, 1, 3)
    win.zigbee_read_btn = QPushButton(t("btn_read_attr"))
    win.zigbee_read_btn.setObjectName("SecondaryAction")
    win.zigbee_read_btn.clicked.connect(lambda: zigbee_read_attr(win))
    attr.addWidget(win.zigbee_read_btn, 1, 4)
    win.zigbee_write_btn = QPushButton(t("btn_write_attr"))
    win.zigbee_write_btn.setObjectName("PrimaryAction")
    win.zigbee_write_btn.clicked.connect(lambda: zigbee_write_attr(win))
    attr.addWidget(win.zigbee_write_btn, 1, 5)
    bottom_l.addWidget(win.zigbee_attr_group, stretch=2)

    win.zigbee_log_group = QGroupBox(t("group_zigbee_log"))
    log_l = QVBoxLayout(win.zigbee_log_group)
    win.zigbee_log = QPlainTextEdit()
    win.zigbee_log.setReadOnly(True)
    win.zigbee_log.setMaximumBlockCount(500)
    log_l.addWidget(win.zigbee_log)
    bottom_l.addWidget(win.zigbee_log_group, stretch=1)

    split.addWidget(bottom)
    split.setStretchFactor(0, 3)
    split.setStretchFactor(1, 2)
    layout.addWidget(split, stretch=1)
    return tab


def wire_mqtt_worker(win):
    w = win.mqtt_worker
    w.connected_signal.connect(lambda ok, msg: on_mqtt_connected(win, ok, msg))
    w.disconnected_signal.connect(lambda: on_mqtt_disconnected(win))
    w.message_signal.connect(lambda topic, payload, qos, retain: on_mqtt_message(win, topic, payload, qos, retain))
    w.error_signal.connect(lambda msg: win.statusBar().showMessage(f"MQTT: {msg}", 5000))
    w.log_signal.connect(lambda msg: win.statusBar().showMessage(f"MQTT: {msg}", 3000))


def wire_zigbee_worker(win):
    w = win.zigbee_worker
    w.connected_signal.connect(lambda ok, msg: on_zigbee_connected(win, ok, msg))
    w.disconnected_signal.connect(lambda: on_zigbee_disconnected(win))
    w.device_list_signal.connect(lambda devices: on_zigbee_devices(win, devices))
    w.device_joined_signal.connect(lambda info: zigbee_append_log(win, f"Joined {info.get('ieee')}"))
    w.attr_result_signal.connect(lambda d: on_zigbee_attr(win, d))
    w.error_signal.connect(lambda msg: (win.statusBar().showMessage(f"Zigbee: {msg}", 6000), zigbee_append_log(win, msg)))
    w.log_signal.connect(lambda msg: zigbee_append_log(win, msg))


def toggle_mqtt_connection(win):
    if win.mqtt_connected or win._mqtt_connecting:
        win._mqtt_connecting = False
        win.mqtt_connect_btn.setText(t("btn_disconnecting"))
        win.mqtt_connect_btn.setEnabled(False)
        old = win.mqtt_worker
        win.mqtt_worker = MqttWorker()
        wire_mqtt_worker(win)
        win._schedule_worker_cleanup(old)
        win.mqtt_connected = False
        win.mqtt_chip.setText(t("chip_idle"))
        win.mqtt_chip.setStyleSheet(win._chip_style("idle"))
        win.mqtt_connect_btn.setText(t("btn_connect"))
        win.mqtt_connect_btn.setEnabled(True)
        return

    if not HAS_PAHO:
        QMessageBox.warning(win, t("msg_error"), t("status_paho_missing"))
        return

    host = win.mqtt_host_edit.currentText().strip()
    win.mqtt_worker.configure(
        host=host,
        port=win.mqtt_port_spin.value(),
        client_id=win.mqtt_client_id_edit.text().strip() or "ranaliz-mqtt",
        username=win.mqtt_user_edit.text(),
        password=win.mqtt_pass_edit.text(),
        use_tls=win.mqtt_tls_check.isChecked(),
    )
    history_cache.push("mqtt_hosts", host)
    win._fill_history_combo(win.mqtt_host_edit, "mqtt_hosts", host or "127.0.0.1")
    win._mqtt_connecting = True
    win.mqtt_chip.setText(t("chip_connecting"))
    win.mqtt_chip.setStyleSheet(win._chip_style("idle"))
    win.mqtt_connect_btn.setText(t("btn_disconnect"))
    win.mqtt_worker.start()


def on_mqtt_connected(win, ok, msg):
    win._mqtt_connecting = False
    if ok:
        win.mqtt_connected = True
        win.mqtt_chip.setText(t("chip_connected"))
        win.mqtt_chip.setStyleSheet(win._chip_style("ok"))
        win.statusBar().showMessage(msg, 4000)
    else:
        win.mqtt_connected = False
        win.mqtt_chip.setText(t("chip_error"))
        win.mqtt_chip.setStyleSheet(win._chip_style("err"))
        win.mqtt_connect_btn.setText(t("btn_connect"))
        QMessageBox.warning(win, t("msg_conn_failed"), msg)


def on_mqtt_disconnected(win):
    win.mqtt_connected = False
    win._mqtt_connecting = False
    win.mqtt_chip.setText(t("chip_idle"))
    win.mqtt_chip.setStyleSheet(win._chip_style("idle"))
    win.mqtt_connect_btn.setText(t("btn_connect"))
    win.mqtt_connect_btn.setEnabled(True)


def mqtt_subscribe(win):
    if not win.mqtt_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    topic = win.mqtt_sub_topic_edit.text().strip()
    if not topic:
        QMessageBox.warning(win, t("msg_invalid"), t("msg_mqtt_topic_required"))
        return
    qos = win.mqtt_sub_qos_spin.value()
    win.mqtt_worker.subscribe(topic, qos)
    label = f"{topic}  (QoS {qos})"
    if win.mqtt_sub_list.findItems(label, Qt.MatchExactly):
        return
    # replace same topic different qos
    for i in range(win.mqtt_sub_list.count()):
        if win.mqtt_sub_list.item(i).text().startswith(topic + "  "):
            win.mqtt_sub_list.takeItem(i)
            break
    item = QListWidgetItem(label)
    item.setData(Qt.UserRole, topic)
    win.mqtt_sub_list.addItem(item)


def mqtt_unsubscribe(win):
    if not win.mqtt_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    item = win.mqtt_sub_list.currentItem()
    if item is None:
        QMessageBox.information(win, t("msg_no_point_selected"), t("msg_select_subscription"))
        return
    topic = item.data(Qt.UserRole) or item.text().split("  ")[0]
    win.mqtt_worker.unsubscribe(topic)
    row = win.mqtt_sub_list.row(item)
    win.mqtt_sub_list.takeItem(row)


def mqtt_publish(win):
    if not win.mqtt_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    topic = win.mqtt_pub_topic_edit.text().strip()
    if not topic:
        QMessageBox.warning(win, t("msg_invalid"), t("msg_mqtt_topic_required"))
        return
    win.mqtt_worker.publish(
        topic,
        win.mqtt_payload_edit.text(),
        qos=win.mqtt_pub_qos_spin.value(),
        retain=win.mqtt_retain_check.isChecked(),
    )


def on_mqtt_message(win, topic, payload, qos, retain):
    row = win.mqtt_msg_table.rowCount()
    win.mqtt_msg_table.insertRow(row)
    stamp = time.strftime("%H:%M:%S")
    values = [stamp, topic, str(qos), "1" if retain else "0", payload]
    for col, val in enumerate(values):
        win.mqtt_msg_table.setItem(row, col, QTableWidgetItem(val))
    win.mqtt_msg_table.scrollToBottom()
    # keep last 500
    while win.mqtt_msg_table.rowCount() > 500:
        win.mqtt_msg_table.removeRow(0)


def _zigbee_radio_changed(win):
    radio = win.zigbee_radio_combo.currentData()
    baud = str(DEFAULT_BAUD.get(radio, 115200))
    idx = win.zigbee_baud_combo.findText(baud)
    if idx >= 0:
        win.zigbee_baud_combo.setCurrentIndex(idx)


def refresh_zigbee_ports(win):
    current = win.zigbee_com_combo.currentText().strip() if win.zigbee_com_combo.count() or win.zigbee_com_combo.isEditable() else ""
    discovered = []
    if HAS_SERIAL_LIST:
        discovered = [p.device for p in list_ports.comports()]
    hist = history_cache.get("com_ports")
    merged = []
    for p in hist + discovered:
        if p and p not in merged:
            merged.append(p)
    win.zigbee_com_combo.blockSignals(True)
    win.zigbee_com_combo.clear()
    win.zigbee_com_combo.addItems(merged if merged else ["/dev/ttyUSB0"])
    if current:
        idx = win.zigbee_com_combo.findText(current)
        if idx >= 0:
            win.zigbee_com_combo.setCurrentIndex(idx)
        else:
            win.zigbee_com_combo.setEditText(current)
    win.zigbee_com_combo.blockSignals(False)


def toggle_zigbee_connection(win):
    if win.zigbee_connected or win._zigbee_connecting:
        win._zigbee_connecting = False
        win.zigbee_connect_btn.setText(t("btn_disconnecting"))
        win.zigbee_connect_btn.setEnabled(False)
        old = win.zigbee_worker
        win.zigbee_worker = ZigbeeWorker()
        wire_zigbee_worker(win)
        win._schedule_worker_cleanup(old)
        win.zigbee_connected = False
        win.zigbee_chip.setText(t("chip_idle"))
        win.zigbee_chip.setStyleSheet(win._chip_style("idle"))
        win.zigbee_connect_btn.setText(t("btn_connect"))
        win.zigbee_connect_btn.setEnabled(True)
        return

    if not HAS_ZIGPY:
        QMessageBox.warning(win, t("msg_error"), t("status_zigpy_missing"))
        return

    port = win.zigbee_com_combo.currentText().strip()
    if not port:
        QMessageBox.warning(win, t("msg_invalid"), t("msg_zigbee_port"))
        return

    radio = win.zigbee_radio_combo.currentData() or "znp"
    baud = int(win.zigbee_baud_combo.currentText())
    win.zigbee_worker.configure(radio, port, baud)
    history_cache.push("com_ports", port)
    win._zigbee_connecting = True
    win.zigbee_chip.setText(t("chip_connecting"))
    win.zigbee_chip.setStyleSheet(win._chip_style("idle"))
    win.zigbee_connect_btn.setText(t("btn_disconnect"))
    zigbee_append_log(win, f"Connecting {radio} on {port}…")
    win.zigbee_worker.start()


def on_zigbee_connected(win, ok, msg):
    win._zigbee_connecting = False
    if ok:
        win.zigbee_connected = True
        win.zigbee_chip.setText(t("chip_connected"))
        win.zigbee_chip.setStyleSheet(win._chip_style("ok"))
        zigbee_append_log(win, msg)
    else:
        win.zigbee_connected = False
        win.zigbee_chip.setText(t("chip_error"))
        win.zigbee_chip.setStyleSheet(win._chip_style("err"))
        win.zigbee_connect_btn.setText(t("btn_connect"))
        zigbee_append_log(win, msg)
        QMessageBox.warning(win, t("msg_conn_failed"), msg)


def on_zigbee_disconnected(win):
    win.zigbee_connected = False
    win._zigbee_connecting = False
    win.zigbee_chip.setText(t("chip_idle"))
    win.zigbee_chip.setStyleSheet(win._chip_style("idle"))
    win.zigbee_connect_btn.setText(t("btn_connect"))
    win.zigbee_connect_btn.setEnabled(True)


def on_zigbee_devices(win, devices):
    win._zigbee_devices = devices or []
    win.zigbee_dev_table.setRowCount(0)
    for d in win._zigbee_devices:
        row = win.zigbee_dev_table.rowCount()
        win.zigbee_dev_table.insertRow(row)
        eps = ",".join(str(e["id"]) for e in d.get("endpoints", []))
        vals = [d.get("ieee", ""), f"0x{d.get('nwk', 0):04X}", d.get("manufacturer", ""), d.get("model", ""), eps]
        for col, val in enumerate(vals):
            win.zigbee_dev_table.setItem(row, col, QTableWidgetItem(val))


def zigbee_device_selected(win):
    rows = win.zigbee_dev_table.selectionModel().selectedRows()
    if not rows:
        return
    idx = rows[0].row()
    if idx < 0 or idx >= len(win._zigbee_devices):
        return
    d = win._zigbee_devices[idx]
    eps = d.get("endpoints") or []
    if eps:
        win.zigbee_ep_spin.setValue(int(eps[0]["id"]))
        in_c = eps[0].get("in_clusters") or []
        if in_c:
            win.zigbee_cluster_edit.setText(f"0x{in_c[0]:04X}")


def zigbee_permit_join(win):
    if not win.zigbee_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    win.zigbee_worker.permit_join(win.zigbee_permit_spin.value())


def zigbee_refresh_devices(win):
    if not win.zigbee_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    win.zigbee_worker.refresh_devices()


def _selected_ieee(win):
    rows = win.zigbee_dev_table.selectionModel().selectedRows()
    if not rows:
        return None
    item = win.zigbee_dev_table.item(rows[0].row(), 0)
    return item.text() if item else None


def _parse_hex_int(text, default=0):
    raw = (text or "").strip().lower()
    try:
        if raw.startswith("0x"):
            return int(raw, 16)
        return int(raw)
    except ValueError:
        return default


def zigbee_read_attr(win):
    if not win.zigbee_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    ieee = _selected_ieee(win)
    if not ieee:
        QMessageBox.information(win, t("msg_no_point_selected"), t("msg_select_device"))
        return
    win.zigbee_worker.read_attribute(
        ieee,
        win.zigbee_ep_spin.value(),
        _parse_hex_int(win.zigbee_cluster_edit.text()),
        _parse_hex_int(win.zigbee_attr_edit.text()),
    )


def zigbee_write_attr(win):
    if not win.zigbee_connected:
        QMessageBox.information(win, t("msg_not_connected"), t("msg_connect_first"))
        return
    ieee = _selected_ieee(win)
    if not ieee:
        QMessageBox.information(win, t("msg_no_point_selected"), t("msg_select_device"))
        return
    win.zigbee_worker.write_attribute(
        ieee,
        win.zigbee_ep_spin.value(),
        _parse_hex_int(win.zigbee_cluster_edit.text()),
        _parse_hex_int(win.zigbee_attr_edit.text()),
        win.zigbee_value_edit.text(),
    )


def on_zigbee_attr(win, data):
    if data.get("op") == "read" and data.get("value") is not None:
        win.zigbee_value_edit.setText(str(data["value"]))
    zigbee_append_log(win, f"{data.get('op')} → {data.get('value')} {data.get('error', '')}".strip())


def zigbee_append_log(win, msg):
    win.zigbee_log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {msg}")


def retranslate_mqtt_zigbee(win):
    """Update MQTT/Zigbee widget texts after language change."""
    if not hasattr(win, "protocol_tabs"):
        return
    if win.protocol_tabs.count() >= 4:
        win.protocol_tabs.setTabText(2, "📨  " + t("tab_mqtt"))
        win.protocol_tabs.setTabText(3, "📡  " + t("tab_zigbee"))

    pairs = [
        ("mqtt_conn_group", "group_mqtt_conn"),
        ("mqtt_sub_group", "group_mqtt_sub"),
        ("mqtt_pub_group", "group_mqtt_pub"),
        ("mqtt_msg_group", "group_mqtt_msg"),
        ("zigbee_conn_group", "group_zigbee_conn"),
        ("zigbee_dev_group", "group_zigbee_devices"),
        ("zigbee_attr_group", "group_zigbee_attr"),
        ("zigbee_log_group", "group_zigbee_log"),
        ("lbl_mqtt_host", "lbl_ip"),
        ("lbl_mqtt_port", "lbl_port"),
        ("lbl_mqtt_client_id", "lbl_client_id"),
        ("lbl_mqtt_user", "lbl_username"),
        ("lbl_mqtt_pass", "lbl_password"),
        ("lbl_mqtt_sub_topic", "lbl_topic"),
        ("lbl_mqtt_sub_qos", "lbl_qos"),
        ("lbl_mqtt_pub_topic", "lbl_topic"),
        ("lbl_mqtt_payload", "lbl_payload"),
        ("lbl_mqtt_pub_qos", "lbl_qos"),
        ("lbl_zigbee_radio", "lbl_radio"),
        ("lbl_zigbee_com", "lbl_com"),
        ("lbl_zigbee_baud", "lbl_baud"),
        ("lbl_zigbee_permit", "lbl_permit_s"),
        ("lbl_zigbee_ep", "lbl_endpoint"),
        ("lbl_zigbee_cluster", "lbl_cluster"),
        ("lbl_zigbee_attr", "lbl_attr"),
        ("lbl_zigbee_val", "lbl_attr_value"),
        ("mqtt_sub_btn", "btn_subscribe"),
        ("mqtt_unsub_btn", "btn_unsubscribe"),
        ("mqtt_pub_btn", "btn_publish"),
        ("mqtt_tls_check", "lbl_tls"),
        ("mqtt_retain_check", "lbl_retain"),
        ("zigbee_refresh_ports_btn", "btn_refresh"),
        ("zigbee_permit_btn", "btn_permit_join"),
        ("zigbee_refresh_dev_btn", "btn_refresh_devices"),
        ("zigbee_read_btn", "btn_read_attr"),
        ("zigbee_write_btn", "btn_write_attr"),
    ]
    for attr, key in pairs:
        w = getattr(win, attr, None)
        if w is None:
            continue
        if hasattr(w, "setTitle"):
            w.setTitle(t(key))
        elif hasattr(w, "setText"):
            w.setText(t(key))

    if getattr(win, "mqtt_connected", False) or getattr(win, "_mqtt_connecting", False):
        win.mqtt_connect_btn.setText(t("btn_disconnect"))
    elif hasattr(win, "mqtt_connect_btn"):
        win.mqtt_connect_btn.setText(t("btn_connect"))

    if getattr(win, "zigbee_connected", False) or getattr(win, "_zigbee_connecting", False):
        win.zigbee_connect_btn.setText(t("btn_disconnect"))
    elif hasattr(win, "zigbee_connect_btn"):
        win.zigbee_connect_btn.setText(t("btn_connect"))

    if hasattr(win, "mqtt_msg_table"):
        win.mqtt_msg_table.setHorizontalHeaderLabels(
            [t("hdr_time"), t("hdr_topic"), t("hdr_qos"), t("hdr_retain"), t("hdr_payload")]
        )
    if hasattr(win, "zigbee_dev_table"):
        win.zigbee_dev_table.setHorizontalHeaderLabels(
            [t("hdr_ieee"), t("hdr_nwk"), t("hdr_mfr"), t("hdr_model"), t("hdr_endpoints")]
        )
    if getattr(win, "mqtt_warn_label", None) is not None:
        win.mqtt_warn_label.setText("⚠️  " + t("status_paho_missing"))
    if getattr(win, "zigbee_warn_label", None) is not None:
        win.zigbee_warn_label.setText("⚠️  " + t("status_zigpy_missing"))

    if hasattr(win, "mqtt_chip"):
        if getattr(win, "mqtt_connected", False):
            win.mqtt_chip.setText(t("chip_connected"))
        elif getattr(win, "_mqtt_connecting", False):
            win.mqtt_chip.setText(t("chip_connecting"))
        else:
            win.mqtt_chip.setText(t("chip_idle"))

    if hasattr(win, "zigbee_chip"):
        if getattr(win, "zigbee_connected", False):
            win.zigbee_chip.setText(t("chip_connected"))
        elif getattr(win, "_zigbee_connecting", False):
            win.zigbee_chip.setText(t("chip_connecting"))
        else:
            win.zigbee_chip.setText(t("chip_idle"))
