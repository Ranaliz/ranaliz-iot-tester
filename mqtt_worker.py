"""
MQTT client worker (QThread) using paho-mqtt Callback API v2.
Connect / subscribe / publish without blocking the GUI thread.
"""
import queue
import ssl
import traceback

from PySide6.QtCore import QThread, Signal

try:
    from paho.mqtt.client import Client as MqttClient, CallbackAPIVersion, MQTT_ERR_SUCCESS
    HAS_PAHO = True
except Exception:
    HAS_PAHO = False
    MqttClient = None
    CallbackAPIVersion = None
    MQTT_ERR_SUCCESS = 0


class MqttWorker(QThread):
    connected_signal = Signal(bool, str)
    disconnected_signal = Signal()
    message_signal = Signal(str, str, int, bool)  # topic, payload, qos, retain
    error_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.host = "127.0.0.1"
        self.port = 1883
        self.client_id = "ranaliz-mqtt"
        self.username = ""
        self.password = ""
        self.use_tls = False
        self._client = None
        self._running = False
        self._abort = False
        self._cmd_queue = queue.Queue()
        self._subscriptions = set()

    def configure(self, host, port, client_id, username="", password="", use_tls=False):
        self.host = host
        self.port = int(port)
        self.client_id = client_id or "ranaliz-mqtt"
        self.username = username or ""
        self.password = password or ""
        self.use_tls = bool(use_tls)

    def subscribe(self, topic, qos=0):
        self._cmd_queue.put(("subscribe", topic, int(qos)))

    def unsubscribe(self, topic):
        self._cmd_queue.put(("unsubscribe", topic))

    def publish(self, topic, payload, qos=0, retain=False):
        self._cmd_queue.put(("publish", topic, payload, int(qos), bool(retain)))

    def stop(self):
        self._abort = True
        self._running = False
        self._cmd_queue.put(("stop",))
        client = self._client
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass

    def run(self):
        if not HAS_PAHO:
            self.connected_signal.emit(False, "paho-mqtt not installed (pip install paho-mqtt)")
            return

        self._abort = False
        self._running = True
        self._subscriptions.clear()
        try:
            client = MqttClient(CallbackAPIVersion.VERSION2, client_id=self.client_id)
        except Exception as e:
            self.connected_signal.emit(False, f"MQTT client create failed: {e}")
            return

        self._client = client

        def on_connect(client, userdata, flags, reason_code, properties=None):
            ok = False
            try:
                if hasattr(reason_code, "is_failure"):
                    ok = not reason_code.is_failure
                elif hasattr(reason_code, "value"):
                    ok = int(reason_code.value) == 0
                else:
                    ok = int(reason_code) == 0
            except Exception:
                ok = str(reason_code) in ("Success", "0")
            if ok:
                self.connected_signal.emit(True, f"Connected to {self.host}:{self.port}")
                for topic, qos in list(self._subscriptions):
                    try:
                        client.subscribe(topic, qos)
                    except Exception as exc:
                        self.error_signal.emit(f"Resubscribe {topic}: {exc}")
            else:
                self.connected_signal.emit(False, f"MQTT connect failed: {reason_code}")

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
            self.disconnected_signal.emit()

        def on_message(client, userdata, msg):
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                payload = repr(msg.payload)
            self.message_signal.emit(msg.topic, payload, int(msg.qos), bool(msg.retain))

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        if self.username:
            client.username_pw_set(self.username, self.password or None)
        if self.use_tls:
            try:
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            except Exception as e:
                self.error_signal.emit(f"TLS setup: {e}")

        try:
            self.log_signal.emit(f"Connecting to {self.host}:{self.port}…")
            client.connect_async(self.host, self.port, keepalive=30)
            client.loop_start()
        except Exception as e:
            self.connected_signal.emit(False, str(e))
            self._cleanup_client(client)
            self._client = None
            return

        while self._running and not self._abort:
            try:
                cmd = self._cmd_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._handle_cmd(client, cmd)
            except Exception as e:
                self.error_signal.emit(f"{e}\n{traceback.format_exc()}")

        self._cleanup_client(client)
        self._client = None
    def _handle_cmd(self, client, cmd):
        kind = cmd[0]
        if kind == "stop":
            self._running = False
            return
        if kind == "subscribe":
            _, topic, qos = cmd
            if not topic:
                return
            rc = client.subscribe(topic, qos)
            code = rc[0] if isinstance(rc, tuple) else rc
            if code == MQTT_ERR_SUCCESS:
                self._subscriptions.add((topic, qos))
                self.log_signal.emit(f"Subscribed: {topic} (QoS {qos})")
            else:
                self.error_signal.emit(f"Subscribe failed ({code}): {topic}")
        elif kind == "unsubscribe":
            _, topic = cmd
            client.unsubscribe(topic)
            self._subscriptions = {(t, q) for t, q in self._subscriptions if t != topic}
            self.log_signal.emit(f"Unsubscribed: {topic}")
        elif kind == "publish":
            _, topic, payload, qos, retain = cmd
            info = client.publish(topic, payload, qos=qos, retain=retain)
            if getattr(info, "rc", MQTT_ERR_SUCCESS) != MQTT_ERR_SUCCESS:
                self.error_signal.emit(f"Publish failed: {topic}")
            else:
                self.log_signal.emit(f"Published → {topic}")

    def _cleanup_client(self, client):
        if client is None:
            return
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass
