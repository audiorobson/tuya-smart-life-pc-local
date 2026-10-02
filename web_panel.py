"""Execute com o Python do ambiente virtual e abra localhost:8770."""
import argparse
import json
from pathlib import Path

from tuya_local.config import DEFAULT_CONFIG, load
from tuya_local.web import Dashboard, make_server


def main():
    parser = argparse.ArgumentParser(description="Painel web Tuya restrito a este computador")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    mapping_path = config_path.with_name("devices.json")
    source = json.loads(mapping_path.read_text(encoding="utf-8-sig")) if mapping_path.exists() else []
    if not isinstance(source, list):
        raise SystemExit("devices.json precisa conter a lista exportada pelo TinyTuya.")
    capability_path = config_path.with_name('capabilities.local.json')
    capabilities = json.loads(capability_path.read_text(encoding='utf-8')) if capability_path.exists() else {}
    credential_path = config_path.with_name('tinytuya.json')
    def cloud_factory():
        import tinytuya
        return tinytuya.Cloud(**json.loads(credential_path.read_text(encoding='utf-8-sig')))
    dashboard = Dashboard(load(config_path), source, capabilities=capabilities,
                          storage=config_path.with_name('scenes.local.json'),
                          cloud=cloud_factory if credential_path.exists() else None, config_path=config_path)
    server = make_server(dashboard, args.port)
    dashboard.start()
    print(f"Ativ Labs: http://127.0.0.1:{server.server_port} — Ctrl+C para encerrar.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        dashboard.close()


if __name__ == "__main__":
    main()
