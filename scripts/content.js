  let recognition;
  let isListening = false;
  const micButton = document.getElementById("micButton");
  const instructions = document.getElementById("voiceCommands");

  function appendMessage(sender, text) {
    const chatWindow = document.getElementById("chatWindow");
    console.log("chatWindow:", chatWindow);
    const msgEl = document.createElement("div");
    msgEl.className = sender;
    msgEl.innerText = text;
    console.log("msgEl:", msgEl);
    chatWindow.appendChild(msgEl);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  function initVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in your browser.");
      return;
    }
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US"; 

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript.trim().toLowerCase();
      console.log("Recognized:", transcript);

      appendMessage("user", transcript);

      if (transcript.includes("scroll down")) {
        window.scrollBy({ top: 50, behavior: "smooth" });
      } else if (transcript.includes("scroll up")) {
        window.scrollBy({ top: -50, behavior: "smooth" });
      } else if (transcript.includes("new tab")) {
        chrome.runtime.sendMessage({ action: "newTab" });
      } else if (transcript.includes("next tab")) {
        chrome.runtime.sendMessage({ action: "nextTab" });
      } else if (transcript.includes("go back")) {
        window.history.back();
      } else if (transcript.includes("go forward")) {
        window.history.forward();
      } else  {
        sendToAI(transcript);
      }
    };

    recognition.onerror = (err) => console.error("Voice recognition error:", err);

    recognition.start();
  }

  function sendToAI(query) {
    appendMessage("user", query);
    fetch("https://tech-assistant-for-seniors-eb4876783faf.herokuapp.com/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_input: query }),
    })
      .then((res) => res.json())
      .then((data) => {
        appendMessage("ai", data.reply);
      })
      .catch((err) => {
        appendMessage("ai", "Sorry, an error occurred while processing your request.");
        console.error(err);
      });
  }

  document.addEventListener("click", (event) => {
    if (event.target && event.target.id === "micButton") {
      if (isListening) {
        recognition.stop();
        event.target.innerHTML = "🎤";
      } else {
        initVoiceRecognition();
        event.target.innerHTML = "🛑";
      }
      isListening = !isListening;
    }
  });

  //document.addEventListener("click", (event) => {
    //if (event.target && event.target.id === "infoButton") {
      //instructions.classList.toggle("show");
    //}
  //});
