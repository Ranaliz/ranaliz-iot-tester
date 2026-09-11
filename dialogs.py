"""Small reusable dialogs used by the main window."""
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QComboBox,
)

from i18n import t


class ModbusWriteDialog(QDialog):
    """Dialog to compose a Modbus write request (single or multiple)."""
    def __init__(self, parent, function, slave_id, address):
        super().__init__(parent)
        self.setWindowTitle(t("dlg_modbus_write"))
        self.setMinimumWidth(360)
        self.function = function
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(0, 247)
        self.slave_spin.setValue(slave_id)
        layout.addRow(t("dlg_slave"), self.slave_spin)

        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(0, 65535)
        self.addr_spin.setValue(address)
        layout.addRow(t("dlg_address"), self.addr_spin)

        self.value_edit = QLineEdit()
        if function == "write_coil":
            self.value_edit.setPlaceholderText(t("dlg_ph_coil"))
        elif function == "write_register":
            self.value_edit.setPlaceholderText(t("dlg_ph_reg"))
        elif function == "write_coils":
            self.value_edit.setPlaceholderText(t("dlg_ph_coils"))
        elif function == "write_registers":
            self.value_edit.setPlaceholderText(t("dlg_ph_regs"))
        layout.addRow(t("dlg_values"), self.value_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("dlg_send"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("dlg_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        slave = self.slave_spin.value()
        addr = self.addr_spin.value()
        text = self.value_edit.text().strip()
        if self.function in ("write_coil", "write_register"):
            val = int(text)
        else:
            val = [int(v.strip()) for v in text.split(",") if v.strip() != ""]
        return slave, addr, val


class Iec104CommandDialog(QDialog):
    """Dialog to compose an IEC 104 command to send from the client."""
    def __init__(self, parent, command_types):
        super().__init__(parent)
        self.setWindowTitle(t("dlg_iec_cmd"))
        self.setMinimumWidth(380)
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(command_types.keys()))
        layout.addRow(t("dlg_cmd_type"), self.type_combo)

        self.io_spin = QSpinBox()
        self.io_spin.setRange(0, 16777215)
        layout.addRow(t("dlg_io"), self.io_spin)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText(t("dlg_ph_iec_val"))
        layout.addRow(t("dlg_value"), self.value_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("dlg_send"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("dlg_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        type_label = self.type_combo.currentText()
        io_addr = self.io_spin.value()
        text = self.value_edit.text().strip().lower()
        if text in ("true", "1", "on", "yes"):
            value = True
        elif text in ("false", "0", "off", "no"):
            value = False
        else:
            try:
                value = float(text) if "." in text else int(text)
            except ValueError:
                value = text
        return type_label, io_addr, value


class Iec104AddPointDialog(QDialog):
    """Dialog to add a monitoring/command point to an IEC 104 station (client or server)."""
    def __init__(self, parent, type_options, is_server=False):
        super().__init__(parent)
        self.setWindowTitle(t("dlg_add_point"))
        self.setMinimumWidth(380)
        self.is_server = is_server
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(type_options.keys()))
        layout.addRow(t("dlg_type"), self.type_combo)

        self.io_spin = QSpinBox()
        self.io_spin.setRange(0, 16777215)
        layout.addRow(t("dlg_io"), self.io_spin)

        if is_server:
            self.initial_value_edit = QLineEdit()
            self.initial_value_edit.setPlaceholderText(t("dlg_ph_initial"))
            layout.addRow(t("dlg_initial"), self.initial_value_edit)

            self.report_spin = QSpinBox()
            self.report_spin.setRange(0, 3600000)
            self.report_spin.setSingleStep(500)
            self.report_spin.setValue(0)
            self.report_spin.setSuffix(t("dlg_report_suffix"))
            layout.addRow(t("dlg_report"), self.report_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("dlg_add"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("dlg_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        type_label = self.type_combo.currentText()
        io_addr = self.io_spin.value()
        if self.is_server:
            text = self.initial_value_edit.text().strip().lower()
            if text in ("true", "1", "on", "yes"):
                initial_value = True
            elif text in ("false", "0", "off", "no"):
                initial_value = False
            elif text == "":
                initial_value = None
            else:
                try:
                    initial_value = float(text) if "." in text else int(text)
                except ValueError:
                    initial_value = None
            return type_label, io_addr, initial_value, self.report_spin.value()
        return type_label, io_addr
