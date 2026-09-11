"""
IEC 60870-5-104 worker: wraps the `c104` library (lib60870-C based) to provide
both a Client (SCADA/master - reads monitoring points, sends commands) and a
Server (RTU/simulator - hosts points that a real SCADA master can poll/command)
inside a background QThread, with Qt signals back to the GUI thread.
"""
import time
import traceback
import queue

from PySide6.QtCore import QThread, Signal, QTimer

try:
    import c104
    HAS_C104 = True
except Exception:
    HAS_C104 = False
    c104 = None


# Human-readable labels for the most commonly used monitoring & command types.
MONITORING_TYPES = {
    "M_SP_NA_1 - Single Point": "M_SP_NA_1",
    "M_DP_NA_1 - Double Point": "M_DP_NA_1",
    "M_ST_NA_1 - Step Position": "M_ST_NA_1",
    "M_BO_NA_1 - Bitstring 32": "M_BO_NA_1",
    "M_ME_NA_1 - Measured Normalized": "M_ME_NA_1",
    "M_ME_NB_1 - Measured Scaled": "M_ME_NB_1",
    "M_ME_NC_1 - Measured Float": "M_ME_NC_1",
    "M_IT_NA_1 - Integrated Totals": "M_IT_NA_1",
}

COMMAND_TYPES = {
    "C_SC_NA_1 - Single Command": "C_SC_NA_1",
    "C_DC_NA_1 - Double Command": "C_DC_NA_1",
    "C_RC_NA_1 - Regulating Step": "C_RC_NA_1",
    "C_SE_NA_1 - Setpoint Normalized": "C_SE_NA_1",
    "C_SE_NB_1 - Setpoint Scaled": "C_SE_NB_1",
    "C_SE_NC_1 - Setpoint Float": "C_SE_NC_1",
    "C_BO_NA_1 - Bitstring 32 Command": "C_BO_NA_1",
}


def _type_from_name(name):
    return getattr(c104.Type, name)


class Iec104ClientWorker(QThread):
    """SCADA/master role: connects to a remote RTU, polls/monitors points, sends commands."""

    connected_signal = Signal(bool, str)
    disconnected_signal = Signal()
    point_update_signal = Signal(dict)   # {common_address, io_address, type, value, quality, cot, timestamp}
    error_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.ip = "127.0.0.1"
        self.port = 2404
        self.common_address = 1
        self.points = []  # list of dicts: {io_address, type_name}
        self._client = None
        self._connection = None
        self._station = None
        self._running = False
        self._abort = False
        self._pending_command = None  # (io_address, type_name, value)
        self._point_objs = {}  # io_address -> c104.Point
        self._update_queue = queue.Queue()  # Thread-safe deferred updates from c104 callback

    def configure(self, ip, port, common_address, points):
        self.ip = ip
        self.port = int(port)
        self.common_address = int(common_address)
        self.points = points  # [{"io_address": int, "type_name": str}]

    def queue_command(self, io_address, type_name, value):
        self._pending_command = (io_address, type_name, value)

    def queue_interrogation(self):
        self._pending_command = ("__INTERROGATE__", None, None)

    def run(self):
        if not HAS_C104:
            self.connected_signal.emit(False, "c104 library not installed")
            return
        self._abort = False
        try:
            self._client = c104.Client(tick_rate_ms=100, command_timeout_ms=5000)
            self._connection = self._client.add_connection(
                ip=self.ip, port=self.port, init=c104.Init.ALL
            )
            if self._connection is None:
                self.connected_signal.emit(False, "Failed to create connection object")
                return

            self._station = self._connection.add_station(common_address=self.common_address)
            if self._station is None:
                self.connected_signal.emit(False, "Failed to add station")
                return

            for p in self.points:
                try:
                    type_obj = _type_from_name(p["type_name"])
                    point = self._station.add_point(io_address=int(p["io_address"]), type=type_obj)
                    if point is not None:
                        point.on_receive(self._make_receive_handler())
                        self._point_objs[int(p["io_address"])] = point
                except Exception as e:
                    self.error_signal.emit(f"Point add error ({p}): {e}")

            self._client.start()
            self._connection.connect()

            # wait (bounded) for the connection to actually come up. Both OPEN and
            # OPEN_MUTED are usable states for data exchange in lib60870-C/c104 --
            # "muted" just means the link layer hasn't confirmed activation yet,
            # ASDUs still flow. Only CLOSED* states mean it truly failed.
            waited = 0
            usable_states = (c104.ConnectionState.OPEN, c104.ConnectionState.OPEN_MUTED)
            while waited < 5000 and not self._abort and self._connection.state not in usable_states:
                time.sleep(0.05)
                waited += 50

            if self._abort:
                return

            if self._connection.state in usable_states:
                self.connected_signal.emit(True, "Connected")
            else:
                self.connected_signal.emit(False, f"Connection state: {self._connection.state}")
                return

            # Poll for queued commands and deferred point updates in a loop.
            self._running = True
            while self._running and not self._abort:
                # Process queued point updates (from c104's background thread callback)
                while True:
                    try:
                        update = self._update_queue.get_nowait()
                        self.point_update_signal.emit(update)
                    except queue.Empty:
                        break
                
                # Process pending commands
                if self._pending_command is not None:
                    cmd = self._pending_command
                    self._pending_command = None
                    self._execute_command(cmd)
                time.sleep(0.05)

        except Exception as e:
            self.error_signal.emit(f"IEC104 client exception: {e}\n{traceback.format_exc()}")
            self.connected_signal.emit(False, str(e))
        finally:
            try:
                if self._client:
                    self._client.stop()
            except Exception:
                pass
            self._client = None
            self._connection = None
            self._station = None
            self.disconnected_signal.emit()

    def _make_receive_handler(self):
        worker = self

        def handler(point: c104.Point, previous_info: c104.Information, message: c104.IncomingMessage) -> c104.ResponseState:
            try:
                # Queue the update instead of directly emitting signal from c104's background thread
                # This ensures the signal is delivered safely via the worker's polling loop
                worker._update_queue.put({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "common_address": worker.common_address,
                    "io_address": point.io_address,
                    "type": str(point.type).split(".")[-1],
                    "value": point.value,
                    "quality": str(point.quality) if point.quality is not None else "",
                    "cot": str(message.cot) if hasattr(message, "cot") else "",
                })
            except Exception as e:
                worker.error_signal.emit(f"Receive handler error: {e}")
            return c104.ResponseState.SUCCESS

        return handler

    def _execute_command(self, cmd):
        io_address, type_name, value = cmd
        try:
            if io_address == "__INTERROGATE__":
                ok = self._station.interrogation(cause=c104.Cot.ACTIVATION) if hasattr(self._station, "interrogation") else False
                self.log_signal.emit(f"General interrogation sent: {ok}")
                return

            point = self._point_objs.get(int(io_address))
            if point is None:
                self.error_signal.emit(f"No point configured at IO address {io_address}")
                return
            point.value = value
            ok = point.transmit(cause=c104.Cot.ACTIVATION)
            self.log_signal.emit(f"Command to IO {io_address} ({type_name}) = {value}: {'OK' if ok else 'FAILED'}")
        except Exception as e:
            self.error_signal.emit(f"Command execution error: {e}")

    def stop(self):
        """Abort ASAP: stop the c104 client from any thread so connect waits unblock."""
        self._abort = True
        self._running = False
        client = self._client
        connection = self._connection
        try:
            if connection is not None and hasattr(connection, "disconnect"):
                connection.disconnect()
        except Exception:
            pass
        try:
            if client is not None:
                client.stop()
        except Exception:
            pass


