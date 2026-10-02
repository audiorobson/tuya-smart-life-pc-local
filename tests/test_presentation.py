import tempfile
import unittest
from pathlib import Path
from test_web import config, source
from test_hub import FakeDevice
from tuya_local.config import save, load, import_devices
from tuya_local.web import Dashboard
from tuya_local.presentation import readings


class PresentationTests(unittest.TestCase):
    def test_cloud_readings_never_enable_local_commands(self):
        class Cloud:
            def cloudrequest(self,path,**kwargs):
                return {'success':True,'result':[{'code':'battery_percentage','value':87}, {'code':'unlock_password','value':999}]}
        src=source()
        src[0]['mapping']['9']={'code':'battery_percentage','values':{'unit':'%'}}
        panel=Dashboard(config(),src,factory=FakeDevice,cloud=Cloud)
        panel.submit('cloud-status',action={'id':'light'})
        panel._execute(panel.tasks.get_nowait())
        d=next(d for d in panel.snapshot()['devices'] if d['id']=='light')
        self.assertFalse(d['controls'][0]['enabled'])
        self.assertEqual(d['cloud_snapshot']['readings'][0]['value'],87)
        self.assertNotIn('unlock_password',str(d))
        self.assertEqual(panel.hub.connections,{})
        panel.close()

    def test_boolean_enum_missing_and_stale_readings(self):
        device={'web_mapping':{
            '1':{'code':'doorcontact_state','values':{}},
            '2':{'code':'pir','values':{'range':['pir','none']}},
            '3':{'code':'watersensor_state','values':{'range':['alarm','normal']}},
            '4':{'code':'unlock_password','values':{}},
        }}
        state={'state':'online','dps':{'1':False,'2':'pir','4':123},'current_dps':{'1':False}}
        values=readings(device,state)
        self.assertEqual(len(values),3)
        self.assertEqual(values[0]['value'],'Inativo')
        self.assertFalse(values[0]['stale'])
        self.assertTrue(values[1]['stale'])
        self.assertEqual(values[2]['value'],'Sem leitura')
        self.assertFalse(values[2]['available'])
        self.assertNotIn('unlock_password',str(values))

    def test_mapping_scales_without_inventing_units(self):
        d={'web_mapping':{'1':{'code':'va_temperature','values':{'scale':1,'unit':'°C'}},'2':{'code':'va_battery','values':{}}}}
        result=readings(d,{'state':'online','dps':{'1':234,'2':21},'current_dps':{'1':234,'2':21}})
        self.assertEqual(result[0]['value'],23.4)
        self.assertEqual(result[1]['unit'],'')

    def test_metadata_survives_reload_and_import_without_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json'
            save(config(),path)
            panel=Dashboard(config(),source(),factory=FakeDevice,config_path=path)
            panel.submit('metadata',action={'id':'light','name':' Luz sala ','room':' Sala ','favorite':True})
            panel._execute(panel.tasks.get_nowait())
            self.assertEqual(panel.hub.connections,{})
            persisted=load(path)
            merged=import_devices(persisted,[{'id':'light','name':'Nome da nuvem'}])
            device=next(d for d in merged['devices'] if d['id']=='light')
            self.assertEqual((device['name'],device['room'],device['favorite']),('Luz sala','Sala',True))
            snapshot=panel.snapshot()
            self.assertEqual(snapshot['api_version'],1)
            self.assertEqual(snapshot['rooms'],['Sala'])
            self.assertFalse(snapshot['features']['scenes_ui'])
            panel.close()

    def test_metadata_does_not_allow_access_settings_or_invalid_values(self):
        panel=Dashboard(config(),source(),factory=FakeDevice)
        for changes in ({'key':'new-secret'},{'ip':'1.1.1.1'},{'name':''},{'room':True},{'favorite':'yes'},{'room':'x'*61}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                panel.submit('metadata',action={'id':'light',**changes})
        self.assertFalse(panel.busy)
        panel.close()
