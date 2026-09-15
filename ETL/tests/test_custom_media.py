import io
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from test_scoreboard_app import scoreboard, scoreboard_web


def test_text_box_normalization_and_image_pixels(tmp_path):
    boxes = [{'text':'First','x':5,'y':5,'width':30,'height':20,'opacity':100,
              'background':[255,0,0],'color':[255,255,255]},
             {'text':'Second','x':55,'y':5,'width':30,'height':20,'opacity':100,
              'background':[0,0,255],'color':[255,255,0]}]
    config = scoreboard.normalise_project_configs({'t8':{'text_boxes':boxes}})['t8']
    assert config['text_boxes'][0]['background'] == [255,0,0]
    image = scoreboard.render_t8(config)
    assert image.getpixel((100,60)) == (255,0,0)
    assert image.getpixel((1060,60)) == (0,0,255)
    overlay = scoreboard.render_custom_text_overlay(config,(1920,1080))
    assert overlay.getpixel((0,0))[3] == 0
    assert any(color[:3]==(255,255,0) for _,color in overlay.crop((1056,54,1632,270)).getcolors(200000))
    huge = {'text':'Many words '*1000,'width':2,'height':2,'x':float('nan'),'y':-100,'font_size':9999}
    clean = scoreboard.normalise_custom_text_boxes([huge]*25)
    assert len(clean) == 20 and len(clean[0]['text']) == 2000
    assert clean[0]['font_size'] == 180 and clean[0]['y'] == 0
    assert scoreboard.normalise_custom_text_boxes(None) == []
    assert scoreboard.render_custom_text_overlay({'text_boxes':[huge]},(1920,1080)).size == (1920,1080)


def test_upload_validation_and_named_presets(tmp_path):
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    data = io.BytesIO()
    scoreboard.Image.new('RGB',(80,160),'red').save(data,'PNG')
    raw = data.getvalue()
    cfg = runtime.upload_media(io.BytesIO(raw),len(raw),'portrait.png')
    cfg['text_boxes'] = [{'text':'Saved title','x':5,'y':5,'width':40,'height':15}]
    image, cfg = runtime.render('t8',cfg,update_live=False)
    assert image.size == (1920,1080)
    assert image.getpixel((0,0)) == (0,0,0)
    assert image.getpixel((960,540)) == (255,0,0)
    payload = dict(template='t8',player='Opening graphic',config=cfg)
    saved = runtime.save_template(payload,'192.168.50.15')
    assert saved['saved']
    assert saved['item']['country'] == ''
    assert not runtime.save_template(payload,'192.168.50.15')['saved']
    assert runtime.list_templates()[0]['config']['media_path'] == cfg['media_path']
    assert runtime.list_templates()[0]['config']['text_boxes'][0]['text'] == 'Saved title'
    before = set(runtime.upload_dir.iterdir())
    for name,length,content in [('bad.exe',1,b'x'),('bad.png',10,b'x'),('huge.mp4',513*1024*1024,b'')]:
        with pytest.raises(ValueError):
            runtime.upload_media(io.BytesIO(content),length,name)
    assert set(runtime.upload_dir.iterdir()) == before


