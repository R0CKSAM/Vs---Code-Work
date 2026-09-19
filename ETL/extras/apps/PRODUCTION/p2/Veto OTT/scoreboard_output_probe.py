"""Read-only DeckLink discovery. Never open a playback pipeline during probing."""
import json


def discover(core):
    gst=core.load_gstreamer()
    monitor=gst.DeviceMonitor.new()
    monitor.add_filter('Video/Sink',None)
    devices=[]
    try:
        if not monitor.start():
            raise RuntimeError('Video output discovery could not start.')
        for device in monitor.get_devices():
            props=device.get_properties()
            if props is None or not props.has_field('device-number') or not props.has_field('model-name'):
                continue
            if 'decklink' not in str(props.get_value('model-name')).lower():
                continue
            number=int(props.get_value('device-number'))
            caps=device.get_caps()
            modes=[]
            for name,preset in core.VIDEO_EXPORT_PRESETS.items():
                scan='interleaved' if preset.get('interlaced') else 'progressive'
                candidate=gst.Caps.from_string(
                    f"video/x-raw,width={preset['width']},height={preset['height']},"
                    f"framerate={core.preset_rate(preset)},interlace-mode={scan}")
                if caps is not None and caps.can_intersect(candidate):
                    modes.append(name)
            devices.append(dict(name=f'DeckLink output {number+1} (device {number})',
                                number=number,model=str(props.get_value('model-name')),modes=modes))
        return dict(devices=devices,switcher_detected=False,
                    note='SDI receiver format is not discoverable here. Match the switcher setting exactly.')
    finally:
        monitor.stop()


if __name__=='__main__':
    import scoreboard_app
    try:
        print(json.dumps(discover(scoreboard_app)))
    except Exception as error:
        print(json.dumps(dict(devices=[],error=str(error),switcher_detected=False)))
