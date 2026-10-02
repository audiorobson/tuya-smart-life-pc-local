"""Uma conexão por gateway; todas as operações são serializadas."""
import copy
import threading
import time
from datetime import datetime, timezone

from .config import pending, validate


class LocalHub:
    def __init__(self, config, factory=None):
        if factory is None:
            import tinytuya
            factory = tinytuya.Device
        self.config = copy.deepcopy(validate(config))
        self.devices = {d["id"]: d for d in self.config["devices"]}
        self.factory = factory
        self.connections = {}
        self.states = {}
        self.heartbeats = {}
        self.lock = threading.RLock()

    def _connect(self, device_id):
        entry = self.devices[device_id]
        issue = pending(entry, self.devices)
        if issue:
            raise ValueError(issue)
        if device_id not in self.connections:
            if entry.get("parent"):
                parent = self._connect(entry["parent"])
                connection = self.factory(device_id, parent=parent, cid=entry["node_id"])
            else:
                connection = self.factory(device_id, entry["ip"], entry["key"],
                                          version=float(entry["version"]), persist=True)
                connection.set_socketTimeout(2)
                connection.set_socketRetryLimit(1)
            self.connections[device_id] = connection
        return self.connections[device_id]

    def _discard(self, device_id):
        root = self.devices[device_id].get("parent") or device_id
        for key in list(self.connections):
            if key == root or self.devices[key].get("parent") == root:
                connection = self.connections.pop(key)
                if key == root:
                    try:
                        connection.close()
                    except Exception:
                        pass
        self.heartbeats.pop(root, None)

    def _record(self, device_id, response):
        previous = self.states.get(device_id, {})
        state = {"id": device_id, "dps": dict(previous.get("dps", {})),
                 "last_seen": previous.get("last_seen"), "state": "sem_resposta", "current_dps": {}}
        if isinstance(response, dict) and isinstance(response.get("dps"), dict) and response["dps"] and not response.get("Error"):
            state["dps"].update(response["dps"])
            state["current_dps"] = dict(response["dps"])
            state.update(state="online", last_seen=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        elif isinstance(response, dict) and response.get("Err"):
            code = str(response["Err"])
            state["error_code"] = code
            state["state"] = {
                "914": "verificar_chave_ou_protocolo", "901": "falha_conexao",
                "902": "sem_resposta", "905": "inacessivel", "907": "nao_suportado",
            }.get(code, "erro_protocolo")
        if self.devices[device_id].get("kind") == "zigbee" and state["state"] == "sem_resposta":
            state["state"] = "aguardando_evento"
        self.states[device_id] = state
        return copy.deepcopy(state)

    def status(self, device_id):
        with self.lock:
            try:
                response = self._connect(device_id).status()
                result = self._record(device_id, response)
                if result["state"] not in ("online", "aguardando_evento"):
                    self._discard(device_id)
                return result
            except ValueError:
                # Não reproduzir mensagens da biblioteca que possam conter credenciais.
                self._discard(device_id)
                issue = pending(self.devices[device_id], self.devices)
                return {"id": device_id, "state": "configuracao_pendente" if issue else "erro_protocolo",
                        "detail": issue or "Verifique a chave e o protocolo."}
            except Exception:
                self._discard(device_id)
                return self._record(device_id, {"Err": "901"})

    def command(self, device_id, control_index, action):
        """Só envia valores explicitamente mapeados e após leitura válida do DP."""
        with self.lock:
            control = self.devices[device_id].get("controls", [])[control_index]
            if action not in control["values"]:
                raise ValueError("Ação não cadastrada.")
            return self.write(device_id, str(control["dp"]), control["values"][action])

    def write(self, device_id, dp, value):
        """Escrita serializada; o chamador deve validar o perfil e os limites."""
        with self.lock:
            state = self.status(device_id)
            dp = str(dp)
            if state["state"] != "online" or dp not in state.get("current_dps", {}):
                raise ValueError("Comando bloqueado: leitura atual do canal não confirmada.")
            try:
                response = self._connect(device_id).set_value(dp, value)
            except Exception:
                self._discard(device_id)
                raise ValueError("Falha ao enviar. O resultado do comando é desconhecido.") from None
            if isinstance(response, dict) and response.get("Error"):
                self._discard(device_id)
                raise ValueError("O dispositivo retornou erro; confirme seu estado antes de repetir.")
            # Não repetir comandos automaticamente após timeout; pode ter havido atuação.
            confirmed = self.status(device_id)
            confirmed["command_confirmed"] = (
                confirmed["state"] == "online" and
                dp in confirmed.get("current_dps", {}) and
                confirmed["current_dps"][dp] == value
            )
            return confirmed

    def events(self):
        """Uma janela curta de recepção por gateway, chamada por worker da interface."""
        updates = []
        with self.lock:
            parents = {d["parent"] for d in self.devices.values() if d.get("parent")}
            for parent_id in parents:
                gateway = None
                try:
                    # Registra todos os filhos para que TinyTuya roteie os eventos.
                    children = [d for d in self.devices.values() if d.get("parent") == parent_id]
                    for child in children:
                        if not pending(child, self.devices):
                            self._connect(child["id"])
                    gateway = self.connections.get(parent_id)
                    if gateway is None:
                        continue
                    now = time.monotonic()
                    if now - self.heartbeats.get(parent_id, 0) >= 9:
                        gateway.heartbeat()
                        self.heartbeats[parent_id] = now
                    gateway.set_socketTimeout(0.2)
                    response = gateway.receive()
                    if not isinstance(response, dict):
                        continue
                    if str(response.get("Err")) in ("901", "905", "914"):
                        updates.append(self._record(parent_id, response))
                        self._discard(parent_id)
                        continue
                    source = response.get("device")
                    for child in children:
                        if ((source is not None and source is self.connections.get(child["id"])) or
                                (child.get("node_id") and response.get("cid") == child["node_id"])):
                            updates.append(self._record(child["id"], response))
                            break
                except Exception:
                    self._discard(parent_id)
                finally:
                    if gateway is not None:
                        gateway.set_socketTimeout(2)
        return updates

    def close(self):
        with self.lock:
            for device_id in list(self.connections):
                if not self.devices[device_id].get("parent"):
                    self._discard(device_id)


def discover(seconds=20):
    from tinytuya import scanner
    return scanner.devices(verbose=False, scantime=seconds, poll=False, color=False)
