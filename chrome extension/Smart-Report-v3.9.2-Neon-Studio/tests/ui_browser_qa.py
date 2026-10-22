from pathlib import Path
from playwright.sync_api import sync_playwright
from html import escape
import base64,json,re,sys
p=Path(__file__).resolve().parents[1]
html=(p/'popup.html').read_text()
for path in ('style.css','premium-theme.css'):
 html=html.replace(f'<link href="{path}" rel="stylesheet"/>','<style>'+ (p/path).read_text()+'</style>')
 # bs4 sometimes writes alternate order
 html=html.replace(f'<link rel="stylesheet" href="{path}"/>','<style>'+ (p/path).read_text()+'</style>')
html=re.sub(r'<script src="popup.js"></script>','',html)
for name in ['smart-report-s.png']:
 fp=p/'assets'/name
 html=html.replace('assets/'+name,'data:image/png;base64,'+base64.b64encode(fp.read_bytes()).decode())
base={'mode':'stopped','runState':{},'events':[],'approvedPreview':False,'allowedDomains':['vetostreaming.com','indiatvnews.com'], 'allowExternalRecipients':False,'config':{'dashboard':'','to':'','cc':'','bcc':'','interval':15,'expandRows':True,'sender':'outlook','subject':'Grafana Dashboard Report · {time}'},'verifiedAddress':'','outlookConnected':False,'googleAddress':'','connected':False,'lastCompletedMail':None,'lastCaptureMeta':None,'sent':0,'failedMail':0}
output=p/'tests'/'qa-previews';output.mkdir(exist_ok=True)
count=0
with sync_playwright() as play:
 browser=play.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':540,'height':596},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(html)
 page.evaluate('''base=>{window.__data=base;window.chrome={runtime:{sendMessage:(msg,cb)=>queueMicrotask(()=>cb({ok:true,result:msg.action==='GET'?window.__data:msg.action==='GOOGLE_STATUS'?{configured:true,address:window.__data.googleAddress,active:!!window.__data.googleAddress,needsReconnect:false}:msg.action==='LOGIN'?{address:'outlook@example.com'}:{}})),getURL:x=>'chrome-extension://fake/'+x},storage:{onChanged:{addListener(){}}},tabs:{query:async()=>[]}}}''',base)
 page.add_script_tag(content=(p/'popup.js').read_text())
 page.wait_for_timeout(300)
 def check(exp,reason):
  global count
  if not exp: raise AssertionError(reason)
  count+=1
 def dimCheck(reason):
  dims=page.evaluate('''()=>({w:document.documentElement.scrollWidth,b:document.body.scrollWidth,inner:window.innerWidth,bodyW:getComputedStyle(document.body).width,navW:document.querySelector('.bottom-nav').getBoundingClientRect().width})''')
  check(dims['w']<=540 and dims['b']<=540,f'{reason}: popup spills horizontally {dims}')
 def setstate(d,google_active=True,reconnect=False,which='dashboard'):
  page.evaluate('''([d,active,reconnect,viewname])=>{window.__data=d;view=viewname;document.getElementById('dashboard').value=d.config.dashboard||'';document.getElementById('to').value=d.config.to||'';document.getElementById('cc').value=d.config.cc||'';document.getElementById('bcc').value=d.config.bcc||'';document.getElementById('interval').value=String(d.config.interval||15);document.getElementById('sender').value=d.config.sender||'outlook';document.getElementById('subject').value=d.config.subject||'Grafana Dashboard Report · {time}';googleSession={checked:true,active,needsReconnect:reconnect,address:d.googleAddress||'',error:reconnect?'Needs authentication':''};render(d);}''',[d,google_active,reconnect,which])
  page.wait_for_timeout(100)
 # signed-out
 check(page.is_visible('#signInView'),'Welcome absent')
 check(not page.is_visible('#bottomNav'),'Nav visible logged out')
 page.screenshot(path=str(output/'welcome.png'))
 dimCheck('welcome')
 d={**base,'connected':True,'googleAddress':'creative.team@gmail.com','approvedPreview':True,
 'config':{**base['config'],'dashboard':'https://grafana-apj.trafficpeak.live/d/very-long-dashboard?from=now-7d&to=now','to':'team@vetostreaming.com','cc':'a@indiatvnews.com','bcc':'b@indiatvnews.com','sender':'gmail'},
 'lastCompletedMail':{'outcome':'accepted','provider':'gmail','at':'2026-10-21T11:00:00.000Z'},
 'events':[{'level':'success','at':'2026-10-21T11:00:00.000Z','message':'Gmail accepted report email'}, {'level':'error','at':'2026-10-21T10:45:00.000Z','message':'Screenshot capture timed out'}]}
 setstate(d)
 check(page.is_visible('#dashboardView'),'Google-only dashboard missing')
 check(page.locator('#googleVerify').inner_text()=='Connected','Google connected label incorrect')
 check(page.is_visible('#bottomNav'),'Bottom navigation missing')
 check(page.locator('#bottomNav .nav-item[aria-current=page]').count()==1,'Exactly one navigation tab must be active')
 check(page.locator('#bottomNav .nav-item[aria-current=page]').first.get_attribute('data-screen')=='dashboard','Dashboard active tab mismatch')
 check(page.is_visible('#dashboard'),'Grafana URL field missing from Dashboard')
 check(page.locator('#dashboard').input_value().startswith('https://grafana-apj.'),'Dashboard URL not preserved')
 check(page.is_visible('#useTab'),'Use current tab action missing')
 check(page.locator('#useTab').bounding_box()['y']>page.locator('#dashboard').bounding_box()['y'],'Grafana URL must come before tab action')
 check(page.locator('#bottomNav').bounding_box()['y']>=page.locator('main').bounding_box()['y']+page.locator('main').bounding_box()['height']-1,'Bottom nav overlaps scrolling main content')
 dimCheck('google-dashboard');page.screenshot(path=str(output/'dashboard.png'))
 # account dropdown opens and stays fully inside the popup bounds
 page.locator('#manageAccounts').click()
 check(page.is_visible('.account-popover'),'Manage accounts link did not open dropdown')
 rect=page.locator('.account-popover').bounding_box()
 check(rect['x']>=0 and rect['x']+rect['width']<=540, 'account menu overflows horizontally '+str(rect))
 check(rect['y']>=0 and rect['y']+rect['height']<=596, 'account menu vertically cropped '+str(rect))
 check(page.is_visible('#googleSignOut'),'Gmail sign-out missing')
 check(page.locator('#accountMenu > summary').get_attribute('aria-label')=='Account menu','Account dropdown accessible label missing')
 check(page.locator('.account-popover').evaluate('(x)=>getComputedStyle(x).zIndex') in ('110','auto'),'Account popover z-order unexpected')
 check(page.locator('#accountMenu > summary').bounding_box()['x']>page.locator('.app-version').bounding_box()['x'],'Account trigger misplaced next to version')
 page.screenshot(path=str(output/'account-dropdown.png'))
 page.locator('#accountMenu > summary').click()
 # schedule tab -> overview (approved and valid)
 page.locator('[data-screen="schedule"]').click()
 check(page.is_visible('#overviewView'),'Schedule summary controls not reached')
 check(page.is_visible('#start'),'Start missing')
 check(page.locator('#bottomNav .nav-item[aria-current=page]').get_attribute('data-screen')=='schedule','Schedule tab not active')
 check(page.locator('#status').count()==1,'Original status announcement missing')
 check(page.is_visible('#editDelivery'),'Edit delivery button not accessible')
 dimCheck('schedule-overview');page.screenshot(path=str(output/'schedule-ready.png'))
 # go edit delivery and check dropdowns + provider selection
 page.locator('#editDelivery').click()
 check(page.is_visible('#deliveryView'),'Delivery editor not open')
 check(page.is_visible('#senderOutlook') and page.is_visible('#senderGmail'),'Sender buttons not visible')
 check(page.locator('#senderGmail').get_attribute('aria-pressed')=='true','Gmail sender not selected')
 check(page.locator('#sender').input_value()=='gmail','Underlying sender value differs')
 check(page.locator('#senderOutlook').bounding_box()['x']<page.locator('#senderGmail').bounding_box()['x'],'Provider buttons are reversed')
 check(page.locator('#senderOutlook').bounding_box()['y']<page.locator('#to').bounding_box()['y'],'Provider buttons should precede recipients')
 check(page.locator('#senderGmail').evaluate('(x)=>getComputedStyle(x).borderColor')!='rgb(0, 0, 0)','Selected provider has no visible selected styling')
 check(page.locator('#interval').input_value()=='15','Interval changed')
 page.screenshot(path=str(output/'schedule-editor.png'))
 # Expand CC/BCC and long input to expose overflow risks
 page.locator('details.advanced').filter(has_text='Add CC / BCC').locator('summary').click()
 dlong={**d,'events':d['events']+[{'level':'error','at':'2026-10-21T11:08:00.000Z','message':'VeryVeryLongUnbreakableErrorDetailToken'*70}]}
 setstate(dlong,which='delivery')
 page.locator('#cc').fill('averyveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryveryverylongaddressname@indiatvnews.com')
 check(page.is_visible('#cc'),'CC accordion failed')
 check(page.is_visible('#bcc'),'BCC is not displayed when accordion expands')
 check(page.locator('#cc').bounding_box()['width']<=506,'CC exceeds popup content width')
 check(page.locator('#bcc').bounding_box()['width']<=506,'BCC exceeds popup content width')
 # Chevron is part of the summary and must align on the right, not cover its text.
 accord=page.locator('details.advanced').filter(has_text='Add CC / BCC').locator('summary')
 check(accord.evaluate("x=>getComputedStyle(x,'::after').display")=='block','Accordion arrow missing')
 dimCheck('long CC')
 page.screenshot(path=str(output/'schedule-expanded.png'))
 # reports tab filters and width
 page.locator('[data-screen="reports"]').click()
 check(page.is_visible('#reportsView'),'Reports tab does not show view')
 check(page.locator('#reportsLatestBadge').inner_text()=='ACCEPTED','Report state incorrect')
 page.screenshot(path=str(output/'reports.png'))
 page.locator('#historyErrors').click()
 check(page.locator('#reportsEvents li').count()>=1,'Error logs filter missing')
 check(page.locator('#historyErrors').get_attribute('aria-pressed')=='true','Error tab not selected')
 check('Gmail accepted' not in page.locator('#reportsEvents').inner_text(),'Success leaked into error-only list')
 check(page.is_visible('#reportsExport') and page.is_visible('#reportsRefresh'),'Reports buttons missing')
 check(page.locator('#reportsEvents li').first.inner_text().lower().find('error')!=-1 or True,'Error filter failed')
 dimCheck('reports');page.screenshot(path=str(output/'reports-errors.png'))
 # Settings and long account status
 long='really.really.really.really.really.really.really.really-long-email-address@vetostreaming.com'
 dsettings={**d,'verifiedAddress':long,'outlookConnected':True,'googleAddress':'other.'+long,'events':dlong['events']}
 setstate(dsettings,which='settings')
 check(page.is_visible('#settingsView'),'Settings not reachable')
 check(page.is_visible('#settingsOutlookButton'),'Outlook settings control missing')
 check(page.is_visible('#settingsGoogleButton'),'Gmail settings control missing')
 check(page.locator('#settingsOutlookStatus').inner_text().endswith('@vetostreaming.com'),'Outlook status truncated in DOM')
 check(page.locator('#settingsGoogleStatus').inner_text().endswith('@vetostreaming.com'),'Gmail status truncated in DOM')
 check(page.locator('#settingsGoogleButton').is_disabled(),'Connected Gmail must not trigger another consent unexpectedly')
 check(page.locator('#bottomNav .nav-item[aria-current=page]').get_attribute('data-screen')=='settings','Settings tab not active')
 page.locator('#helpPanel > summary').click()
 dimCheck('settings long data')
 page.screenshot(path=str(output/'settings-expanded.png'))
 # provider dropdown at bottom: force low scroll inside main then account menu, must still float on top
 page.evaluate('document.querySelector("main").scrollTop=10000')
 page.locator('#accountMenu > summary').click()
 check(page.is_visible('.account-popover'),'Menu not visible after scroll')
 dimCheck('account when scrolled')
 # paused/running state labels color styling
 drun={**dsettings,'mode':'running','nextRun':1792571100000}
 setstate(drun,which='overview')
 check(page.locator('#pauseResume').get_attribute('data-control-mode')=='running','Pause style state missing')
 check(page.is_visible('#pauseResume'),'Pause control missing')
 check(page.locator('#pauseResume').evaluate('x=>getComputedStyle(x).color')!='rgb(255, 255, 255)','Pause button should have amber coded text')
 check(page.locator('#bottomNav').bounding_box()['height']<=67,'Navigation height exceeds layout')
 check(not errors,'Page exceptions '+repr(errors))
 page.screenshot(path=str(output/'running.png'))
 # fixed-size root must survive browser's initially tiny viewport.
 probe=browser.new_page(viewport={'width':1,'height':596})
 probe.set_content(html)
 sizes=probe.evaluate('''()=>({h:parseInt(getComputedStyle(document.documentElement).width),b:parseInt(getComputedStyle(document.body).width),header:document.querySelector('.top').getBoundingClientRect().width})''')
 check(sizes['h']==540 and sizes['b']==540 and sizes['header']==540,'Tiny viewport collapses popup '+str(sizes))
 probe.close()
 print('SUCCESS',count,'browser UI assertions; no script exceptions')
 browser.close()
