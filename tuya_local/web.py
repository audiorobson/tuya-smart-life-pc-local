"""Painel loopback com controles LAN e operações opcionais de nuvem."""
import copy
import json
import queue
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import pending
from .service import LocalHub
from .features import Features
from .presentation import API_VERSION, readings as present_readings, integration

ASSETS = Path(__file__).parent / "static"
SENSOR_CODES = {"temp_current": "Temperatura", "humidity_value": "Umidade", "va_temperature": "Temperatura", "va_humidity": "Umidade",
                "battery_percentage": "Bateria", "va_battery": "Bateria"}


def prepare(config, source, capabilities=None):
    """Perfis limitados a interruptores identificados no mapeamento importado."""
    config = copy.deepcopy(config)
    mappings = {d["id"]: d.get("mapping", {}) for d in source}
    for d in config["devices"]:
        mapping = mappings.get(d["id"]) or {}
        d["web_mapping"] = mapping
        # A versão web não expõe controles manuais de alarmes, portas ou cenas.
        d["controls"] = []
        if d.get("category") not in ("kg", "tdq", "tgq", "dgnzk"):
            continue
        for dp, spec in mapping.items():
            code = spec.get("code", "")
            if d.get('category') == 'dgnzk' and code not in {f['code'] for f in (capabilities or {}).get('functions', {}).get(d['id'], [])}:
                continue
            if spec.get("type") == "Boolean" and re.fullmatch(r"switch_(?:led_)?[1-9][0-9]*", code) and str(dp).isdigit():
                channel = code.rsplit("_", 1)[-1]
                d["controls"].append({"name": f"Canal {channel}", "dp": str(dp),
                                      "values": {"Ligar": True, "Desligar": False}})
    return config


class Dashboard(Features):
    def __init__(self, config, source, factory=None, capabilities=None, storage=None, cloud=None, config_path=None):
        self.source = source
        self.config_path = Path(config_path) if config_path else None
        self.hub = LocalHub(prepare(config, source, capabilities), factory=factory)
        self.states = {}
        self.lock = threading.Lock()
        self.tasks = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.busy = False
        self.operation = ""
        self.last_command = None
        self.activity = []
        self.thread = None
        self.token = secrets.token_urlsafe(32)
        self.init_features(capabilities, storage, cloud)

    def start(self):
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.submit("refresh")

    def submit(self, operation, device_id=None, control=None, action=None):
        if operation in self.OPERATIONS:
            action = self.validate_feature(operation, action)
        elif operation not in ("refresh", "status", "command"):
            raise ValueError("Operação desconhecida.")
        if operation in ('status', 'command') and device_id not in self.hub.devices:
            raise ValueError("Dispositivo não cadastrado.")
        if operation == "command":
            controls = self.hub.devices[device_id]["controls"]
            if type(control) is not int or control < 0 or control >= len(controls):
                raise ValueError("Canal não permitido.")
            if not isinstance(action, str) or action not in controls[control]["values"]:
                raise ValueError("Ação não permitida.")
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            if operation in ('command', 'setting'):
                self.last_command = {'id': device_id if operation == 'command' else action['id'],
                                     'control': control if operation == 'command' else None,
                                     'dp': action.get('dp') if operation == 'setting' else None,
                                     'target': action if operation == 'command' else action['value'],
                                     'status': 'pending'}
            self.operation = "Consultando equipamentos…" if operation == "refresh" else "Aguardando resposta do equipamento…"
            self.tasks.put_nowait((operation, device_id, control, action))
        return True

    def _store(self, state):
        with self.lock:
            self.states[state["id"]] = state

    def _log(self, text, level="info"):
        with self.lock:
            self.activity.insert(0, {"time": datetime.now(timezone.utc).isoformat(), "text": text, "level": level})
            del self.activity[20:]

    def _execute(self, task):
        operation, device_id, control, action = task
        try:
            if operation in self.OPERATIONS:
                self.execute_feature(operation, action)
                if operation == 'setting':
                    with self.lock:
                        self.last_command['status'] = 'confirmed'
            elif operation == "refresh":
                for entry in self.hub.devices.values():
                    if self.stop.is_set():
                        break
                    self._store(self.hub.status(entry["id"]))
                self._log("Consulta de estado concluída.")
            elif operation == "status":
                self._store(self.hub.status(device_id))
                self._log(f"Estado consultado: {self.hub.devices[device_id].get('name', device_id)}.")
            else:
                result = self.hub.command(device_id, control, action)
                self._store(result)
                with self.lock:
                    self.last_command['status'] = 'confirmed' if result.get('command_confirmed') else 'unconfirmed'
                name = self.hub.devices[device_id].get("name", device_id)
                if result.get("command_confirmed"):
                    self._log(f"{name} · {action}: estado confirmado.", "success")
                else:
                    self._log(f"{name} · resultado não confirmado. Confira o equipamento antes de repetir.", "error")
        except Exception as exc:
            # Apenas mensagens controladas do serviço; nunca payload/traceback/chaves.
            message = str(exc) if type(exc) is ValueError else "Falha na operação. Consulte o estado antes de repetir."
            self._log(message, "error")
        finally:
            with self.lock:
                if operation in ('command', 'setting') and self.last_command and self.last_command['status'] == 'pending':
                    self.last_command['status'] = 'unconfirmed'
                self.busy = False
                self.operation = ""

    def _worker(self):
        next_refresh = time.monotonic() + 60
        next_events = time.monotonic() + 3
        try:
            while not self.stop.is_set():
                try:
                    task = self.tasks.get(timeout=0.4)
                except queue.Empty:
                    now = time.monotonic()
                    if now >= next_events:
                        for state in self.hub.events():
                            self._store(state)
                        next_events = time.monotonic() + 3
                    if now >= next_refresh:
                        self.submit("refresh")
                        next_refresh = time.monotonic() + 60
                else:
                    self._execute(task)
        finally:
            self.hub.close()

    def snapshot(self):
        with self.lock:
            states = copy.deepcopy(self.states)
            result = {"busy": self.busy, "operation": self.operation,
                      "last_command": copy.deepcopy(self.last_command),
                      "activity": copy.deepcopy(self.activity), "devices": []}
            result.update(self.feature_snapshot())
            hub, settings, pairing = self.hub, self.settings, dict(self.pairing)
            cloud_states = copy.deepcopy(self.cloud_states)
        for d in hub.devices.values():
            state = states.get(d["id"], {})
            issue = pending(d, hub.devices)
            controls = []
            for index, control in enumerate(d["controls"]):
                value = state.get("current_dps", {}).get(control["dp"])
                enabled = state.get("state") == "online" and type(value) is bool and not issue
                controls.append({"index": index, "name": control["name"], "value": value if type(value) is bool else None,
                                 "enabled": bool(enabled), "actions": list(control["values"])})
            readings = present_readings(d, state)
            parent = hub.devices.get(d.get("parent"), {})
            device_settings = []
            for spec in settings[d['id']]:
                item = copy.deepcopy(spec)
                item['value'] = state.get('current_dps', {}).get(spec['dp'])
                item['enabled'] = state.get('state') == 'online' and item['value'] is not None and not issue
                device_settings.append(item)
            result["devices"].append({
                "id": d["id"], "name": d.get("name", d["id"]), "kind": d.get("kind", "unknown"),
                "category": d.get("category", ""), "ip": d.get("ip", ""), "room": d.get("room", ""),
                "parent": d.get("parent", ""), "parent_name": parent.get("name", ""),
                "children": sum(x.get("parent") == d["id"] for x in hub.devices.values()),
                "state": state.get("state", "configuracao_pendente" if issue else "nao_consultado"),
                "detail": issue or state.get("detail", ""), "last_seen": state.get("last_seen"),
                "controls": controls, "readings": readings,
                "settings": device_settings, "pairing_until": pairing.get(d['id'], 0),
                "favorite": d.get('favorite', False),
                "cloud_snapshot": cloud_states.get(d['id']),
                "integration": integration(d, controls, device_settings, readings, issue),
            })
        result['api_version'] = API_VERSION
        result['features'] = {'scenes_ui':False, 'metadata':True, 'diagnostics':True}
        result['rooms'] = sorted({d['room'] for d in result['devices'] if d['room']})
        return result

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
        else:
            self.hub.close()


