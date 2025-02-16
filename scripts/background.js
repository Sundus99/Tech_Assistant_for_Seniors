chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: injectSidebar,
  });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "newTab") {
    chrome.tabs.create({ url: "https://*/*" });
  }
});

function injectSidebar() {
  const htmlURL = chrome.runtime.getURL('sidebar/sidebar.html');
  const cssURL = chrome.runtime.getURL('sidebar/sidebar.css');

  Promise.all([
    fetch(htmlURL).then((res) => res.text()),
    fetch(cssURL).then((res) => res.text()),
  ])
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
