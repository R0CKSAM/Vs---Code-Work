from pathlib import Path
from playwright.sync_api import sync_playwright
import re,sys
p=Path(sys.argv[1]);html=(p/'popup.html').read_text();css=(p/'style.css').read_text();js=(p/'popup.js').read_text()
html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+css+'</style>').replace('<script src="popup.js"></script>','')
base={'mode':'stopped','runState':{},'events':[],'approvedPreview':False,'allowedDomains':['vetostreaming.com','indiatvnews.com'],'config':{'dashboard':'','to':'','cc':'','bcc':'','interval':15,'expandRows':True,'sender':'outlook'},'verifiedAddress':'','outlookConnected':False,'googleAddress':'','connected':False,'lastCompletedMail':None,'lastCaptureMeta':None,'sent':0,'failedMail':0}
count=0
with sync_playwright() as play:
 browser=play.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 for width in [555,400]:
  page=browser.new_page(viewport={'width':width,'height':900})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content(html)
  page.evaluate('''base=>{window.__data=base;window.chrome={runtime:{sendMessage:(msg,cb)=>queueMicrotask(()=>cb({ok:true,result:msg.action==='GET'?window.__data:msg.action==='GOOGLE_STATUS'?{configured:true,address:window.__data.googleAddress,active:!!window.__data.googleAddress,needsReconnect:false}:msg.action==='LOGIN'?{address:'outlook@example.com'}:{}})),getURL:x=>'chrome-extension://fake/'+x},storage:{onChanged:{addListener(){}}},tabs:{query:async()=>[]}}}''',base)
  page.add_script_tag(content=js)
  page.wait_for_timeout(120)
  def check(exp,msg):
   global count
   if not exp:raise AssertionError(f'{width}px: {msg}')
   count+=1
  check(page.is_visible('#signInView'),'Signed out welcome missing')
  check(not page.is_visible('#appView'),'Signed out app visible')
  check(page.is_visible('#googleSignIn'),'Google login missing')
  check(page.is_visible('#signIn'),'Microsoft login missing')
  data={**base,'connected':True,'googleAddress':'google.user@gmail.com','approvedPreview':True,'config':{**base['config'],'dashboard':'https://grafana-apj.trafficpeak.live/d/demo/dash?from=now-7d&to=now','to':'team@vetostreaming.com','cc':'alice@indiatvnews.com','bcc':'bob@indiatvnews.com','sender':'gmail'}}
  def setstate(d,google_active=True,reconnect=False):
   page.evaluate('''([d,active,reconnect])=>{window.__data=d;document.getElementById('dashboard').value=d.config.dashboard||'';document.getElementById('to').value=d.config.to||'';document.getElementById('cc').value=d.config.cc||'';document.getElementById('bcc').value=d.config.bcc||'';document.getElementById('interval').value=String(d.config.interval||15);document.getElementById('sender').value=d.config.sender||'outlook';document.getElementById('subject').value=d.config.subject||'Grafana Dashboard Report · {time}';googleSession={checked:true,active,needsReconnect:reconnect,address:d.googleAddress||'',error:reconnect?'Needs authentication':''};view='';render(d);}''',[d,google_active,reconnect])
  setstate(data)
  check(page.locator('#sender').count()==1,'Missing sender selector')
  check(page.is_visible('#appView'),'Google-only app did not open')
  check(page.is_visible('#overviewView'),'Google-only overview missing')
  check(page.is_visible('#providerBar'),'Provider strip missing')
  check(page.is_visible('#connectOutlook'),'Microsoft connect inaccessible to Gmail user')
  check(page.is_visible('#accountMenu'),'Gmail account menu missing')
  check(page.is_visible('#googleTools'),'Gmail panel missing')
  check(page.locator('#googleVerify').inner_text()=='Connected','Authorized Google account incorrectly shows reconnect')
  check(page.is_enabled('#googleTest'),'Gmail one-shot test disabled when ready')
  check(not page.is_visible('#outlookTestRow'),'Gmail user incorrectly sees Outlook test')
  check(page.is_visible('#start') and not page.is_enabled('#start'),'Untested Gmail schedule must be disabled')
  check(page.is_visible('#frequencyRow'),'Gmail schedule missing frequency')
  check(page.is_visible('#lastOutlookRow'),'Gmail user cannot see last delivery result')
  page.locator('#accountMenu > summary').click()
  check(page.is_visible('#googleSignOut'),'Google disconnect inaccessible')
  check(not page.is_visible('#verify'),'Outlook verify shown without Outlook')
  setstate(data,google_active=False,reconnect=True)
  check(page.is_visible('#providerNotice'),'Stale Google auth not explained')
  check(page.locator('#googleVerify').inner_text()=='Reconnect','Expired Google authentication should show reconnect')
  check(not page.is_enabled('#googleTest'),'Stale Google auth permitted sending')
  data_o={**data,'outlookConnected':True,'verifiedAddress':'user@vetostreaming.com','googleAddress':'','config':{**data['config'],'sender':'outlook'}}
  setstate(data_o)
  check(page.is_visible('#outlookTestRow'),'Outlook test missing')
  check(page.is_enabled('#test'),'Valid Outlook test disabled')
  check(page.is_visible('#start') and page.is_enabled('#start'),'Outlook schedule missing')
  check(not page.is_visible('#googleTools'),'Gmail test shown without Google')
  data_b={**data_o,'googleAddress':'google.user@gmail.com'}
  setstate(data_b)
  check(page.is_visible('#outlookTestRow') and page.is_visible('#googleTools'),'Both tests not accessible')
  check(page.is_enabled('#googleTest'),'Google send disabled when both authorized')
  running={**data_b,'mode':'running','nextRun':1760980000000}
  setstate(running)
  check(not page.is_enabled('#googleTest'),'Gmail test while Outlook scheduling should be blocked')
  check(page.is_visible('#pauseResume'),'Pause button missing for running schedule')
  pending={**data_b,'gmailSubmissionPending':True}
  setstate(pending)
  check(page.is_visible('#gmailRecovery'),'Pending Gmail send lacks recovery')
  check(not page.is_enabled('#googleTest'),'Pending Gmail send was enabled')
  long='really.very.long.address.with.multiple.sections.and.no.break@vetostreaming.com'
  longData={**data_b,'verifiedAddress':long,'googleAddress':long,'lastMailOutcome':'', 'events':[{'level':'error','at':'2026-10-19T07:00:00.000Z','message':'Fatal '+('LongUnbreakableToken'*70)}]}
  setstate(longData)
  page.locator('#helpPanel > summary').click()
  dim=page.evaluate('''()=>({htmlWidth:document.documentElement.scrollWidth,viewport:window.innerWidth,bodyWidth:document.body.scrollWidth})''')
  check(dim['htmlWidth']<=max(540,width)+1 and dim['bodyWidth']<=540+1,'Elements stretch beyond the fixed 540px Chrome popup')
  check(not errors,'Page exception(s): '+repr(errors))
  print(f'{width}px host: {count} assertions cumulative, zero console errors, popup internal width <=540px')
  page.close()
 # Simulate Chrome opening a popup with a one-pixel initial width. Do not
 # click controls at this artificially constrained viewport: test intrinsic size only.
 probe=browser.new_page(viewport={'width':1,'height':800})
 probe.set_content(html)
 dims=probe.evaluate("""()=>({html:parseFloat(getComputedStyle(document.documentElement).width),body:parseFloat(getComputedStyle(document.body).width),child:document.querySelector('header').getBoundingClientRect().width})""")
 assert dims['html']>=539 and dims['body']>=539 and dims['child']>=539, f'Popup collapsed at 1px: {dims}'
 count+=1
 print('1px initial viewport: fixed 540px popup intrinsic width verified')
 probe.close()
 browser.close()
print('SUCCESS - all UI assertions passed:',count)
