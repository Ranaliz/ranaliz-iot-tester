"""
Zigbee coordinator worker (QThread) wrapping zigpy + radio drivers.
Runs an asyncio loop off the GUI thread for ZNP / EZSP / deCONZ USB sticks.
"""
from __future__ import annotations

import asyncio
import pathlib
import queue
import traceback

from PySide6.QtCore import QThread, Signal

CACHE_DIR = pathlib.Path.home() / ".ranaliz_modbus_iec"
ZIGBEE_DB = CACHE_DIR / "zigbee.db"

RADIO_MODULES = {
    "znp": ("zigpy_znp.zigbee.application", "ControllerApplication"),
    "ezsp": ("bellows.zigbee.application", "ControllerApplication"),
    "deconz": ("zigpy_deconz.zigbee.application", "ControllerApplication"),
}

DEFAULT_BAUD = {
    "znp": 115200,
    "ezsp": 115200,
    "deconz": 38400,
}


def probe_radios():
    """Return {radio_key: True/False} for import availability."""
    import importlib

    available = {}
    for key, (mod, attr) in RADIO_MODULES.items():
        try:
            m = importlib.import_module(mod)
            getattr(m, attr)
            available[key] = True
        except Exception:
            available[key] = False
    return available


HAS_ZIGPY = any(probe_radios().values())


class _AppListener:
    """Bridge zigpy listener events into the worker."""

    def __init__(self, worker: "ZigbeeWorker"):
        self.worker = worker

    def device_joined(self, device):
        self.worker._emit_device(device, joined=True)

    def device_initialized(self, device):
        self.worker._emit_device(device, joined=False)
        self.worker._schedule_refresh()


