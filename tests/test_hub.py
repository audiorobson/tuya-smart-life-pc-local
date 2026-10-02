import copy
import json
import tempfile
import unittest
from pathlib import Path

from tuya_local.config import import_devices, load, merge_discovery, pending, save, validate
from tuya_local.service import LocalHub


def fixture():
    return {"schema_version": 1, "devices": [
        {"id": "gateway", "kind": "gateway", "ip": "192.168.1.5", "version": "3.4", "key": "0123456789abcdef"},
        {"id": "light", "kind": "zigbee", "parent": "gateway", "node_id": "node1", "controls": [
            {"name": "Luz", "dp": "1", "values": {"Ligar": True, "Desligar": False}}]},
        {"id": "sensor", "kind": "zigbee", "parent": "gateway", "node_id": "node2"}
    ]}


class FakeDevice:
    def __init__(self, device_id, *args, **kwargs):
        self.id, self.args, self.kwargs = device_id, args, kwargs
        self.responses = [{"dps": {"1": False}}]
        self.sent = []
        self.closed = False
        self.event = None

    def set_socketTimeout(self, value):
        self.timeout = value

    def set_socketRetryLimit(self, value):
        pass

    def status(self):
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def set_value(self, dp, value):
        self.sent.append((dp, value))
        self.responses = [{"dps": {dp: value}}]
        return {"dps": {dp: value}}

    def heartbeat(self):
        pass

    def receive(self):
        return self.event

    def close(self):
        self.closed = True


class ConfigTests(unittest.TestCase):
    def test_cloud_sub_flag_does_not_turn_gateways_panels_or_ir_into_zigbee(self):
        source = [
            {"id": "p", "category": "dgnzk", "sub": True},
            {"id": "g", "category": "wg2", "sub": True},
            {"id": "ir", "category": "infrared_ac", "sub": True, "node_id": "ir1"},
        ]
        result = import_devices({"schema_version": 1, "devices": []}, source)
        self.assertEqual([d["kind"] for d in result["devices"]], ["panel", "gateway", "subdevice"])
        self.assertIn("específica", pending(result["devices"][2], {}))

    def test_round_trip_and_no_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.local.json"
            self.assertEqual(load(path)["devices"], [])
            save(fixture(), path)
            self.assertEqual(load(path), fixture())

    def test_discovery_updates_by_id_and_preserves_secrets_controls_and_missing_devices(self):
        config = fixture()
        merged = merge_discovery(config, {"192.168.1.8": {"gwId": "gateway", "version": "3.5"}})
        self.assertEqual(merged["devices"][0]["ip"], "192.168.1.8")
        self.assertEqual(merged["devices"][0]["key"], config["devices"][0]["key"])
        self.assertEqual(merged["devices"][1:], config["devices"][1:])
        self.assertEqual(config, fixture())

    def test_discovery_does_not_guess_gateway_or_panel_type(self):
        config = merge_discovery({"schema_version": 1, "devices": []},
                                 {"192.168.1.8": {"gwId": "new", "version": "3.5"}})
        self.assertEqual(config["devices"][0]["kind"], "unknown")

    def test_wizard_import_retains_customizations_and_links_children(self):
        config = fixture()
        config["devices"][0]["kind"] = "panel"
        config["devices"][0]["name"] = "Meu painel"
        imported = import_devices(config, [{"id": "gateway", "name": "Nome nuvem", "key": "fedcba9876543210"},
                                            {"id": "new", "sub": True, "parent": "gateway", "node_id": "node3"}])
        self.assertEqual(imported["devices"][0]["name"], "Meu painel")
        self.assertEqual(imported["devices"][0]["kind"], "panel")
        self.assertEqual(imported["devices"][-1]["kind"], "zigbee")
        self.assertEqual(imported["devices"][1]["controls"], config["devices"][1]["controls"])

    def test_unknown_parent_remains_pending(self):
        imported = import_devices({"schema_version": 1, "devices": []},
                                  [{"id": "sensor", "sub": True, "parent": "", "node_id": "abc"}])
        self.assertEqual(pending(imported["devices"][0], {}), "Falta associar gateway")

    def test_missing_gateway_import_creates_pending_stub(self):
        imported = import_devices({"schema_version": 1, "devices": []},
                                  [{"id": "sensor", "parent": "gateway", "node_id": "abc"}])
        by_id = {d["id"]: d for d in imported["devices"]}
        self.assertEqual(by_id["gateway"]["kind"], "gateway")
        self.assertIn("Gateway:", pending(by_id["sensor"], by_id))

    def test_rejects_duplicates_cycles_and_duplicate_nodes(self):
        for mode in ("id", "cycle", "node"):
            with self.subTest(mode=mode):
                config = fixture()
                if mode == "id":
                    config["devices"].append(copy.deepcopy(config["devices"][0]))
                elif mode == "cycle":
                    config["devices"][0]["parent"] = "light"
                else:
                    config["devices"][2]["node_id"] = "node1"
                with self.assertRaises(ValueError):
                    validate(config)

    def test_invalid_save_preserves_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.local.json"
            save(fixture(), path)
            with self.assertRaises(ValueError):
                save({"devices": []}, path)
            self.assertEqual(load(path), fixture())


