"""Cadastro local. Nenhuma credencial é incluída nos relatórios de diagnóstico."""
import copy
import ipaddress
import json
import os
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.local.json"
KINDS = ("unknown", "wifi", "gateway", "zigbee", "panel", "subdevice")
VERSIONS = (3.1, 3.2, 3.3, 3.4, 3.5)


def validate(config):
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Formato inválido: schema_version deve ser 1.")
    devices = config.get("devices")
    if not isinstance(devices, list):
        raise ValueError("devices deve ser uma lista.")
    ids = set()
    for d in devices:
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"].strip():
            raise ValueError("Cada dispositivo precisa de um ID.")
        if d["id"] in ids:
            raise ValueError("Há IDs duplicados no cadastro.")
        ids.add(d["id"])
        if d.get("kind", "wifi") not in KINDS:
            raise ValueError("Tipo de dispositivo inválido.")
        for field in ("name", "room", "ip", "key", "parent", "node_id"):
            if field in d and not isinstance(d[field], str):
                raise ValueError(f"O campo {field} deve ser texto.")
        if d.get("version") not in (None, ""):
            try:
                version = float(d["version"])
            except (TypeError, ValueError):
                raise ValueError("Versão de protocolo inválida.") from None
            if version not in VERSIONS:
                raise ValueError("Versão de protocolo não suportada.")
        if d.get("ip"):
            try:
                address = ipaddress.ip_address(d["ip"])
                if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
                    raise ValueError()
            except ValueError:
                raise ValueError("Informe um endereço IPv4 da rede local.") from None
        controls = d.get("controls", [])
        if not isinstance(controls, list):
            raise ValueError("controls deve ser uma lista.")
        for control in controls:
            if not isinstance(control, dict) or not str(control.get("dp", "")).isdigit():
                raise ValueError("Cada controle precisa de um DP numérico.")
            values = control.get("values")
            if not isinstance(values, dict) or not values:
                raise ValueError("Cada controle precisa de ações e valores explícitos.")
            if any(not isinstance(v, (str, bool, int, float)) for v in values.values()):
                raise ValueError("Valores de controles devem ser texto, booleano ou número.")
    by_id = {d["id"]: d for d in devices}
    pairs = set()
    for d in devices:
        parent = d.get("parent")
        if parent:
            if parent not in by_id or parent == d["id"]:
                raise ValueError("Gateway inexistente ou referência ao próprio dispositivo.")
            gateway = by_id[parent]
            if gateway.get("parent") or gateway.get("kind") not in ("gateway", "panel"):
                raise ValueError("O pai deve ser um gateway ou painel sem outro pai.")
            if d.get("node_id"):
                pair = (parent, d["node_id"])
                if pair in pairs:
                    raise ValueError("Há node_id duplicado no mesmo gateway.")
                pairs.add(pair)
    return config


def load(path=DEFAULT_CONFIG):
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "devices": []}
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("O cadastro não é um JSON válido.") from None
    return validate(config)


def save(config, path=DEFAULT_CONFIG):
    validate(config)
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def merge_discovery(config, discovered):
    result = copy.deepcopy(config)
    by_id = {d["id"]: d for d in result["devices"]}
    for ip, item in discovered.items():
        device_id = item.get("gwId") or item.get("id")
        if not device_id:
            continue
        if device_id not in by_id:
            entry = {"id": device_id, "name": device_id, "kind": "unknown", "controls": []}
            result["devices"].append(entry)
            by_id[device_id] = entry
        entry = by_id[device_id]
        if entry.get("parent") or entry.get("kind") == "zigbee":
            continue
        entry["ip"] = item.get("ip") or ip
        if item.get("version"):
            entry["version"] = str(item["version"])
    return validate(result)


def import_devices(config, source):
    """Importa devices.json do wizard. Associação ambígua exige edição manual."""
    if not isinstance(source, list):
        raise ValueError("Selecione o devices.json (lista) exportado pelo TinyTuya.")
    result = copy.deepcopy(config)
    by_id = {d["id"]: d for d in result["devices"]}
    seen = set()
    for item in source:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Item importado sem ID válido.")
        if item["id"] in seen:
            raise ValueError("Arquivo contém IDs repetidos; use o devices.json do wizard.")
        seen.add(item["id"])
        entry = by_id.get(item["id"])
        if entry is None:
            entry = {"id": item["id"], "name": item.get("name") or item["id"], "kind": "unknown", "controls": []}
            by_id[item["id"]] = entry
            result["devices"].append(entry)
        for field in ("key", "ip", "version", "node_id", "category", "product_name"):
            if item.get(field):
                entry[field] = item[field]
        parent = item.get("parent") or item.get("gateway_id")
        if parent:
            entry["parent"] = parent
        category = item.get("category", "")
        if category == "dgnzk":
            entry["kind"] = "panel"
        elif category == "wg2":
            entry["kind"] = "gateway"
        elif category.startswith("infrared_"):
            entry["kind"] = "subdevice"
        elif item.get("sub") or "parent" in item or parent or item.get("node_id"):
            entry["kind"] = "zigbee"
        if entry.get("name") == entry["id"] and item.get("name"):
            entry["name"] = item["name"]
    # O wizard pode deixar o pai vazio: não inferir só pela chave compartilhada.
    for entry in list(result["devices"]):
        parent = entry.get("parent")
        if not parent:
            continue
        if parent not in by_id:
            stub = {"id": parent, "name": parent, "kind": "gateway", "controls": []}
            by_id[parent] = stub
            result["devices"].append(stub)
        elif by_id[parent].get("kind") != "panel":
            by_id[parent]["kind"] = "gateway"
    return validate(result)


def pending(device, by_id):
    if device.get("kind") == "subdevice":
        return "Subdispositivo requer integração específica do modelo"
    if device.get("parent") or device.get("kind") == "zigbee":
        if not device.get("parent"):
            return "Falta associar gateway"
        if not device.get("node_id"):
            return "Falta node_id"
        gateway_issue = pending(by_id[device["parent"]], by_id)
        return "Gateway: " + gateway_issue if gateway_issue else ""
    if not device.get("ip"):
        return "Falta IP"
    if len(device.get("key", "").encode("utf-8")) != 16:
        return "Falta chave local válida (16 bytes)"
    if not device.get("version"):
        return "Falta versão do protocolo"
    return ""
