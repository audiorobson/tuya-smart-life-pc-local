"""Contrato público de apresentação; nunca inclui chaves ou DPs arbitrários."""
import math

API_VERSION = 1
READINGS = {
    'temp_current':'Temperatura', 'humidity_value':'Umidade',
    'va_temperature':'Temperatura', 'va_humidity':'Umidade',
    'battery_percentage':'Bateria', 'va_battery':'Bateria',
    'doorcontact_state':'Contato da porta', 'pir':'Movimento',
    'watersensor_state':'Sensor de água', 'battery_state':'Nível da bateria',
    'charge_state':'Carregando', 'master_mode':'Modo do alarme',
    'closed_opened':'Estado da porta', 'switch_mode1':'Último evento do botão',
}
TEXT = {'pir':'Movimento detectado', 'none':'Sem detecção', 'alarm':'Alerta',
        'normal':'Normal', 'high':'Alto', 'medium':'Médio', 'low':'Baixo',
        'poweroff':'Sem energia', 'disarmed':'Desarmado', 'arm':'Armado',
        'home':'Modo casa', 'sos':'SOS', 'unknown':'Desconhecido',
        'open':'Aberta', 'closed':'Fechada', 'click':'Clique simples',
        'double_click':'Clique duplo', 'press':'Pressionado'}


def readings(device, state):
    result = []
    for dp, spec in device.get('web_mapping', {}).items():
        code = spec.get('code')
        if code not in READINGS:
            continue
        raw = state.get('dps', {}).get(str(dp))
        limits = spec.get('values', {})
        if not isinstance(limits, dict):
            continue
        unit = ''
        if raw is None:
            value = 'Sem leitura'
        elif type(raw) is bool:
            value = 'Ativo' if raw else 'Inativo'
        elif type(raw) in (int, float):
            scale = limits.get('scale', 0)
            if type(scale) is not int or not 0 <= scale <= 6 or not math.isfinite(raw):
                continue
            value = round(raw / 10**scale, scale)
            unit = limits.get('unit', '')
        elif isinstance(raw, str) and raw in limits.get('range', []):
            value = TEXT.get(raw, raw)
        else:
            continue
        result.append({'code':code, 'name':READINGS[code], 'value':value, 'unit':unit,
                       'available':raw is not None,
                       'stale':state.get('state') != 'online' or str(dp) not in state.get('current_dps', {}),
                       'widget':'metric' if type(value) in (int, float) else 'status'})
    return result


def integration(device, controls, settings, measurements, issue):
    writable = any(c['enabled'] for c in controls) or any(s['enabled'] for s in settings)
    return {'transport':'gateway_lan' if device.get('parent') else 'lan',
            'writable':writable, 'control_count':len(controls),
            'setting_count':len(settings), 'reading_count':len(measurements),
            'blocker':issue or ('' if writable else 'Sem controle disponível na leitura atual'),
            'pairing':'cloud_request_unverified' if device.get('kind') in ('panel','gateway') else None}
