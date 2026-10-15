chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
  if(msg.action==='MY_TAB_ID'){sendResponse({tabId:sender.tab?.id??null});}
});