def make_server(dashboard, port=8770):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def allowed(self):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts:
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in hosts}:
                return False
            return self.headers.get("Sec-Fetch-Site") != "cross-site"

        def send_data(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return self.send_data(403, {"error": "Origem não permitida."})
            if self.path == "/api/state":
                data = dashboard.snapshot()
                data["token"] = dashboard.token
                return self.send_data(200, data)
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/features.js": ("features.js", "text/javascript; charset=utf-8"),
                      "/api-client.js": ("api-client.js", "text/javascript; charset=utf-8"),
                      "/inventory.js": ("inventory.js", "text/javascript; charset=utf-8"),
                      "/theme.css": ("theme.css", "text/css; charset=utf-8"),
                      "/automacao-ui.css": ("automacao-ui.css", "text/css; charset=utf-8"),
                      "/controls.js": ("controls.js", "text/javascript; charset=utf-8"),
                      "/fonts.css": ("fonts.css", "text/css; charset=utf-8"),
                      "/figtree.ttf": ("figtree.ttf", "font/ttf"),
                      "/jetbrainsmono.ttf": ("jetbrainsmono.ttf", "font/ttf"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path not in assets:
                return self.send_data(404, {"error": "Não encontrado."})
            filename, mime = assets[self.path]
            self.send_data(200, (ASSETS / filename).read_bytes(), mime)

        def do_POST(self):
            if not self.allowed() or not secrets.compare_digest(self.headers.get("X-Local-Token", ""), dashboard.token):
                return self.send_data(403, {"error": "Atualize a página para autorizar a operação local."})
            if self.path not in tuple('/api/'+op for op in ('refresh', 'status', 'command')+dashboard.OPERATIONS):
                return self.send_data(404, {"error": "Não encontrado."})
            if self.headers.get("Content-Type") != "application/json":
                return self.send_data(415, {"error": "Formato inválido."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError()
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError()
                device_id = data.get("id")
                if device_id is not None and not isinstance(device_id, str):
                    raise ValueError()
                operation = self.path.rsplit('/', 1)[-1]
                accepted = dashboard.submit(operation, device_id,
                                            data.get("control"), data if operation in dashboard.OPERATIONS else data.get("action"))
                self.send_data(202 if accepted else 409,
                               {"ok": True} if accepted else {"error": "Há uma operação em andamento. Aguarde."})
            except (ValueError, TypeError, KeyError):
                self.send_data(400, {"error": "Requisição inválida ou canal não permitido."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server
