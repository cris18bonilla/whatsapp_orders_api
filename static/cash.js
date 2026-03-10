const token = window.ADMIN_TOKEN || "";
const restaurantSlug = window.RESTAURANT_SLUG || "deaca";

const openCashBtn = document.getElementById("openCashBtn");
const refreshCashBtn = document.getElementById("refreshCashBtn");
const addMovementBtn = document.getElementById("addMovementBtn");
const closeCashBtn = document.getElementById("closeCashBtn");

const currentCashBox = document.getElementById("currentCashBox");
const cashStatus = document.getElementById("cashStatus");
const movementsList = document.getElementById("movementsList");

async function fetchCurrentCash() {
  cashStatus.textContent = "Cargando caja...";
  try {
    const res = await fetch(`/admin/api/cash/current?restaurant=${encodeURIComponent(restaurantSlug)}&token=${encodeURIComponent(token)}`);
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));

    renderCurrentCash(data.session);
    renderMovements(data.movements || []);
    cashStatus.textContent = "Caja actualizada.";
  } catch (e) {
    cashStatus.textContent = `Error: ${e.message}`;
  }
}

function renderCurrentCash(session) {
  if (!session) {
    currentCashBox.innerHTML = `<div class="muted">No hay caja abierta.</div>`;
    return;
  }

  currentCashBox.innerHTML = `
    <div><strong>Sesión:</strong> <span class="mono">${session.session_number || "-"}</span></div>
    <div><strong>Estado:</strong> ${session.status || "-"}</div>
    <div><strong>Apertura NIO:</strong> ${session.opening_fund_nio ?? 0}</div>
    <div><strong>Apertura USD:</strong> ${session.opening_fund_usd ?? 0}</div>
    <div><strong>Abierta:</strong> ${session.opened_at || "-"}</div>
    <div><strong>Notas:</strong> ${session.notes || "-"}</div>
  `;
}

function renderMovements(items) {
  if (!items.length) {
    movementsList.innerHTML = `<div class="muted">Sin movimientos.</div>`;
    return;
  }

  movementsList.innerHTML = items.map(m => `
    <div class="item">
      <div class="item-top">
        <div>
          <strong>${m.movement_type || "-"}</strong>
          <div class="muted">${m.sales_channel || "-"} · ${m.currency || "-"}</div>
        </div>
        <div class="amt ${m.movement_type === "expense" ? "bad" : "ok"}">
          ${m.amount ?? 0}
        </div>
      </div>
      <div class="muted" style="margin-top:6px;">${m.payment_method || "-"} · ${m.created_at || "-"}</div>
      <div style="margin-top:6px;">${m.notes || "-"}</div>
    </div>
  `).join("");
}

async function openCash() {
  cashStatus.textContent = "Abriendo caja...";
  try {
    const body = {
      pin: document.getElementById("openPin").value,
      opening_fund_nio: parseFloat(document.getElementById("openNio").value || "0"),
      opening_fund_usd: parseFloat(document.getElementById("openUsd").value || "0"),
      notes: document.getElementById("openNotes").value
    };

    const res = await fetch(`/admin/api/cash/open?restaurant=${encodeURIComponent(restaurantSlug)}&token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));

    cashStatus.textContent = "Caja abierta correctamente.";
    await fetchCurrentCash();
  } catch (e) {
    cashStatus.textContent = `Error al abrir caja: ${e.message}`;
  }
}

async function addMovement() {
  cashStatus.textContent = "Guardando movimiento...";
  try {
    const body = {
      pin: document.getElementById("movePin").value,
      movement_type: document.getElementById("moveType").value,
      sales_channel: document.getElementById("moveChannel").value,
      currency: document.getElementById("moveCurrency").value,
      amount: parseFloat(document.getElementById("moveAmount").value || "0"),
      payment_method: "cash",
      notes: document.getElementById("moveNotes").value
    };

    const res = await fetch(`/admin/api/cash/movement?restaurant=${encodeURIComponent(restaurantSlug)}&token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));

    cashStatus.textContent = "Movimiento guardado.";
    await fetchCurrentCash();
  } catch (e) {
    cashStatus.textContent = `Error al guardar movimiento: ${e.message}`;
  }
}

async function closeCash() {
  cashStatus.textContent = "Cerrando caja...";
  try {
    const body = {
      pin: document.getElementById("closePin").value,
      counted_cash_nio: parseFloat(document.getElementById("closeNio").value || "0"),
      counted_cash_usd: parseFloat(document.getElementById("closeUsd").value || "0"),
      notes: document.getElementById("closeNotes").value
    };

    const res = await fetch(`/admin/api/cash/close?restaurant=${encodeURIComponent(restaurantSlug)}&token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));

    cashStatus.textContent = "Caja cerrada.";
    await fetchCurrentCash();
  } catch (e) {
    cashStatus.textContent = `Error al cerrar caja: ${e.message}`;
  }
}

openCashBtn.addEventListener("click", openCash);
refreshCashBtn.addEventListener("click", fetchCurrentCash);
addMovementBtn.addEventListener("click", addMovement);
closeCashBtn.addEventListener("click", closeCash);

fetchCurrentCash();
