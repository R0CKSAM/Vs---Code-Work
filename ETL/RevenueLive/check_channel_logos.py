"""Visual asset audit against the locally served app; no account or DB writes."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={'width':1000,'height':700})
    page.goto('http://127.0.0.1:8820')
    count = page.evaluate('''async()=>{
      const manifest=await fetch('/static/channel-logos/manifest.json').then(r=>r.json());
      document.body.replaceChildren();document.body.style.cssText='background:#eef3f8;padding:24px;display:grid;grid-template-columns:repeat(4,1fr);gap:16px;font:14px Arial';
      const files=new Set();
      for(const [name,item] of Object.entries(manifest)){
        if(files.has(item.file))continue;files.add(item.file);
        const card=document.createElement('div');card.style.cssText='background:white;padding:16px;height:150px;display:flex;flex-direction:column;gap:12px;align-items:center';
        const image=document.createElement('img');image.src='/static/channel-logos/'+item.file;image.style.cssText='width:180px;height:95px;object-fit:contain';image.style.backgroundColor=item.background||'#fff';
        const label=document.createElement('span');label.textContent=name;card.append(image,label);document.body.append(card);
      }
      await Promise.all([...document.images].map(image=>image.decode()));return files.size;
    }''')
    assert count >= 12
    assert page.locator('img').evaluate_all('images=>images.every(i=>i.naturalWidth>0 && i.naturalHeight>0)')
    (ROOT / '.screenshots').mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT / '.screenshots/channel-logos.png'),full_page=True)
    print(f'PASS: {count} local logos decoded; contact sheet captured.')
    browser.close()
