"""Perfis de escrita verificados, cenas locais e operações opcionais de nuvem."""
import copy
import json
import re
import time
import uuid
from pathlib import Path

LABELS = {
    'bright_value_1': 'Brilho', 'brightness_min_1': 'Brilho mínimo',
    'led_type_1': 'Tipo de lâmpada', 'relay_status': 'Estado após retorno de energia',
    'switch_type': 'Tipo de interruptor', 'switch_backlight': 'Iluminação do interruptor',
    'voice_vol': 'Volume do painel', 'voice_mic': 'Microfone do painel',
    'mute': 'Silenciar áudio', 'switch_welcome': 'Mensagem de boas-vindas',
}


def profiles(device, functions):
    result = []
    allowed = {f['code'] for f in functions}
    for dp, spec in device.get('web_mapping', {}).items():
        code = spec.get('code', '')
        if code not in allowed or not str(dp).isdigit():
            continue
        if code not in LABELS and not re.fullmatch(r'countdown_[1-4]', code):
            continue
        kind, limits = spec.get('type'), spec.get('values', {})
        if kind not in ('Boolean', 'Integer', 'Enum') or not isinstance(limits, dict):
            continue
        if kind == 'Integer' and not all(type(limits.get(k)) is int for k in ('min', 'max', 'step')):
            continue
        if kind == 'Enum' and not limits.get('range'):
            continue
        result.append({'dp': str(dp), 'code': code, 'name': LABELS.get(code, 'Temporizador canal '+code[-1]),
                       'type': kind, 'limits': limits})
    return result