class Iec104ServerWorker(QThread):
    """RTU/simulator role: hosts a station with configurable points that report
    periodic measurements and accept incoming commands from a real SCADA master."""

    started_signal = Signal(bool, str)
    stopped_signal = Signal()
    activity_signal = Signal(dict)  # generic log entry for the UI
    error_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.port = 2404
        self.common_address = 1
        self.points = []  # [{"io_address", "type_name", "initial_value"}]
        self._server = None
        self._station = None
        self._running = False
        self._abort = False
        self._point_objs = {}
        self._activity_queue = queue.Queue()  # Thread-safe deferred updates from c104 callback

    def configure(self, port, common_address, points):
        self.port = int(port)
        self.common_address = int(common_address)
        self.points = points

    def run(self):
        if not HAS_C104:
            self.started_signal.emit(False, "c104 library not installed")
            return
        self._abort = False
        try:
            self._server = c104.Server(ip="0.0.0.0", port=self.port)
            self._station = self._server.add_station(common_address=self.common_address)

            for p in self.points:
                try:
                    type_obj = _type_from_name(p["type_name"])
                    point = self._station.add_point(
                        io_address=int(p["io_address"]),
                        type=type_obj,
                        report_ms=int(p.get("report_ms", 0)) or 0,
                    )
                    if point is not None:
                        if p.get("initial_value") is not None:
                            try:
                                point.value = p["initial_value"]
                            except Exception:
                                pass
                        point.on_receive(self._make_command_handler())
                        self._point_objs[int(p["io_address"])] = point
                except Exception as e:
                    self.error_signal.emit(f"Point add error ({p}): {e}")

            self._server.start()
            self._running = True
            self.started_signal.emit(True, f"Listening on 0.0.0.0:{self.port}")

            while self._running and not self._abort:
                # Process queued activity from c104 callback
                while True:
                    try:
                        activity = self._activity_queue.get_nowait()
                        self.activity_signal.emit(activity)
                    except queue.Empty:
                        break
                time.sleep(0.1)

        except Exception as e:
            self.error_signal.emit(f"IEC104 server exception: {e}\n{traceback.format_exc()}")
            self.started_signal.emit(False, str(e))
        finally:
            try:
                if self._server:
                    self._server.stop()
            except Exception:
                pass
            self._server = None
            self._station = None
            self.stopped_signal.emit()

    def _make_command_handler(self):
        worker = self

        def handler(point: c104.Point, previous_info: c104.Information, message: c104.IncomingMessage) -> c104.ResponseState:
            try:
                # Queue the activity instead of directly emitting from c104's background thread
                worker._activity_queue.put({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "common_address": worker.common_address,
                    "io_address": point.io_address,
                    "type": str(point.type).split(".")[-1],
                    "value": point.value,
                    "quality": str(point.quality) if point.quality is not None else "",
                    "cot": "COMMAND_RECEIVED",
                })
            except Exception as e:
                worker.error_signal.emit(f"Command handler error: {e}")
            return c104.ResponseState.SUCCESS

        return handler

    def set_point_value(self, io_address, value):
        """Manually push a new value for a simulated point and transmit it (spontaneous update)."""
        point = self._point_objs.get(int(io_address))
        if point is None:
            self.error_signal.emit(f"No point configured at IO address {io_address}")
            return False
        try:
            point.value = value
            return point.transmit(cause=c104.Cot.SPONTANEOUS)
        except Exception as e:
            self.error_signal.emit(f"set_point_value error: {e}")
            return False

    def stop(self):
        self._abort = True
        self._running = False
        server = self._server
        try:
            if server is not None:
                server.stop()
        except Exception:
            pass
