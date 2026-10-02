import http.client
import json
import threading
import unittest

from test_hub import FakeDevice, fixture
from tuya_local.web import Dashboard, make_server, prepare


def source():
    return [{"id": "light", "mapping": {
        "1": {"code": "switch_1", "type": "Boolean", "values": {}},
        "14": {"code": "relay_status", "type": "Enum", "values": {}},
        "16": {"code": "switch_backlight", "type": "Boolean", "values": {}},
    }}]


def config():
    data = fixture()
    data["devices"][1]["category"] = "tdq"
    return data


class ProfileTests(unittest.TestCase):
    def test_only_explicit_boolean_switches_enabled(self):
        prepared = prepare(config(), source())
        self.assertEqual([c["dp"] for c in prepared["devices"][1]["controls"]], ["1"])

    def test_alarm_and_unknown_mapping_never_expose_controls(self):
        data = config()
        data["devices"][1]["category"] = "mal"
        self.assertEqual(prepare(data, source())["devices"][1]["controls"], [])
        self.assertEqual(prepare(config(), [])["devices"][1]["controls"], [])

    def test_sensor_scale_and_staleness(self):
        mappings = [{"id": "sensor", "mapping": {"1": {"code": "va_temperature", "values": {"scale": 1, "unit": "°C"}}}}]
        dashboard = Dashboard(config(), mappings, factory=FakeDevice)
        dashboard._store({"id": "sensor", "state": "aguardando_evento", "dps": {"1": 235}})
        sensor = next(d for d in dashboard.snapshot()["devices"] if d["id"] == "sensor")
        self.assertEqual(sensor["readings"][0]["value"], 23.5)
        self.assertTrue(sensor["readings"][0]["stale"])


class WebTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = Dashboard(config(), source(), factory=FakeDevice)
        self.server = make_server(self.dashboard, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.dashboard.close()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        h = {"Content-Type": "application/json", "X-Local-Token": self.dashboard.token}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_snapshot_never_contains_keys(self):
        code, body = self.request("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertNotIn(b"0123456789abcdef", body)
        self.assertNotIn(b'"key"', body)
        self.assertNotIn(b'"web_mapping"', body)

    def test_static_server_never_serves_credentials(self):
        for path in ("/tinytuya.json", "/devices.json", "/config.local.json", "/../tinytuya.json"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_foreign_host_origin_and_missing_token_rejected(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"},
                        {"X-Local-Token": ""}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("POST", "/api/refresh", {}, headers)[0], 403)
        self.assertFalse(self.dashboard.busy)

    def test_unmapped_commands_rejected(self):
        good = {"id": "light", "control": 0, "action": "Ligar", "confirmed": True}
        for change in ({"control": -1}, {"control": True}, {"action": "Abrir"}, {"id": "gateway"}):
            self.assertEqual(self.request("POST", "/api/command", dict(good, **change))[0], 400)
        self.assertEqual(self.dashboard.hub.connections, {})

    def test_command_executes_once_and_records_confirmation(self):
        command = {"id": "light", "control": 0, "action": "Ligar"}
        self.assertEqual(self.request("POST", "/api/command", command)[0], 202)
        self.assertEqual(self.dashboard.snapshot()['last_command']['status'], 'pending')
        self.assertEqual(self.request("POST", "/api/command", command)[0], 409)
        self.dashboard._execute(self.dashboard.tasks.get_nowait())
        self.assertEqual(self.dashboard.hub.connections["light"].sent, [("1", True)])
        snapshot = self.dashboard.snapshot()
        self.assertEqual(snapshot["activity"][0]["level"], "success")
        self.assertFalse(snapshot["busy"])
        self.assertEqual(snapshot['last_command']['status'], 'confirmed')

    def test_read_failure_never_sends_command(self):
        device = self.dashboard.hub._connect("light")
        device.responses = [{"Err": "914"}]
        self.dashboard.submit("command", "light", 0, "Ligar")
        self.dashboard._execute(self.dashboard.tasks.get_nowait())
        self.assertEqual(device.sent, [])
        self.assertEqual(self.dashboard.snapshot()["activity"][0]["level"], "error")
        self.assertEqual(self.dashboard.snapshot()['last_command']['status'], 'unconfirmed')


if __name__ == "__main__":
    unittest.main()
