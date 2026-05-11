const form = document.getElementById("aiChatForm");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("aiChatInput");
    const log = document.getElementById("aiChatLog");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    log.textContent = "思考中...";
    const response = await fetch("/api/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, context: { path: window.location.pathname } })
    });
    const data = await response.json();
    log.textContent = data.reply || JSON.stringify(data);
  });
}
