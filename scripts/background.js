/*
 * Background service worker Manifest V3 
 *
 */

// imports 
// need chrome and device driver to run selenium 

chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: injectSidebar,
  });
});

// forgot to add sender and the response header here 
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    switch (request.action) {
    case "newTab":
      chrome.tabs.create({ url: "chrome://newtab"})
      break
    case "closeTab":
      if (sender.tab?.id) chrome.tabs.remove(sender.tab.id);
      break
    case "nextTab":
      chrome.tabs.query({ currentWindow: true }, (tabs) => {
        const idx = tabs.findIndex((t) => t.active)
        const next = tabs[(idx + 1) % tabs.length]
        if (next) chrome.tabs.update(next.id, { active: true })
      })
      break
  }
})

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "newTab") {
    chrome.tabs.create({ url: "about:blank" });
  }
});

async function injectSidebar() {
  const existing = document.getElementById("chatbotSidebar")
  if (existing) {
    existing.style.display = existing.style.display === "none" ? "" : "none"
    return
  }
  const htmlURL = chrome.runtime.getURL('sidebar/sidebar.html');
  const cssURL = chrome.runtime.getURL('sidebar/sidebar.css');

  try { 
    const [html, css] = await Promise.all([
      fetch(htmlURL).then((res) => res.text()),
      fetch(cssURL).then((res) => res.text()),
    ])

    // injection of google fonts 
    .then(([html, css]) => {
      const sidebarElement = document.createElement('div');
      sidebarElement.innerHTML = html;
      document.body.appendChild(sidebarElement);

      const style = document.createElement('style');
      style.textContent = css;
      document.head.appendChild(style);
    })
    .catch((err) =>
      console.error('Error loading sidebar resources:', err)
    );
}