def test_video_playback_and_browser(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    ffmpeg = scoreboard.locate_ffmpeg()
    assert ffmpeg, 'FFmpeg required for video verification'
    clip = tmp_path/'motion.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10',
        '-t','1','-pix_fmt','yuv420p',str(clip)],check=True,timeout=30)
    runtime = scoreboard_web.ScoreboardWebRuntime(scoreboard,tmp_path/'uploads')
    with clip.open('rb') as source:
        cfg = runtime.upload_media(source,clip.stat().st_size,clip.name)
    assert cfg['media_kind'] == 'video'
    cfg['text_boxes'] = [{'text':'LIVE','x':0,'y':0,'width':20,'height':20,
                         'opacity':100,'background':[255,0,255]}]
    frames = []
    class Output:
        def __init__(self,*args): pass
        def start(self,image): self.update(image)
        def update(self,image): self.image=image.copy(); frames.append(image.tobytes())
        def snapshot_frame(self): return self.image.copy()
        def poll_error(self): return None
        def stop(self): pass
    monkeypatch.setitem(scoreboard.VIDEO_EXPORT_PRESETS,'Test',dict(width=160,height=90,fps=10))
    playback = runtime.media.VideoPlayback(scoreboard,Output(),cfg['media_path'],'Test',False,config=cfg)
    try:
        playback.start()
        playback.thread.join(timeout=10)
        assert playback.finished and not playback.error
        assert len(set(frames)) >= 5
        assert all(frame[:3] == bytes([255,0,255]) for frame in frames)
    finally:
        playback.stop()
    assert playback.process.poll() is not None
    monkeypatch.setattr(scoreboard,'DeckLinkLiveOutput',Output)
    runtime.register_session('media-test','Media test','127.0.0.1')
    runtime.start_live('t8',cfg,'Test',next(iter(scoreboard.DECKLINK_OUTPUTS)),
        'media-test','127.0.0.1',standby=True)
    runtime.show_live('t8',cfg,'media-test','127.0.0.1')
    active = runtime.media_playback
    try:
        time.sleep(2)
        assert not active.finished and not active.error
        previews=set()
        source_frames=set()
        for _ in range(20):
            previews.add(runtime.program_preview()[0])
            source_frames.add(runtime.live_output.snapshot_frame().tobytes())
            time.sleep(.17)
        assert len(previews)>1, (
            f'finished={active.finished} error={active.error} frames={len(frames)} '
            f'unique_recent={len(set(frames[-30:]))} same_output={active.output is runtime.live_output} '
            f'size={runtime.live_output.image.size} unique_sources={len(source_frames)}')
        runtime.clear_live('media-test','127.0.0.1')
        assert active.process.poll() is not None
        assert runtime.media_playback is None
        assert runtime.live_output.image.getbbox() is None
        assert runtime.live_status()['active']
        runtime.show_live('t1',scoreboard.DEF_T1,'media-test','127.0.0.1')
        assert active.process.poll() is not None
        assert runtime.media_playback is None
    finally:
        runtime.stop_live(force=True)
    monkeypatch.setitem(scoreboard.MP4_EXPORT_PRESETS,'Test',dict(width=160,height=90,fps=10,level='3.1'))
    exported=tmp_path/'exported.mp4'
    exported.write_bytes(runtime.export_mp4('t8',cfg,'Test',1))
    result=subprocess.run([ffmpeg,'-v','error','-i',str(exported),'-an','-f','rawvideo',
        '-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True,timeout=30)
    frame_size=160*90*3
    assert len({result.stdout[i:i+frame_size] for i in range(0,len(result.stdout),frame_size)})>=5
    assert result.stdout[0] > 220 and result.stdout[1] < 30 and result.stdout[2] > 220
    server = ThreadingHTTPServer(('127.0.0.1',0),scoreboard_web.make_handler(runtime))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':1600,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/scoreboard')
            page.click('#templateLabel')
            page.fill('#templateSearch','Custom Upload')
            page.locator('#templateOptions button').click()
            page.locator('#customMedia').set_input_files(str(clip))
            expect(page.locator('.file-name')).to_have_text('motion',timeout=30000)
            page.wait_for_function('document.getElementById("mediaPreview").currentTime > 0.1')
            page.click('#addTextBox')
            page.locator('[data-box-field=text]').fill('First overlay')
            page.locator('[data-box-field=background]').fill('#ff0000')
            page.click('#addTextBox')
            page.locator('[data-box-field=text]').fill('Second overlay')
            page.locator('[data-box-field=background]').fill('#0000ff')
            page.locator('[data-box-field=x]').fill('55')
            page.locator('[data-box-field=width]').fill('30')
            page.select_option('#textBoxChoice','0')
            hit=page.locator('.custom-box-hit.selected')
            before=hit.bounding_box()
            page.mouse.move(before['x']+40,before['y']+20)
            page.mouse.down()
            page.mouse.move(before['x']+70,before['y']-10,steps=5)
            page.mouse.up()
            after=hit.bounding_box()
            assert after['x'] > before['x']+20 and after['y'] < before['y']-20
            handle=page.locator('.custom-box-hit.selected [data-corner=se]').bounding_box()
            page.mouse.move(handle['x']+6,handle['y']+6)
            page.mouse.down()
            page.mouse.move(handle['x']+36,handle['y']+26,steps=5)
            page.mouse.up()
            assert hit.bounding_box()['width'] > after['width']+20
            page.wait_for_function('document.querySelector("#customBoxCanvas>img").naturalWidth === 1920')
            page.click('#savePreset')
            expect(page.locator('#presetCountryName')).not_to_be_visible()
            page.fill('#presetPlayerName','Opening video')
            page.click('#confirmPreset')
            expect(page.locator('#presetDialog')).not_to_be_visible()
            expect(page.locator('#presetPlayer')).to_contain_text('Opening video')
            saved = runtime.list_templates()[0]
            assert len(saved['config']['text_boxes']) == 2
            assert saved['config']['text_boxes'][0]['background'] == [255,0,0]
            assert saved['config']['text_boxes'][1]['background'] == [0,0,255]
            page.click('#newPlayer')
            page.select_option('#presetPlayer',saved['id'])
            expect(page.locator('#textBoxChoice option')).to_have_count(2)
            page.wait_for_timeout(1500)
            page.wait_for_function('''() => {
                const image=document.querySelector('#customBoxCanvas>img');
                if(!image.complete || !image.naturalWidth) return false;
                const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=1080;
                const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
                return ctx.getImageData(0,0,1920,1080).data.some((v,i)=>i%4===3&&v>0);
            }''')
            for width,height in [(1600,1000),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                page.screenshot(path=str(tmp_path/f'custom-{width}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
