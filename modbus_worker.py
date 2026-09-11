"""
Background worker (QThread) that owns the actual Modbus client connection
and performs polling on a timer, emitting results back to the GUI thread.
"""
import time
import traceback

from PySide6.QtCore import QThread, Signal, QMutex

import inspect

from pymodbus.client import ModbusTcpClient, ModbusUdpClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException

# pymodbus renamed the unit-id keyword across versions:
#   <= 3.5   : slave=
#   >= 3.7ish: slave= (kept as alias for a while)
#   3.9+/3.15: device_id= (slave= removed in newer releases)
# Detect which kwarg this installed version actually accepts so calls don't
# blow up with TypeError (which was crashing the worker thread / aborting Qt).
def _detect_unit_kwarg():
    try:
        params = inspect.signature(ModbusTcpClient.read_holding_registers).parameters
        if "device_id" in params:
            return "device_id"
        if "slave" in params:
            return "slave"
    except (ValueError, TypeError):
        pass
    return "slave"


UNIT_KWARG = _detect_unit_kwarg()


def unit_kwargs(unit_id):
    """Build the {slave: id} or {device_id: id} kwarg dict for the installed pymodbus."""
    return {UNIT_KWARG: unit_id}


FUNCTION_MAP = {
    "01-Read Coils": "coils",
    "02-Read Discrete Inputs": "discrete",
    "03-Read Holding Registers": "holding",
    "04-Read Input Registers": "input",
    "05-Write Single Coil": "write_coil",
    "06-Write Single Register": "write_register",
    "15-Write Multiple Coils": "write_coils",
    "16-Write Multiple Registers": "write_registers",
}