def check_value(spec, value):
    kind, limits = spec['type'], spec['limits']
    valid = kind == 'Boolean' and type(value) is bool
    if kind == 'Integer':
        valid = (type(value) is int and limits['min'] <= value <= limits['max']
                 and (value-limits['min']) % max(1, limits['step']) == 0)
    if kind == 'Enum':
        valid = isinstance(value, str) and value in limits['range']
    if not valid:
        raise ValueError('Valor fora do tipo ou limites permitidos pelo dispositivo.')


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class Features:
    OPERATIONS = ('cloud-status', 'metadata', 'setting', 'scene-save', 'scene-delete', 'scene-run', 'cloud-scenes', 'cloud-run', 'pair', 'discover', 'sync')

    def init_features(self, capabilities, storage, cloud):
        self.capabilities = capabilities or {}
        self.storage = Path(storage) if storage else None
        self.cloud_factory = cloud
        self.cloud = None
        self.homes = (capabilities or {}).get('homes', [])
        self.cloud_scenes = []
        self.cloud_message = 'Consulte as cenas para verificar a permissão da API Tuya.'
        self.pairing = {}
        self.cloud_states = {}
        self.scenes = []
        if self.storage and self.storage.exists():
            self.scenes = json.loads(self.storage.read_text(encoding='utf-8'))
        self.settings = {d['id']: profiles(d, (capabilities or {}).get('functions', {}).get(d['id'], []))
                         for d in self.hub.devices.values()}

    def validate_step(self, step):
        if not isinstance(step, dict) or not isinstance(step.get('id'), str) or step['id'] not in self.hub.devices:
            raise ValueError('Dispositivo não cadastrado.')
        if 'dp' in step:
            spec = next((s for s in self.settings[step['id']] if s['dp'] == step['dp']), None)
            if spec is None:
                raise ValueError('Configuração não permitida.')
            check_value(spec, step.get('value'))
            return {'id': step['id'], 'dp': step['dp'], 'value': step['value']}
        controls = self.hub.devices[step['id']]['controls']
        n, action = step.get('control'), step.get('action')
        if type(n) is not int or not 0 <= n < len(controls) or not isinstance(action, str) or action not in controls[n]['values']:
            raise ValueError('Canal ou ação não permitido.')
        return {'id': step['id'], 'control': n, 'action': action}

    def validate_feature(self, op, payload):
        if not isinstance(payload, dict):
            raise ValueError('Dados inválidos.')
        if op == 'metadata':
            if not isinstance(payload.get('id'), str) or payload['id'] not in self.hub.devices:
                raise ValueError('Dispositivo não cadastrado.')
            if set(payload) - {'id','name','room','favorite'}:
                raise ValueError('Campo não permitido.')
            for field, limit in (('name',80),('room',60)):
                if field in payload and (not isinstance(payload[field], str) or len(payload[field].strip()) > limit or (field == 'name' and not payload[field].strip())):
                    raise ValueError('Nome ou ambiente inválido.')
            if 'favorite' in payload and type(payload['favorite']) is not bool:
                raise ValueError('Favorito deve ser verdadeiro ou falso.')
            return {k:v.strip() if isinstance(v,str) and k != 'id' else v for k,v in payload.items()}
        if op == 'setting':
            if 'dp' not in payload:
                raise ValueError('Configuração ausente.')
            return self.validate_step(payload)
        if op == 'scene-save':
            name, steps = payload.get('name'), payload.get('steps')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not isinstance(steps, list) or not 1 <= len(steps) <= 30:
                raise ValueError('Informe nome e de 1 a 30 ações.')
            scene_id = payload.get('scene_id') or uuid.uuid4().hex
            if payload.get('scene_id') and not any(s['scene_id'] == scene_id for s in self.scenes):
                raise ValueError('Cena não encontrada.')
            return {'scene_id': scene_id, 'name': name.strip(), 'steps': [self.validate_step(s) for s in steps]}
        if op in ('scene-run', 'scene-delete'):
            scene = next((s for s in self.scenes if s['scene_id'] == payload.get('scene_id')), None)
            if scene is None:
                raise ValueError('Cena não encontrada.')
            if op == 'scene-run':
                for step in scene['steps']:
                    self.validate_step(step)
            return copy.deepcopy(scene)
        if op == 'discover':
            return {}
        if self.cloud_factory is None:
            raise ValueError('Credenciais da nuvem não configuradas neste serviço.')
        if op == 'cloud-status':
            if not isinstance(payload.get('id'), str) or payload['id'] not in self.hub.devices:
                raise ValueError('Dispositivo não cadastrado.')
            if not any(d['id'] == payload['id'] for d in self.source):
                raise ValueError('Dispositivo não importado da conta Tuya.')
            return {'id':payload['id']}
        if op == 'cloud-run':
            scene = next((s for s in self.cloud_scenes if s['scene_id'] == payload.get('scene_id') and s['home_id'] == payload.get('home_id')), None)
            if scene is None:
                raise ValueError('Atualize a lista e selecione uma cena da conta.')
            return scene
        if op == 'pair':
            d = self.hub.devices.get(payload.get('id'))
            if not d or d.get('kind') not in ('panel', 'gateway') or type(payload.get('duration')) is not int or payload['duration'] not in (0, 60):
                raise ValueError('Selecione um gateway e duração de 60 segundos ou parar.')
        return payload

    def cloud_request(self, path, **kwargs):
        if self.cloud is None:
            self.cloud = self.cloud_factory()
        result = self.cloud.cloudrequest(path, **kwargs)
        if not isinstance(result, dict) or not result.get('success'):
            code = str(result.get('code', 'indisponível')) if isinstance(result, dict) else 'indisponível'
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,30}', code):
                code = 'indisponível'
            reason = 'API não assinada no projeto Tuya' if code == '28841101' else 'a Tuya recusou ou não respondeu à solicitação'
            raise ValueError(f'Nuvem: {reason} (código {code}).')
        return result.get('result')

    def run_step(self, step):
        step = self.validate_step(step)
        result = (self.hub.write(step['id'], step['dp'], step['value']) if 'dp' in step else
                  self.hub.command(step['id'], step['control'], step['action']))
        self._store(result)
        if not result.get('command_confirmed'):
            raise ValueError('Resultado não confirmado; execução interrompida. Consulte o equipamento antes de repetir.')

    def execute_feature(self, op, payload):
        if op == 'cloud-status':
            from datetime import datetime, timezone
            device_id = payload['id']
            # Invalidar a consulta anterior antes de tentar novamente, sem tocar no estado LAN.
            with self.lock:
                self.cloud_states.pop(device_id, None)
            response = self.cloud_request('/v1.0/iot-03/devices/'+device_id+'/status')
            if not isinstance(response, list):
                raise ValueError('A Tuya não retornou uma lista de estados.')
            by_code = {s['code']:s.get('value') for s in response if isinstance(s, dict) and isinstance(s.get('code'), str)}
            dps = {str(dp):by_code[s['code']] for dp,s in self.hub.devices[device_id].get('web_mapping', {}).items() if s.get('code') in by_code}
            from .presentation import readings
            items = readings(self.hub.devices[device_id], {'dps':dps})
            with self.lock:
                self.cloud_states[device_id] = {'queried_at':datetime.now(timezone.utc).isoformat(), 'readings':items}
            self._log('Consulta à nuvem concluída. São os últimos valores conhecidos pela Tuya; não confirmam conexão local.', 'success')
        elif op == 'metadata':
            from .config import load, save
            if not self.config_path:
                raise ValueError('Caminho do cadastro não configurado.')
            config = load(self.config_path)
            entry = next(d for d in config['devices'] if d['id'] == payload['id'])
            changes = {k:v for k,v in payload.items() if k != 'id'}
            entry.update(changes)
            save(config, self.config_path)
            with self.lock:
                self.hub.devices[payload['id']].update(changes)
            self._log('Organização do dispositivo salva neste computador.', 'success')
        elif op == 'setting':
            self.run_step(payload)
            self._log('Configuração aplicada e verificada no equipamento.', 'success')
        elif op in ('scene-save', 'scene-delete'):
            updated = [s for s in self.scenes if s['scene_id'] != payload['scene_id']]
            if op == 'scene-save':
                updated.append(payload)
            if self.storage:
                atomic_json(self.storage, updated)
            with self.lock:
                self.scenes = updated
            self._log('Cena salva.' if op == 'scene-save' else 'Cena excluída.', 'success')
        elif op == 'scene-run':
            for n, step in enumerate(payload['steps'], 1):
                self.run_step(step)
                self._log(f"{payload['name']}: ação {n}/{len(payload['steps'])} confirmada.", 'success')
            self._log(f"Cena concluída: {payload['name']}.", 'success')
        elif op == 'cloud-scenes':
            scenes = []
            try:
                if not self.homes:
                    raise ValueError('Nenhuma casa Tuya cadastrada no cache de capacidades.')
                for home in self.homes:
                    items = self.cloud_request('/v1.1/homes/'+home['id']+'/scenes')
                    for s in items:
                        if s.get('enabled', True):
                            scenes.append({'home_id': home['id'], 'scene_id': str(s['scene_id']), 'name': s.get('name', 'Cena Tuya')})
            except ValueError as exc:
                with self.lock:
                    self.cloud_scenes = []
                    self.cloud_message = str(exc)
                raise
            with self.lock:
                self.cloud_scenes = scenes
                self.cloud_message = f'{len(scenes)} cenas disponíveis na conta Tuya.'
        elif op == 'cloud-run':
            self.cloud_request(f"/v1.0/homes/{payload['home_id']}/scenes/{payload['scene_id']}/trigger", action='POST')
            self._log('Execução da cena aceita pela Tuya. Atualize os estados para verificar os equipamentos.')
        elif op == 'pair':
            result = self.cloud_request(f"/v1.0/devices/{payload['id']}/enabled-sub-discovery", action='PUT', query={'duration': payload['duration']})
            if result is not True:
                raise ValueError('Gateway não confirmou a solicitação de busca.')
            with self.lock:
                self.pairing[payload['id']] = time.time()+payload['duration']
            self._log('Tuya aceitou a busca Zigbee por 60s. Coloque o acessório em pareamento no fabricante.' if payload['duration'] else 'Tuya aceitou encerrar a busca Zigbee.')
        elif op in ('discover', 'sync'):
            self.update_inventory(op)

    def update_inventory(self, operation):
        from .config import load, save, merge_discovery, import_devices
        from .service import discover, LocalHub
        from .web import prepare
        if not self.config_path:
            raise ValueError('Caminho do cadastro não configurado.')
        config = load(self.config_path)
        source = self.source
        capabilities = copy.deepcopy(self.capabilities)
        if operation == 'discover':
            found = discover(12)
            config = merge_discovery(config, found)
            message = f'Busca local concluída: {len(found)} anúncios recebidos. Dispositivos Zigbee aparecem pelo gateway.'
        else:
            if self.cloud is None:
                self.cloud = self.cloud_factory()
            source = self.cloud.getdevices(oldlist=self.source, include_map=True)
            if not isinstance(source, list) or not source:
                raise ValueError('Não foi possível importar o cadastro da Tuya.')
            by_id = {d['id']: d for d in source}
            for device in list(source):
                if device.get('category') in ('wg2', 'dgnzk'):
                    children = self.cloud_request('/v1.0/devices/'+device['id']+'/sub-devices')
                    for child in children:
                        entry = by_id.get(child.get('id') or child.get('device_id'))
                        if entry is not None:
                            entry['parent'] = device['id']
                            if child.get('node_id'):
                                entry['node_id'] = child['node_id']
                if device.get('category') in ('kg', 'tdq', 'tgq', 'dgnzk'):
                    response = self.cloud.getfunctions(device['id'])
                    if response.get('success'):
                        capabilities.setdefault('functions', {})[device['id']] = response['result'].get('functions', [])
            config = import_devices(config, source)
            atomic_json(self.config_path.with_name('devices.json'), source)
            atomic_json(self.config_path.with_name('capabilities.local.json'), capabilities)
            message = f'Cadastro sincronizado: {len(source)} dispositivos na conta. Consulte os estados ou busque IPs locais.'
        new_hub = LocalHub(prepare(config, source, capabilities), factory=self.hub.factory)
        new_settings = {d['id']: profiles(d, capabilities.get('functions', {}).get(d['id'], [])) for d in new_hub.devices.values()}
        save(config, self.config_path)
        old_hub = self.hub
        with self.lock:
            self.hub, self.settings = new_hub, new_settings
            self.source, self.capabilities = source, capabilities
            self.states = {}
        old_hub.close()
        self._log(message, 'success')

    def feature_snapshot(self):
        return {'scenes': copy.deepcopy(self.scenes), 'cloud_scenes': copy.deepcopy(self.cloud_scenes),
                'cloud_message': self.cloud_message, 'cloud_available': self.cloud_factory is not None}
