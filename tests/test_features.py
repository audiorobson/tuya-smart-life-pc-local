import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_web import config, source
from test_hub import FakeDevice
from tuya_local.web import Dashboard
from tuya_local.features import check_value


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Path(self.temp.name)/'scenes.local.json'
        self.panel = Dashboard(config(), source(), factory=FakeDevice, storage=self.storage)

    def tearDown(self):
        self.panel.close()
        self.temp.cleanup()

    def run_op(self, op, payload):
        self.assertTrue(self.panel.submit(op, action=payload))
        self.panel._execute(self.panel.tasks.get_nowait())

    def test_scene_save_restart_and_delete_do_not_actuate(self):
        self.run_op('scene-save', {'name':'Teste', 'steps':[{'id':'light','control':0,'action':'Ligar'}]})
        self.assertEqual(self.panel.hub.connections, {})
        scene = self.panel.scenes[0]
        other = Dashboard(config(), source(), factory=FakeDevice, storage=self.storage)
        self.assertEqual(other.scenes, [scene])
        other.close()
        self.run_op('scene-delete', {'scene_id':scene['scene_id']})
        self.assertEqual(json.loads(self.storage.read_text()), [])

    def test_scene_stops_on_failure_without_resending(self):
        self.run_op('scene-save', {'name':'Teste', 'steps':[{'id':'light','control':0,'action':'Ligar'}, {'id':'light','control':0,'action':'Desligar'}]})
        device = self.panel.hub._connect('light')
        device.responses = [{'Err':'914'}]
        self.run_op('scene-run', {'scene_id':self.panel.scenes[0]['scene_id']})
        self.assertEqual(device.sent, [])
        self.assertEqual(self.panel.activity[0]['level'], 'error')

    def test_scene_reports_partial_completion_and_stops(self):
        steps=[{'id':'light','control':0,'action':'Ligar'}]*3
        self.run_op('scene-save', {'name':'Parcial','steps':steps})
        ok={'id':'light','state':'online','current_dps':{'1':True},'command_confirmed':True}
        with patch.object(self.panel.hub,'command',side_effect=[ok,ValueError('Falha controlada')]) as command:
            self.run_op('scene-run',{'scene_id':self.panel.scenes[0]['scene_id']})
        self.assertEqual(command.call_count,2)
        self.assertEqual(self.panel.activity[0]['level'],'error')
        self.assertIn('ação 1/3', self.panel.activity[1]['text'])

    def test_discovery_preserves_keys_and_reloads_inventory(self):
        from tuya_local.config import save, load
        self.panel.config_path=Path(self.temp.name)/'config.local.json'
        save(config(),self.panel.config_path)
        with patch('tuya_local.service.discover',return_value={'192.168.1.9':{'gwId':'gateway','version':'3.5'}}):
            self.run_op('discover',{})
        self.assertEqual(self.panel.hub.devices['gateway']['ip'],'192.168.1.9')
        self.assertEqual(load(self.panel.config_path)['devices'][0]['key'],'0123456789abcdef')
        self.assertEqual(self.panel.states,{})

    def test_invalid_scene_never_persists(self):
        for step in ({'id':'light','control':99,'action':'Ligar'}, {'id':'light','dp':'999','value':1}):
            with self.assertRaises(ValueError):
                self.panel.submit('scene-save', action={'name':'Bad','steps':[step]})
        self.assertFalse(self.storage.exists())

    def test_integer_enum_boolean_validation(self):
        spec={'type':'Integer','limits':{'min':10,'max':1000,'step':10}}
        check_value(spec, 500)
        for value in (True, 0, 1001, 11, '50', 50.0):
            with self.assertRaises(ValueError):
                check_value(spec, value)
        with self.assertRaises(ValueError):
            check_value({'type':'Enum','limits':{'range':['led']}}, 'reset')
        with self.assertRaises(ValueError):
            check_value({'type':'Boolean','limits':{}}, 1)

    def test_cloud_error_is_reported_without_credentials(self):
        class Cloud:
            def cloudrequest(self, *args, **kwargs):
                return {'success':False, 'code':28841101, 'msg':'secret payload'}
        self.panel.cloud_factory=Cloud
        self.panel.homes=[{'id':'123'}]
        self.run_op('cloud-scenes', {})
        self.assertIn('28841101', self.panel.cloud_message)
        self.assertNotIn('secret', json.dumps(self.panel.snapshot()))

    def test_pair_rejects_non_gateway_and_bad_duration(self):
        self.panel.cloud_factory=lambda:None
        for payload in ({'id':'light','duration':60},{'id':'gateway','duration':3600},{'id':'gateway','duration':True}):
            with self.assertRaises(ValueError):
                self.panel.submit('pair', action=payload)

    def test_gateway_pair_and_stop_exact_request(self):
        calls=[]
        class Cloud:
            def cloudrequest(self,path,**kwargs):
                calls.append((path,kwargs))
                return {'success':True,'result':True}
        self.panel.cloud_factory=Cloud
        for duration in (60,0):
            self.run_op('pair', {'id':'gateway','duration':duration})
            self.assertEqual(calls[-1], ('/v1.0/devices/gateway/enabled-sub-discovery', {'action':'PUT','query':{'duration':duration}}))

    def test_settings_require_cloud_function_and_local_mapping(self):
        src=source()
        src[0]['mapping']['2']={'code':'bright_value_1','type':'Integer','values':{'min':10,'max':1000,'step':1}}
        p=Dashboard(config(),src,factory=FakeDevice,capabilities={'functions':{'light':[{'code':'bright_value_1'}]}})
        self.assertEqual(p.settings['light'][0]['dp'],'2')
        with self.assertRaises(ValueError):
            p.submit('setting',action={'id':'light','dp':'2','value':1001})
        p.submit('setting',action={'id':'light','dp':'2','value':500})
        p._execute(p.tasks.get_nowait())
        self.assertEqual(p.hub.connections['light'].sent, []) # DP absent in fresh response
        p.hub.connections['light'].responses=[{'dps':{'2':100}}]
        p.submit('setting',action={'id':'light','dp':'2','value':500})
        p._execute(p.tasks.get_nowait())
        self.assertEqual(p.hub.connections['light'].sent,[('2',500)])
        self.assertEqual(p.activity[0]['level'],'success')
        p.close()
