/* =========================================================================
   GrandAssist — content script
   ---------------------------------------------------------------------------
   Runs in every tab and injected alongside sidebar.html + sidebar.css.
   Responsibilities:
     * Manage voice-recognition lifecycle (idle / listening / thinking / error)
     * Handle UI controls (mic, close, minimize, font size, drawers)
     * Route voice commands:
         - local DOM actions (scroll, tab nav)    -> handled here
         - backend intents                         -> POST /chat on server
     * Render AI replies and Pinterest pin grids
     * Persist minimized + font-scale preferences via chrome.storage
   ========================================================================= */

(function () {
  "use strict";

  const BACKENDS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://tech-assistant-for-seniors-eb4876783faf.herokuapp.com",
  ];
  const KNOWN_SITES = [
    { aliases: ["youtube", "you tube"], name: "YouTube", url: "https://www.youtube.com/" },
    { aliases: ["gmail"], name: "Gmail", url: "https://www.gmail.com/" },
    { aliases: ["google"], name: "Google", url: "https://www.google.ca/" },
    { aliases: ["facebook"], name: "Facebook", url: "https://www.facebook.com/" },
    { aliases: ["hotmail", "outlook"], name: "Hotmail", url: "https://outlook.live.com/" },
    { aliases: ["yahoo"], name: "Yahoo", url: "https://www.yahoo.com/" },
    { aliases: ["bing"], name: "Bing", url: "https://www.bing.com/" },
    { aliases: ["duckduckgo", "duck duck go", "duck duckgo"], name: "DuckDuckGo", url: "https://duckduckgo.com/" },
    { aliases: ["amazon"], name: "Amazon", url: "https://www.amazon.ca/" },
    { aliases: ["ebay"], name: "eBay", url: "https://www.ebay.ca/" },
    { aliases: ["wikipedia"], name: "Wikipedia", url: "https://www.wikipedia.org/" },
    { aliases: ["pinterest"], name: "Pinterest", url: "https://www.pinterest.com/" },
  ];
  const OPEN_VERBS = ["open", "launch", "go to", "take me to"];

  // --- state --------------------------------------------------------------
  const state = {
    recognition: null,
    listening: false,
    sessionId: null,
    sidebar: null,
    chat: null,
    welcomeShown: true,
  };

  // --- init ---------------------------------------------------------------
  function init() {
    state.sidebar = document.getElementById("chatbotSidebar");
    state.chat = document.getElementById("gaChat");
    if (!state.sidebar) return;

    wireControls();
    restorePreferences();
    state.sidebar.setAttribute("data-state", "idle");
  }

  // --- preference persistence --------------------------------------------
  function restorePreferences() {
    if (!chrome?.storage?.local) return;
    chrome.storage.local.get(["minimized", "fontScale", "sessionId"], (pref) => {
      if (pref.minimized) minimize();
      if (pref.fontScale) applyFontScale(pref.fontScale);
      state.sessionId = pref.sessionId || null;
    });
  }

  function savePreference(key, value) {
    if (!chrome?.storage?.local) return;
    chrome.storage.local.set({ [key]: value });
  }

  // --- event wiring -------------------------------------------------------
  function wireControls() {
    on("#micButton",    "click", toggleMic);
    on("#gaMinBtn",     "click", minimize);
    on("#gaCloseBtn",   "click", closeSidebar);
    on("#gaMinPill",    "click", restore);
    on("#gaInfoBtn",    "click", () => toggleDrawer("gaInfoDrawer"));
    on("#gaFontBtn",    "click", () => toggleDrawer("gaFontDrawer"));

    document.querySelectorAll(".ga-font-opt").forEach(btn => {
      btn.addEventListener("click", () => {
        const scale = parseFloat(btn.dataset.scale);
        applyFontScale(scale);
        savePreference("fontScale", scale);
      });
    });

    // Drag to move
    const header = document.getElementById("gaHeader");
    if (header) enableDrag(header);

    // Keyboard shortcut: Alt+M toggles mic
    document.addEventListener("keydown", (e) => {
      if (e.altKey && e.key.toLowerCase() === "m") {
        e.preventDefault();
        toggleMic();
      }
    });
  }

  function on(sel, ev, fn) {
    const el = document.querySelector(sel);
    if (el) el.addEventListener(ev, fn);
  }

  // --- drawer toggles -----------------------------------------------------
  function toggleDrawer(id) {
    const drawer = document.getElementById(id);
    const other = id === "gaInfoDrawer" ? "gaFontDrawer" : "gaInfoDrawer";
    document.getElementById(other)?.setAttribute("hidden", "");
    if (drawer.hasAttribute("hidden")) drawer.removeAttribute("hidden");
    else drawer.setAttribute("hidden", "");
  }

  // --- font scaling -------------------------------------------------------
  function applyFontScale(scale) {
    state.sidebar.style.setProperty("--ga-scale", String(scale));
    document.querySelectorAll(".ga-font-opt").forEach(opt => {
      opt.setAttribute("aria-checked",
        parseFloat(opt.dataset.scale) === scale ? "true" : "false");
    });
  }

  // --- minimize / restore / close -----------------------------------------
  function minimize() {
    state.sidebar.classList.add("minimized");
    document.getElementById("gaMinPill")?.removeAttribute("hidden");
    savePreference("minimized", true);
  }
  function restore() {
    state.sidebar.classList.remove("minimized");
    document.getElementById("gaMinPill")?.setAttribute("hidden", "");
    savePreference("minimized", false);
  }
  function closeSidebar() {
    if (state.listening) stopRecognition();
    state.sidebar.style.display = "none";
  }

  // --- drag handling ------------------------------------------------------
  function enableDrag(handle) {
    let dragging = false;
    let startX = 0, startY = 0, origX = 0, origY = 0;
    const ignoreSelectors = ".ga-icon-btn";

    handle.addEventListener("mousedown", (e) => {
      if (e.target.closest(ignoreSelectors)) return;
      dragging = true;
      startX = e.clientX; startY = e.clientY;
      const rect = state.sidebar.getBoundingClientRect();
      origX = rect.left; origY = rect.top;
      document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const nx = origX + (e.clientX - startX);
      const ny = origY + (e.clientY - startY);
      state.sidebar.style.left = `${Math.max(0, nx)}px`;
      state.sidebar.style.top  = `${Math.max(0, ny)}px`;
      state.sidebar.style.right = "auto";
    });

    document.addEventListener("mouseup", () => {
      dragging = false;
      document.body.style.userSelect = "";
    });
  }

  // --- voice recognition --------------------------------------------------
  function toggleMic() {
    if (state.listening) stopRecognition();
    else startRecognition();
  }

  function startRecognition() {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      renderError("Your browser doesn't support speech recognition. Please use Chrome.");
      return;
    }

    state.recognition = new SpeechRecognition();
    state.recognition.continuous = false;
    state.recognition.interimResults = false;
    state.recognition.lang = "en-US";

    state.recognition.onstart = () => {
      state.listening = true;
      setState("listening", "Listening…");
      const btn = document.getElementById("micButton");
      if (btn) btn.setAttribute("aria-pressed", "true");
      document.getElementById("gaMicHint").textContent = "Tap again to stop";
    };

    state.recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript.trim();
      handleTranscript(transcript);
    };

    state.recognition.onerror = (event) => {
      console.error("[GrandAssist] recognition error:", event.error);
      setState("idle", "Ready to listen");
      if (event.error === "not-allowed") {
        renderError("Microphone access was blocked. Please allow it in your browser settings.");
      } else if (event.error !== "aborted") {
        renderError(`Couldn't hear you (${event.error}). Please try again.`);
      }
      state.listening = false;
      document.getElementById("micButton")?.setAttribute("aria-pressed", "false");
      document.getElementById("gaMicHint").textContent = "Tap to speak";
    };

    state.recognition.onend = () => {
      state.listening = false;
      document.getElementById("micButton")?.setAttribute("aria-pressed", "false");
      document.getElementById("gaMicHint").textContent = "Tap to speak";
      if (state.sidebar.getAttribute("data-state") === "listening") {
        setState("idle", "Ready to listen");
      }
    };

    try { state.recognition.start(); }
    catch (e) { console.error(e); setState("idle", "Ready to listen"); }
  }

  function stopRecognition() {
    try { state.recognition?.stop(); } catch (_) {}
    state.listening = false;
  }

  function setState(name, statusText) {
    state.sidebar.setAttribute("data-state", name);
    const el = state.sidebar.querySelector(".ga-status-text");
    if (el) el.textContent = statusText;
  }

  // --- command handling ---------------------------------------------------
  function handleTranscript(transcript) {
    const lower = transcript.toLowerCase();
    renderMessage("user", transcript);
    const localWebsite = matchLocalWebsite(lower);
    if (localWebsite) {
      window.open(localWebsite.url, "_blank", "noopener");
      let reply = `Opening ${localWebsite.name}.`;
      if (localWebsite.name === "YouTube") {
        reply += " Now, in the search bar, type what you want to watch and press Enter.";
      }
      return renderMessage("ai", reply);
    }

    // Local DOM actions — never touch the backend
    if (lower.includes("scroll down")) {
      window.scrollBy({ top: 500, behavior: "smooth" });
      return renderMessage("ai", "Scrolled down.");
    }
    if (lower.includes("scroll up")) {
      window.scrollBy({ top: -500, behavior: "smooth" });
      return renderMessage("ai", "Scrolled up.");
    }
    if (lower.includes("scroll to top")) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return renderMessage("ai", "Back to the top.");
    }
    if (lower.includes("new tab")) {
      chrome.runtime.sendMessage({ action: "newTab" });
      return renderMessage("ai", "Opening a new tab.");
    }
    if (lower.includes("go back")) {
      window.history.back();
      return renderMessage("ai", "Going back.");
    }
    if (lower.includes("go forward")) {
      window.history.forward();
      return renderMessage("ai", "Going forward.");
    }
    if (lower.includes("close sidebar") || lower.includes("close the sidebar")) {
      return closeSidebar();
    }
    if (lower.includes("minimize") || lower.includes("minimise")) {
      return minimize();
    }

    // Everything else goes to the backend
    sendToBackend(transcript);
  }

  function matchLocalWebsite(text) {
    const isHowTo = text.includes("how") && (text.includes("do i") || text.includes("to "));
    if (isHowTo || !OPEN_VERBS.some(verb => text.includes(verb))) return null;
    return KNOWN_SITES.find(site => site.aliases.some(alias => text.includes(alias))) || null;
  }

  // --- backend I/O --------------------------------------------------------
  async function sendToBackend(query) {
    setState("thinking", "Thinking…");
    try {
      const data = await postChat(query);
      handleBackendResponse(data);
    } catch (err) {
      console.error("[GrandAssist] backend error:", err);
      renderError("Can't reach our server right now. Please make sure the backend is running, then try again.");
    } finally {
      setState("idle", "Ready to listen");
    }
  }

  async function postChat(query) {
    let lastError = null;
    for (const backend of BACKENDS) {
      try {
        const res = await fetch(`${backend}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_input: query,
            session_id: state.sessionId,
          }),
        });
        if (!res.ok) throw new Error(`${backend} returned HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError || new Error("No backend configured");
  }

  function handleBackendResponse(data) {
    if (data.url && data.type === "open web page") {
      window.open(data.url, "_blank", "noopener");
    }

    if (data.type === "pinterest_auth_required" && data.pinterest_auth_url) {
      renderMessage("ai", data.AI);
      renderAuthLink(data.pinterest_auth_url);
      return;
    }

    if (data.type === "pins" && Array.isArray(data.pins)) {
      renderMessage("ai", data.AI);
      renderPins(data.pins);
      return;
    }

    if (data.type === "error") {
      renderError(data.AI);
      return;
    }

    renderMessage("ai", data.AI);
  }

  // --- rendering ----------------------------------------------------------
  function clearWelcome() {
    if (!state.welcomeShown) return;
    document.getElementById("gaWelcome")?.remove();
    state.welcomeShown = false;
  }

  function renderMessage(role, text) {
    clearWelcome();
    const el = document.createElement("div");
    el.className = `ga-msg ${role}`;
    el.textContent = text;
    state.chat.appendChild(el);
    state.chat.scrollTop = state.chat.scrollHeight;
  }

  function renderError(text) {
    clearWelcome();
    const el = document.createElement("div");
    el.className = "ga-msg error";
    el.textContent = text;
    state.chat.appendChild(el);
    state.chat.scrollTop = state.chat.scrollHeight;
  }

  function renderAuthLink(url) {
    const wrap = document.createElement("div");
    wrap.className = "ga-msg ai";
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Connect Pinterest →";
    a.style.cssText = "color:#E60023;font-weight:700;text-decoration:underline;";
    wrap.appendChild(a);
    state.chat.appendChild(wrap);
  }

  function renderPins(pins) {
    const grid = document.createElement("div");
    grid.className = "ga-pins";
    pins.forEach(pin => {
      const card = document.createElement("a");
      card.className = "ga-pin";
      card.href = pin.link;
      card.target = "_blank";
      card.rel = "noopener";

      if (pin.image_url) {
        const img = document.createElement("img");
        img.src = pin.image_url;
        img.alt = pin.title || "Pinterest pin";
        img.loading = "lazy";
        card.appendChild(img);
      }
      if (pin.title) {
        const t = document.createElement("div");
        t.className = "ga-pin-title";
        t.textContent = pin.title;
        card.appendChild(t);
      }
      grid.appendChild(card);
    });
    state.chat.appendChild(grid);
    state.chat.scrollTop = state.chat.scrollHeight;
  }

  // Kick things off once the sidebar DOM exists
  if (document.getElementById("chatbotSidebar")) {
    init();
  } else {
    // Watch for injection by background.js
    const obs = new MutationObserver(() => {
      if (document.getElementById("chatbotSidebar")) {
        obs.disconnect();
        init();
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }
})();
