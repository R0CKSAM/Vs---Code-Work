"""Read DeckLink COM capabilities without setting profiles or enabling I/O."""
import ctypes as C
import faulthandler
import json
from pathlib import Path
import uuid

P = C.c_void_p
U32 = C.c_uint32
I32 = C.c_int32
I64 = C.c_int64
GUID = C.c_ubyte * 16
ole = C.OleDLL('ole32')
automation = C.OleDLL('oleaut32')
automation.SysFreeString.argtypes = [P]
automation.SysFreeString.restype = None
ole.CoUninitialize.restype = None
ole.CoCreateInstance.argtypes = [C.POINTER(GUID), P, U32, C.POINTER(GUID), C.POINTER(P)]
ole.CoCreateInstance.restype = I32
ole.CoInitializeEx.argtypes = [P, U32]
ole.CoInitializeEx.restype = I32

IIDS = {
    'iterator': '50FB36CD-3063-4B73-BDBB-958087F2D8BA',
    'attributes': '17D4BF8E-4911-473A-80A0-731CF6FF345B',
    'legacy_attributes': 'ABC11843-D966-44CB-96E2-A1CB5D3135C4',
    'config': '912F634B-2D4E-40A4-8AAB-8D80B73F1289',
    'legacy_config': 'EF90380B-4AE5-4346-9077-E288E149F129',
    'status': '5F558200-4028-49BC-BEAC-DB3FA4A96E46',
    'output': 'BE2D9020-461E-442F-84B7-E949CB953B9D',
    'profiles': '30D41429-3998-4B6D-84F8-78C94A797C6E',
    'keyer': '89AFCAF5-65F8-421E-98F7-96FE5F5BFBA3',
    'api': '7BEA3C68-730D-4322-AF34-8A7152B532A4',
}
owned = []


def guid(text):
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


def call(obj, index, types, *args):
    table = C.cast(obj, C.POINTER(C.POINTER(P))).contents
    return C.WINFUNCTYPE(I32, P, *types)(table[index])(obj, *args)


def hresult(value):
    return f'0x{value & 0xffffffff:08X}'


def create(clsid, interface):
    result = P()
    hr = ole.CoCreateInstance(C.byref(guid(clsid)), None, 1,
                              C.byref(guid(IIDS[interface])), C.byref(result))
    if hr != 0:
        raise RuntimeError(f'CoCreateInstance {interface}: {hresult(hr)}')
    owned.append(result)
    return result


def query(obj, name):
    result = P()
    hr = call(obj, 0, [C.POINTER(GUID), C.POINTER(P)], C.byref(guid(IIDS[name])), C.byref(result))
    if hr != 0:
        return None
    owned.append(result)
    return result


def fourcc(text):
    return int.from_bytes(text.encode('ascii'), 'big')


def read(obj, index, key=None, kind=I64):
    if not obj:
        return {'error': 'Interface unavailable'}
    result = kind()
    types = [C.POINTER(kind)]
    args = [C.byref(result)]
    if key is not None:
        types.insert(0, U32)
        args.insert(0, fourcc(key))
    hr = call(obj, index, types, *args)
    if hr != 0:
        return {'error': hresult(hr)}
    if kind is P:
        try:
            return C.wstring_at(result.value) if result.value else ''
        finally:
            if result.value:
                automation.SysFreeString(result)
    return bool(result.value) if kind is I32 else result.value


def named(value):
    if not isinstance(value, int):
        return value
    names = {'dxha': 'half-duplex', 'dxfu': 'full-duplex', 'dxin': 'inactive',
             'dxsp': 'simplex', 'hdup': 'half-duplex (legacy)', 'fdup': 'full-duplex (legacy)',
             '1dfd': 'one-subdevice full-duplex', '1dhd': 'one-subdevice half-duplex',
             '2dfd': 'two-subdevices full-duplex', '2dhd': 'two-subdevices half-duplex',
             '4dhd': 'four-subdevices half-duplex', 'Hi50': '1080i50',
             'BGRA': '8-bit BGRA', '2vuy': '8-bit YUV', 'none': 'none'}
    for key, label in names.items():
        if value == fourcc(key):
            return label
    return value