class HubTests(unittest.TestCase):
    def setUp(self):
        self.hub = LocalHub(fixture(), factory=FakeDevice)

    def tearDown(self):
        self.hub.close()

    def test_siblings_share_gateway_and_use_correct_cid(self):
        one = self.hub._connect("light")
        two = self.hub._connect("sensor")
        self.assertIs(one.kwargs["parent"], two.kwargs["parent"])
        self.assertEqual(one.kwargs["cid"], "node1")
        self.assertEqual(two.kwargs["cid"], "node2")
        self.assertNotIn("local_key", one.kwargs)

    def test_pending_config_never_connects(self):
        config = fixture()
        config["devices"][0]["key"] = ""
        def fail(*args, **kwargs):
            self.fail("Não deve conectar sem chave")
        hub = LocalHub(config, fail)
        self.assertEqual(hub.status("light")["state"], "configuracao_pendente")

    def test_sleeping_sensor_preserves_timestamp_and_values(self):
        sensor = self.hub._connect("sensor")
        first = self.hub.status("sensor")
        sensor.responses = [{"Err": "902"}]
        second = self.hub.status("sensor")
        self.assertEqual(second["state"], "aguardando_evento")
        self.assertEqual(second["dps"], first["dps"])
        self.assertEqual(second["last_seen"], first["last_seen"])

    def test_read_failure_blocks_command(self):
        light = self.hub._connect("light")
        light.responses = [{"Err": "914", "Payload": "SECRET"}]
        with self.assertRaises(ValueError):
            self.hub.command("light", 0, "Ligar")
        self.assertEqual(light.sent, [])
        self.assertNotIn("SECRET", json.dumps(self.hub.states))

    def test_stale_channel_never_authorizes_write(self):
        light = self.hub._connect("light")
        self.hub.status("light")
        light.responses = [{"dps": {"2": 20}}]
        with self.assertRaises(ValueError):
            self.hub.command("light", 0, "Ligar")
        self.assertEqual(light.sent, [])

    def test_mapped_command_routes_and_confirms(self):
        result = self.hub.command("light", 0, "Ligar")
        self.assertTrue(result["command_confirmed"])
        self.assertEqual(self.hub.connections["light"].sent, [("1", True)])
        self.assertEqual(self.hub.connections["gateway"].sent, [])

    def test_unmapped_action_never_connects(self):
        with self.assertRaises(ValueError):
            self.hub.command("light", 0, "Abrir")
        self.assertEqual(self.hub.connections, {})

    def test_event_routes_to_correct_child(self):
        self.hub._connect("light")
        self.hub.connections["gateway"].event = {"cid": "node2", "dps": {"1": 235}}
        updates = self.hub.events()
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["id"], "sensor")
        self.assertEqual(updates[0]["dps"], {"1": 235})

    def test_reconnect_rebuilds_gateway_and_children(self):
        old = self.hub._connect("light")
        old.responses = [{"Err": "901"}]
        self.hub.status("light")
        self.assertTrue(old.kwargs["parent"].closed)
        new = self.hub._connect("light")
        self.assertIsNot(old.kwargs["parent"], new.kwargs["parent"])


if __name__ == "__main__":
    unittest.main()