class ModbusWorker(QThread):
    connected_signal = Signal(bool, str)          # success, message
    data_signal = Signal(list, int)                # values, start_address
    error_signal = Signal(str)
    tx_count_signal = Signal(int)
    disconnected_signal = Signal()

    def __init__(self):
        super().__init__()
        self.client = None
        self._mutex = QMutex()
        self._running = False
        self._connected = False
        self._abort = False

        # connection params
        self.conn_type = "tcp"  # tcp / udp / rtu
        self.tcp_params = {}
        self.serial_params = {}

        # modbus polling params
        self.function = "03-Read Holding Registers"
        self.slave_id = 1
        self.start_address = 0
        self.count = 1
        self.poll_rate_ms = 1000
        self.delay_between_polls_ms = 25
        self.timeout_ms = 3000

        self.tx_count = 0
        self.error_count = 0

        # for one-shot writes queued from UI
        self._pending_write = None

    def _force_close_client(self):
        """Close the underlying transport immediately (safe to call from any thread)."""
        client = self.client
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass
        # Best-effort: poke the raw socket so a blocking connect()/recv() unblocks
        try:
            sock = getattr(client, "socket", None) or getattr(client, "transport", None)
            if sock is not None and hasattr(sock, "close"):
                sock.close()
        except Exception:
            pass

    # ---------------- connection management ----------------

    def configure_tcp(self, ip, port, timeout_ms, delay_ms, protocol="TCP"):
        self.conn_type = "udp" if protocol.upper() == "UDP" else "tcp"
        self.tcp_params = {"host": ip, "port": int(port)}
        self.timeout_ms = timeout_ms
        self.delay_between_polls_ms = delay_ms

    def configure_serial(self, port, baudrate, bytesize, parity, stopbits, timeout_ms, delay_ms):
        self.conn_type = "rtu"
        self.serial_params = {
            "port": port,
            "baudrate": int(baudrate),
            "bytesize": int(bytesize),
            "parity": parity,
            "stopbits": stopbits,
        }
        self.timeout_ms = timeout_ms
        self.delay_between_polls_ms = delay_ms

    def configure_poll(self, function, slave_id, start_address, count, poll_rate_ms):
        self.function = function
        self.slave_id = int(slave_id)
        self.start_address = int(start_address)
        self.count = int(count)
        self.poll_rate_ms = int(poll_rate_ms)

    def queue_write(self, function, address, value):
        """Queue a single write operation to be executed on next loop iteration."""
        self._pending_write = (function, address, value)

    def connect_client(self):
        try:
            timeout_s = max(self.timeout_ms, 1) / 1000.0
            if self.conn_type == "tcp":
                self.client = ModbusTcpClient(
                    self.tcp_params["host"],
                    port=self.tcp_params["port"],
                    timeout=timeout_s,
                )
            elif self.conn_type == "udp":
                self.client = ModbusUdpClient(
                    self.tcp_params["host"],
                    port=self.tcp_params["port"],
                    timeout=timeout_s,
                )
            else:  # rtu
                sp = self.serial_params
                self.client = ModbusSerialClient(
                    port=sp["port"],
                    baudrate=sp["baudrate"],
                    bytesize=sp["bytesize"],
                    parity=sp["parity"],
                    stopbits=sp["stopbits"],
                    timeout=timeout_s,
                )

            if self._abort:
                self._force_close_client()
                self._connected = False
                return False

            ok = self.client.connect()
            if self._abort:
                self._force_close_client()
                self._connected = False
                return False

            self._connected = ok
            if ok:
                self.connected_signal.emit(True, "Connected")
            else:
                self.connected_signal.emit(False, "Failed to open connection")
            return ok
        except Exception as e:
            self._connected = False
            if not self._abort:
                self.connected_signal.emit(False, f"Connection error: {e}")
            return False

    def disconnect_client(self):
        """Abort polling and force-close the socket immediately."""
        self._abort = True
        self._running = False
        self._force_close_client()
        self._connected = False

    # ---------------- main loop ----------------

    def run(self):
        self._abort = False
        if not self.connect_client():
            return
        self._running = True

        while self._running and not self._abort:
            loop_start = time.time()

            # handle any queued write first
            if self._pending_write is not None:
                func, addr, val = self._pending_write
                self._pending_write = None
                self._do_write(func, addr, val)

            self._do_poll()

            elapsed_ms = (time.time() - loop_start) * 1000.0
            sleep_ms = max(self.poll_rate_ms - elapsed_ms, 0)
            # sleep in small increments so we can react to stop requests quickly
            slept = 0.0
            while slept < sleep_ms and self._running and not self._abort:
                step = min(50, sleep_ms - slept)
                time.sleep(step / 1000.0)
                slept += step

            if self._running and not self._abort and self.delay_between_polls_ms > 0:
                time.sleep(self.delay_between_polls_ms / 1000.0)

        self._force_close_client()
        self._connected = False

    def _do_write(self, func, addr, val):
        try:
            uk = unit_kwargs(self.slave_id)
            if func == "write_coil":
                rr = self.client.write_coil(addr, bool(val), **uk)
            elif func == "write_register":
                rr = self.client.write_register(addr, int(val), **uk)
            elif func == "write_coils":
                rr = self.client.write_coils(addr, val, **uk)
            elif func == "write_registers":
                rr = self.client.write_registers(addr, val, **uk)
            else:
                return
            self.tx_count += 1
            self.tx_count_signal.emit(self.tx_count)
            if rr.isError():
                self.error_count += 1
                self.error_signal.emit(f"Write error: {rr}")
        except Exception as e:
            self.error_count += 1
            self.error_signal.emit(f"Write exception: {e}")

    def _do_poll(self):
        kind = FUNCTION_MAP.get(self.function)
        if kind not in ("coils", "discrete", "holding", "input"):
            return  # write-only function selected, nothing to poll continuously

        try:
            uk = unit_kwargs(self.slave_id)
            if kind == "coils":
                rr = self.client.read_coils(self.start_address, count=self.count, **uk)
                values = [int(b) for b in rr.bits[: self.count]] if not rr.isError() else None
            elif kind == "discrete":
                rr = self.client.read_discrete_inputs(self.start_address, count=self.count, **uk)
                values = [int(b) for b in rr.bits[: self.count]] if not rr.isError() else None
            elif kind == "holding":
                rr = self.client.read_holding_registers(self.start_address, count=self.count, **uk)
                values = rr.registers if not rr.isError() else None
            elif kind == "input":
                rr = self.client.read_input_registers(self.start_address, count=self.count, **uk)
                values = rr.registers if not rr.isError() else None
            else:
                values = None

            self.tx_count += 1
            self.tx_count_signal.emit(self.tx_count)

            if values is None:
                self.error_count += 1
                self.error_signal.emit(f"Read error: {rr}")
            else:
                self.data_signal.emit(values, self.start_address)

        except ModbusException as e:
            self.error_count += 1
            self.error_signal.emit(f"Modbus exception: {e}")
        except Exception as e:
            self.error_count += 1
            self.error_signal.emit(f"Exception: {e}\n{traceback.format_exc()}")

    def stop(self):
        """Signal the loop to exit and force-close I/O so waiters unblock ASAP."""
        self._abort = True
        self._running = False
        self._force_close_client()
