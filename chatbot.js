document.addEventListener("DOMContentLoaded", () => {
  const chatContainer = document.getElementById("chat-container");
  const chatBox = document.getElementById("chat-box");
  const userInput = document.getElementById("user-input");
  const closeBtn = document.getElementById("close-btn");
  const openChatBtn = document.getElementById("open-chat-btn");
  const sendBtn = document.querySelector(".send-btn");

  //clear convo
  let clearBtn = document.getElementById("clear-btn");
  if (!clearBtn) {
    clearBtn = document.createElement("button");
    clearBtn.id = "clear-btn";
    clearBtn.textContent = "🗑️";
    clearBtn.title = "Clear Conversation";

    const headerDiv = chatContainer.querySelector(".chat-header div");
    headerDiv.insertBefore(clearBtn, headerDiv.firstChild);
  }

  clearBtn.addEventListener("click", () => {
    chatBox.innerHTML = "";
    userInput.focus();
  });

  //Chat open/close
  chatContainer.style.display = "none";
  openChatBtn.style.display = "block";

  closeBtn.addEventListener("click", () => {
    chatContainer.style.display = "none";
    openChatBtn.style.display = "block";
  });

  openChatBtn.addEventListener("click", () => {
    chatContainer.style.display = "flex";
    openChatBtn.style.display = "none";
    userInput.focus();
  });

  //Send message
  sendBtn.addEventListener("click", sendMessage);
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) return;

    appendMessage(message, "user");
    userInput.value = "";
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      });

      const data = await response.json();
      let botMessage = data.response || "⚠️ No response from the bot.";

      //Convert Markdown to make clear chats
      botMessage = botMessage.replace(/\*\*(.*?)\*\*/g, "<b>$1</b>");
      botMessage = botMessage.replace(/\*(.*?)\*/g, "<i>$1</i>");
      botMessage = botMessage.replace(/\n/g, "<br>");

      appendMessage(botMessage, "bot", true);
      chatBox.scrollTop = chatBox.scrollHeight;

    } catch (err) {
      appendMessage("⚠️ Error contacting server.", "bot");
    }
  }
  

  //message to chat
  function appendMessage(message, sender, isHTML = false) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${sender}`;
    if (isHTML) {
      msgDiv.innerHTML = message; 
    } else {
      msgDiv.textContent = message; 
    }
    chatBox.appendChild(msgDiv);
  }
});