def attributes(obj):
    attrs = query(obj, 'attributes')
    result = {name: read(attrs, 3, key, I32) for name, key in (
        ('external_keying', 'keye'), ('internal_keying', 'keyi'))}
    result.update({name: named(read(attrs, 4, key)) for name, key in (
        ('profile', 'prid'), ('duplex', 'dupx'), ('subdevice_index', 'subi'),
        ('subdevice_count', 'nsbd'), ('persistent_id', 'peid'), ('device_group_id', 'dgid'))})
    return result


def next_object(iterator):
    result = P()
    hr = call(iterator, 3, [C.POINTER(P)], C.byref(result))
    if hr != 0:
        return None
    owned.append(result)
    return result


def video_support(output, pixel_format, flags):
    if not output:
        return {'error': 'Output interface unavailable'}
    actual, supported = U32(), I32()
    hr = call(output, 3, [U32, U32, U32, U32, U32, C.POINTER(U32), C.POINTER(I32)],
              1, fourcc('Hi50'), fourcc(pixel_format), fourcc('none'), flags,
              C.byref(actual), C.byref(supported))
    return {'hresult': hresult(hr), 'supported': bool(supported.value), 'actual_mode': named(actual.value)}


def main():
    hr = ole.CoInitializeEx(None, 0)
    if hr not in (0, 1):
        raise RuntimeError(f'COM initialization: {hresult(hr)}')
    try:
        iterator = create('BA6C6F44-6DA5-4DCE-94AA-EE2D1372A676', 'iterator')
        api = create('263CA19F-ED09-482E-9F9D-84005783A237', 'api')
        report = {'api_version': read(api, 6, 'vers', P), 'devices': []}
        for index in range(16):
            device = next_object(iterator)
            if not device:
                break
            record = {'enumeration_index': index, 'model': read(device, 3, kind=P),
                      'display_name': read(device, 4, kind=P), 'attributes': attributes(device)}
            print(f"Reading device {index}: {record['display_name']}", flush=True)
            config, legacy = query(device, 'config'), query(device, 'legacy_attributes')
            legacy_config = query(device, 'legacy_config')
            record['configuration'] = {
                'video_output_connection': read(config, 6, 'vocn'),
                'legacy_duplex': named(read(legacy_config, 6, 'dupx')),
                'paired_persistent_id': read(legacy, 4, 'ppid'),
                'supports_full_duplex': read(legacy, 3, 'fdup', I32),
            }
            status = query(device, 'status')
            record['status'] = {name: named(read(status, 4, key)) for name, key in (
                ('busy_flags', 'busy'), ('current_output_mode', 'cvom'),
                ('last_output_pixel_format', 'opix'), ('pcie_link_width', 'pwid'),
                ('pcie_link_speed', 'plnk'), ('reference_mode', 'refm'))}
            record['status']['reference_locked'] = read(status, 3, 'refl', I32)
            record['status']['input_signal_locked'] = read(status, 3, 'visl', I32)
            output = query(device, 'output')
            record['keyer_interface_available'] = bool(query(device, 'keyer'))
            record['mode_1080i50'] = {
                'normal_yuv': video_support(output, '2vuy', 0),
                'normal_bgra': video_support(output, 'BGRA', 0),
                'keying_bgra_current_profile': video_support(output, 'BGRA', 1),
            }
            manager = query(device, 'profiles')
            profiles = []
            if manager:
                profile_iterator = P()
                hr = call(manager, 3, [C.POINTER(P)], C.byref(profile_iterator))
                if hr == 0:
                    owned.append(profile_iterator)
                    for _ in range(16):
                        profile = next_object(profile_iterator)
                        if not profile:
                            break
                        details = attributes(profile)
                        details['active'] = read(profile, 4, kind=I32)
                        profiles.append(details)
            record['available_profiles'] = profiles
            report['devices'].append(record)
        text = json.dumps(report, indent=2)
        print(text, flush=True)
        Path(__file__).with_name('hardware-report.json').write_text(text, encoding='utf-8')
    finally:
        for obj in reversed(owned):
            call(obj, 2, [])
        ole.CoUninitialize()


if __name__ == '__main__':
    faulthandler.dump_traceback_later(30, exit=True)
    main()