class ZigbeeWorker(QThread):
    connected_signal = Signal(bool, str)
    disconnected_signal = Signal()
    device_list_signal = Signal(list)
    device_joined_signal = Signal(dict)
    attr_result_signal = Signal(dict)
    error_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.radio = "znp"
        self.port = ""
        self.baudrate = 115200
        self._running = False
        self._abort = False
        self._loop = None
        self._app = None
        self._cmd_queue = queue.Queue()
        self._refresh_pending = False

    def configure(self, radio, port, baudrate=None):
        self.radio = radio
        self.port = port
        if baudrate is None:
            baudrate = DEFAULT_BAUD.get(radio, 115200)
        self.baudrate = int(baudrate)

    def permit_join(self, seconds=60):
        self._cmd_queue.put(("permit", int(seconds)))

    def refresh_devices(self):
        self._cmd_queue.put(("refresh",))

    def read_attribute(self, ieee, endpoint, cluster, attr):
        self._cmd_queue.put(("read", ieee, int(endpoint), int(cluster), int(attr)))

    def write_attribute(self, ieee, endpoint, cluster, attr, value):
        self._cmd_queue.put(("write", ieee, int(endpoint), int(cluster), int(attr), value))

    def stop(self):
        self._abort = True
        self._running = False
        self._cmd_queue.put(("stop",))
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown_app(), loop)
            except Exception:
                pass

    def _schedule_refresh(self):
        self._refresh_pending = True

    def _device_info(self, device) -> dict:
        endpoints = []
        try:
            for ep_id, ep in device.endpoints.items():
                if ep_id == 0:
                    continue
                in_c = sorted(int(c) for c in getattr(ep, "in_clusters", {}).keys())
                out_c = sorted(int(c) for c in getattr(ep, "out_clusters", {}).keys())
                endpoints.append({"id": int(ep_id), "in_clusters": in_c, "out_clusters": out_c})
        except Exception:
            pass
        manufacturer = getattr(device, "manufacturer", None) or ""
        model = getattr(device, "model", None) or ""
        return {
            "ieee": str(device.ieee),
            "nwk": int(getattr(device, "nwk", 0) or 0),
            "manufacturer": str(manufacturer),
            "model": str(model),
            "endpoints": endpoints,
        }

    def _emit_device(self, device, joined=False):
        info = self._device_info(device)
        if joined:
            self.device_joined_signal.emit(info)
            self.log_signal.emit(f"Device joined: {info['ieee']}")

    def run(self):
        radios = probe_radios()
        if not radios.get(self.radio):
            self.connected_signal.emit(
                False,
                f"Radio driver '{self.radio}' not available. Install zigpy-{self.radio}/bellows.",
            )
            return
        if not self.port:
            self.connected_signal.emit(False, "No serial port selected")
            return

        self._abort = False
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            self.connected_signal.emit(False, f"{e}")
            self.error_signal.emit(traceback.format_exc())
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for t in pending:
                    t.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None
            self._app = None
            self.disconnected_signal.emit()

    async def _async_main(self):
        import importlib

        mod_name, attr = RADIO_MODULES[self.radio]
        mod = importlib.import_module(mod_name)
        ControllerApplication = getattr(mod, attr)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            "database_path": str(ZIGBEE_DB),
            "device": {
                "path": self.port,
                "baudrate": self.baudrate,
            },
        }

        self.log_signal.emit(f"Starting {self.radio} on {self.port} @ {self.baudrate}…")
        try:
            self._app = await ControllerApplication.new(config, auto_form=True, start_radio=True)
        except TypeError:
            # Older zigpy: no start_radio kw
            self._app = await ControllerApplication.new(config, auto_form=True)

        listener = _AppListener(self)
        self._app.add_listener(listener)

        pan = getattr(getattr(self._app, "state", None), "network_info", None)
        if pan is not None:
            try:
                self.log_signal.emit(
                    f"Network PAN={getattr(pan, 'pan_id', '?')} "
                    f"channel={getattr(pan, 'channel', '?')} "
                    f"ext_pan={getattr(pan, 'extended_pan_id', '?')}"
                )
            except Exception:
                pass

        self.connected_signal.emit(True, f"{self.radio} ready on {self.port}")
        self._emit_device_list()

        while self._running and not self._abort:
            if self._refresh_pending:
                self._refresh_pending = False
                self._emit_device_list()
            try:
                cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            try:
                await self._handle_cmd(cmd)
            except Exception as e:
                self.error_signal.emit(f"{e}\n{traceback.format_exc()}")

        await self._shutdown_app()

    async def _handle_cmd(self, cmd):
        kind = cmd[0]
        if kind == "stop":
            self._running = False
            return
        if self._app is None:
            return
        if kind == "permit":
            seconds = cmd[1]
            await self._app.permit(time_s=seconds)
            self.log_signal.emit(f"Permit join {seconds}s")
        elif kind == "refresh":
            self._emit_device_list()
        elif kind == "read":
            _, ieee, endpoint, cluster_id, attr_id = cmd
            device = self._find_device(ieee)
            if device is None:
                self.error_signal.emit(f"Device not found: {ieee}")
                return
            ep = device.endpoints.get(endpoint)
            if ep is None:
                self.error_signal.emit(f"Endpoint {endpoint} missing")
                return
            cluster = ep.in_clusters.get(cluster_id) or ep.out_clusters.get(cluster_id)
            if cluster is None:
                self.error_signal.emit(f"Cluster 0x{cluster_id:04X} missing")
                return
            success, failure = await cluster.read_attributes([attr_id], allow_cache=False)
            value = success.get(attr_id) if success else None
            err = failure.get(attr_id) if failure else None
            self.attr_result_signal.emit(
                {
                    "op": "read",
                    "ieee": ieee,
                    "endpoint": endpoint,
                    "cluster": cluster_id,
                    "attr": attr_id,
                    "value": value,
                    "error": str(err) if err else "",
                }
            )
            self.log_signal.emit(f"Read {ieee} ep{endpoint} 0x{cluster_id:04X}/0x{attr_id:04X} = {value}")
        elif kind == "write":
            _, ieee, endpoint, cluster_id, attr_id, value = cmd
            device = self._find_device(ieee)
            if device is None:
                self.error_signal.emit(f"Device not found: {ieee}")
                return
            ep = device.endpoints.get(endpoint)
            if ep is None:
                self.error_signal.emit(f"Endpoint {endpoint} missing")
                return
            cluster = ep.in_clusters.get(cluster_id) or ep.out_clusters.get(cluster_id)
            if cluster is None:
                self.error_signal.emit(f"Cluster 0x{cluster_id:04X} missing")
                return
            parsed = self._parse_value(value)
            await cluster.write_attributes({attr_id: parsed})
            self.attr_result_signal.emit(
                {
                    "op": "write",
                    "ieee": ieee,
                    "endpoint": endpoint,
                    "cluster": cluster_id,
                    "attr": attr_id,
                    "value": parsed,
                    "error": "",
                }
            )
            self.log_signal.emit(f"Write {ieee} ep{endpoint} 0x{cluster_id:04X}/0x{attr_id:04X} = {parsed}")

    def _find_device(self, ieee_str):
        if self._app is None:
            return None
        for ieee, dev in self._app.devices.items():
            if str(ieee) == ieee_str:
                return dev
        return None

    def _emit_device_list(self):
        if self._app is None:
            self.device_list_signal.emit([])
            return
        devices = [self._device_info(d) for d in self._app.devices.values()]
        devices.sort(key=lambda d: d["ieee"])
        self.device_list_signal.emit(devices)

    @staticmethod
    def _parse_value(raw):
        text = str(raw).strip()
        low = text.lower()
        if low in ("true", "on", "yes"):
            return True
        if low in ("false", "off", "no"):
            return False
        try:
            if text.startswith("0x") or text.startswith("0X"):
                return int(text, 16)
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    async def _shutdown_app(self):
        app = self._app
        self._app = None
        if app is None:
            return
        try:
            await app.shutdown()
        except Exception as e:
            self.error_signal.emit(f"Shutdown: {e}")
