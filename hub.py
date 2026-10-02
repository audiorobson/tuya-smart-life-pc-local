"""Entrada do novo gerenciador local: GUI por padrão, CLI para diagnóstico."""
import argparse
import json

from tuya_local.config import DEFAULT_CONFIG, import_devices, load, merge_discovery, pending, save
from tuya_local.service import LocalHub, discover


def main():
    parser = argparse.ArgumentParser(description="Gerenciador local Tuya / Zigbee")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Cadastro local (contém chaves)")
    commands = parser.add_subparsers(dest="command")
    scan = commands.add_parser("discover", help="Descobre e salva IPs por ID, sem acionar equipamentos")
    scan.add_argument("--seconds", type=int, default=20, choices=range(1, 121), metavar="1..120")
    importer = commands.add_parser("import", help="Importa devices.json exportado pelo TinyTuya")
    importer.add_argument("file")
    commands.add_parser("list", help="Lista inventário sem revelar chaves")
    status = commands.add_parser("status", help="Consulta estado de um dispositivo")
    status.add_argument("id")
    args = parser.parse_args()
    try:
        config = load(args.config)
        if args.command is None:
            from tuya_local.ui import run
            run(args.config)
            return 0
        if args.command == "discover":
            config = merge_discovery(config, discover(args.seconds))
            save(config, args.config)
        elif args.command == "import":
            with open(args.file, encoding="utf-8-sig") as stream:
                source = json.load(stream)
            config = import_devices(config, source)
            save(config, args.config)
        elif args.command == "status":
            if args.id not in {d["id"] for d in config["devices"]}:
                raise ValueError("ID não cadastrado.")
            hub = LocalHub(config)
            try:
                print(json.dumps(hub.status(args.id), ensure_ascii=True, indent=2))
            finally:
                hub.close()
            return 0
        by_id = {d["id"]: d for d in config["devices"]}
        for d in config["devices"]:
            print(json.dumps({"id": d["id"], "name": d.get("name", d["id"]),
                              "kind": d.get("kind", "wifi"), "ip": d.get("ip", ""),
                              "parent": d.get("parent", ""), "version": d.get("version"),
                              "readiness": pending(d, by_id) or "Pronto para testar"}, ensure_ascii=True))
        return 0
    except (ValueError, OSError) as exc:
        # JSONDecodeError pode incluir trechos de dados em algumas ferramentas; saída fixa.
        message = "Arquivo JSON inválido." if isinstance(exc, json.JSONDecodeError) else (
            str(exc) if isinstance(exc, ValueError) else "Não foi possível acessar o arquivo ou a rede.")
        print("Erro:", message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
