// Copiar o comando de conexão
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  const text = b.dataset.copy, label = b.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t);
    t.select(); document.execCommand("copy"); t.remove();
  }
  b.textContent = "Copiado"; b.classList.add("done");
  setTimeout(() => { b.textContent = label; b.classList.remove("done"); }, 1800);
});

// Status ao vivo dos servidores (página inicial)
async function refreshStatus() {
  const rows = document.querySelectorAll("[data-server]");
  if (!rows.length) return;
  try {
    const list = await (await fetch("/api/status", { cache: "no-store" })).json();
    let online = 0, slots = 0;
    for (const s of list) {
      if (s.online) { online += s.players; slots += s.max; }
      const row = document.querySelector(`[data-server="${s.id}"]`);
      if (!row) continue;
      row.classList.toggle("off", !s.online);
      row.querySelector('[data-f="status"]').textContent = s.online ? "online" : "offline";
      row.querySelector('[data-f="players"]').textContent = s.players;
      row.querySelector('[data-f="map"]').textContent = s.map || "aguardando jogadores";
      const md = row.querySelector('[data-f="mode"]');
      md.textContent = s.mode_short || "—"; md.title = s.mode || "";
    }
    const o = document.querySelector('[data-live="online"]'); if (o) o.textContent = online;
    const f = document.querySelector('[data-live="free"]'); if (f) f.textContent = Math.max(0, slots - online);
  } catch { /* mantém os últimos valores */ }
}
setInterval(refreshStatus, 15000);

// Busca no ranking
const busca = document.getElementById("busca");
if (busca) busca.addEventListener("input", () => {
  const q = busca.value.trim().toLowerCase();
  document.querySelectorAll(".board a.s-row").forEach((r) => {
    r.hidden = q && !(r.dataset.names || "").includes(q);
  });
});
