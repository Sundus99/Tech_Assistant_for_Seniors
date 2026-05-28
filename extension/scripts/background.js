/* GrandAssist — background service worker (Manifest V3) */

chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: injectSidebar,
  });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  switch (request.action) {
    case "newTab":
      chrome.tabs.create({ url: "chrome://newtab" });
      break;
    case "closeTab":
      if (sender.tab?.id) chrome.tabs.remove(sender.tab.id);
      break;
    case "nextTab":
      chrome.tabs.query({ currentWindow: true }, (tabs) => {
        const idx = tabs.findIndex((t) => t.active);
        const next = tabs[(idx + 1) % tabs.length];
        if (next) chrome.tabs.update(next.id, { active: true });
      });
      break;
  }
  sendResponse({ ok: true });
  return true;
});

async function injectSidebar() {
  const existing = document.getElementById("chatbotSidebar");
  if (existing) {
    existing.style.display = existing.style.display === "none" ? "" : "none";
    return;
  }

  const htmlURL = chrome.runtime.getURL("sidebar/sidebar.html");
  const cssURL  = chrome.runtime.getURL("sidebar/sidebar.css");

  try {
    const [html, css] = await Promise.all([
      fetch(htmlURL).then((r) => r.text()),
      fetch(cssURL).then((r) => r.text()),
    ]);

    // Inject Google Fonts (Newsreader display + Nunito body)
    if (!document.getElementById("grandassist-fonts")) {
      const link = document.createElement("link");
      link.id = "grandassist-fonts";
      link.rel = "stylesheet";
      link.href = "https://fonts.googleapis.com/css2?" +
        "family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,600&" +
        "family=Nunito:wght@400;600;700&display=swap";
      document.head.appendChild(link);
    }

    const style = document.createElement("style");
    style.id = "grandassist-style";
    style.textContent = css;
    document.head.appendChild(style);

    const host = document.createElement("div");
    host.innerHTML = html;
    document.body.appendChild(host.firstElementChild);
  } catch (err) {
    console.error("GrandAssist: failed to inject sidebar", err);
  }
}
