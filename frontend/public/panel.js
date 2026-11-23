"use strict";

const el = id => document.getElementById(id);
const statuses = {
  PENDING: "Pendiente", CONFIRMED: "Confirmado", PREPARING: "En preparación",
  READY: "Listo", ON_THE_WAY: "En camino", DELIVERED: "Entregado", CANCELLED: "Cancelado",
};
const currency = new Intl.NumberFormat("es-AR", {style: "currency", currency: "ARS"});
function localDate(value) {
  const date = typeof value === "number" ? new Date(value * 1000)
    : new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + "Z");
  return date.toLocaleString("es-AR", {timeZone: "America/Argentina/Buenos_Aires"});
}
let demoTimer = null;
let demoSnapshot = "";
let demoWaiting = false;
let demoSending = false;
let demoManual = false;
let token = sessionStorage.getItem("commercial_session");
let account;
let registering = true;
let selectedOrder;
let ordersRequest = 0;
let selectedChat = null;
let chatManual = false;
let currentTab = "orders";
let inboxTimer = null;
let chatGeneration = 0;
let alertSnapshot = "";
let conversationsSnapshot = "";

async function api(path, method = "GET", body) {
  const sessionToken = token;
  const headers = {Accept: "application/json"};
  if (token) headers.Authorization = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {method, headers, body: JSON.stringify(body), cache: "no-store"});
  const data = await response.json().catch(() => null);
  if (sessionToken !== token) throw new Error("La sesión cambió. Volvé a intentar.");
  if (!response.ok) {
    if (response.status === 401 && token) endSession();
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? "Revisá los datos ingresados." : "No se pudo completar la operación.");
  }
  return data;
}
function notice(id, text = "", kind = "error") {
  const node = el(id);
  node.textContent = text;
  node.dataset.kind = kind;
  node.hidden = !text;
}
function busy(button, callback, status) {
  button.disabled = true;
  notice(status);
  return Promise.resolve().then(callback).catch(error => notice(status, error.message))
    .finally(() => { button.disabled = false; });
}
function fields(form) {
  return Object.fromEntries(new FormData(form));
}
function setMode(next) {
  registering = next;
  const title = next ? "Crear perfil del negocio" : "Abrir mi perfil";
  el("registration").hidden = el("registration").disabled = !next;
  el("auth-title").textContent = el("auth-submit").textContent = title;
  el("auth-subtitle").textContent = next ? "Completá los datos del local para abrir tu panel." : "Usá el correo y la clave que elegiste para tu perfil.";
  el("auth-question").textContent = next ? "¿Ya tenés un perfil?" : "¿Querés crear otro perfil?";
  el("auth-switch").textContent = next ? "Abrir mi perfil" : "Crear perfil del negocio";
  el("password").minLength = next ? 12 : 1;
  el("password").autocomplete = next ? "new-password" : "current-password";
  notice("auth-status");
}
function endSession() {
  token = account = selectedOrder = selectedChat = null;
  clearInterval(inboxTimer);
  clearInterval(demoTimer);
  demoTimer = null;
  demoSnapshot = "";
  demoWaiting = demoSending = demoManual = false;
  el("demo-messages").replaceChildren();
  el("demo-message-form").reset();
  el("demo-banner").hidden = true;
  inboxTimer = null;
  el("alert-summary").hidden = true;
  el("alert-count").textContent = "";
  el("chat-history").replaceChildren();
  el("alert-list").replaceChildren();
  el("conversation-list").replaceChildren();
  el("chat-reply-form").reset();
  el("chat-detail").hidden = true;
  el("chat-placeholder").hidden = false;
  alertSnapshot = conversationsSnapshot = "";
  sessionStorage.removeItem("commercial_session");
  if (el("order-dialog").open) el("order-dialog").close();
  if (el("wa-dialog").open) el("wa-dialog").close();
  el("panel").hidden = el("logout").hidden = true;
  el("access").hidden = false;
  el("auth-form").reset();
  for (const id of ["order-list", "product-list", "order-detail"]) el(id).replaceChildren();
  el("payment-form").reset();
  setMode(true);
}
async function startSession() {
  account = await api("/auth/me");
  const business = await api("/businesses/me");
  el("business-label").textContent = business.name;
  el("account-label").textContent = account.name + (account.role === "ADMIN" ? " · Administración" : " · Personal");
  el("product-form").hidden = account.role !== "ADMIN";
  document.querySelector('[data-tab="profile"]').hidden = account.role !== "ADMIN";
  el("access").hidden = true;
  el("panel").hidden = el("logout").hidden = false;
  el("demo-banner").hidden = !account.is_demo;
  document.querySelector('[data-tab="demo-chat"]').hidden = !account.is_demo;
  el("logout").textContent = account.is_demo ? "Salir de la demo" : "Salir del perfil";
  await showTab(account.is_demo ? "demo-chat" : "orders");
  clearInterval(demoTimer);
  if (account.is_demo) demoTimer = setInterval(() => {
    if (account?.is_demo && currentTab === "demo-chat" && !demoSending) loadDemoState().catch(error => notice("demo-chat-status", error.message));
  }, 2500);
  await refreshAttention();
  clearInterval(inboxTimer);
  inboxTimer = setInterval(() => {
    if (account) refreshAttention().catch(error => notice("panel-status", error.message));
  }, 8000);
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function action(text, callback) {
  const button = node("button", text, "button");
  button.type = "button";
  button.addEventListener("click", () => busy(button, callback, "panel-status"));
  return button;
}
function table(target, columns, rows, empty) {
  if (!rows.length) {
    target.replaceChildren(node("p", empty, "empty"));
    return;
  }
  const t = node("table");
  const head = t.createTHead().insertRow();
  for (const column of columns) {
    const th = node("th", column);
    th.scope = "col";
    head.append(th);
  }
  const body = t.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) tr.insertCell().append(value instanceof Node ? value : String(value ?? "—"));
  }
  target.replaceChildren(t);
}
function label(status) {
  const tones = {
    PENDING: "pending", CONFIRMED: "good", PREPARING: "progress",
    READY: "progress", ON_THE_WAY: "progress", DELIVERED: "good", CANCELLED: "cancelled",
  };
  return node("span", statuses[status] || status, "badge " + (tones[status] || ""));
}
async function loadOrders() {
  const request = ++ordersRequest;
  const filter = el("order-filter").value;
  const orders = await api("/orders/" + (filter ? "?status=" + encodeURIComponent(filter) : ""));
  if (request !== ordersRequest || !account) return;
  table(el("order-list"), ["Pedido", "Fecha", "Cliente", "Total", "Estado", "Pago", "Detalle"], orders.map(o => [
    "#" + o.id, localDate(o.created_at), node("span", o.customer_name || o.customer_phone, "customer-name"),
    currency.format(o.total), label(o.status), label(o.payment_status), orderDetailButton(o.id),
  ]), filter ? "No hay pedidos con este estado." : "Todavía no hay pedidos.");
}
function orderDetailButton(id) {
  const button = action("Ver", () => openOrder(id));
  button.setAttribute("aria-label", "Ver pedido #" + id);
  return button;
}
async function openOrder(id) {
  const order = await api("/orders/" + id);
  selectedOrder = order.id;
  el("detail-title").textContent = "Pedido #" + order.id;
  const pendingTransfer = order.payment_method === "TRANSFER" && order.payment_status === "PENDING";
  el("transfer-form").hidden = account.is_demo || !pendingTransfer || order.status === "CANCELLED";
  el("demo-payment").hidden = !account.is_demo || !pendingTransfer || order.status === "CANCELLED";
  el("transfer-form").reset();
  for (const option of el("new-state").options) {
    option.disabled = pendingTransfer && !["PENDING", "CANCELLED"].includes(option.value);
  }
  el("new-state").value = order.status;
  notice("detail-status");
  el("order-detail").replaceChildren(
    node("p", "Cliente: " + (order.customer_name || "Sin nombre") + " · " + order.customer_phone),
    node("p", order.delivery_type === "DELIVERY" ? "Envío: " + (order.delivery_address || "Sin dirección") : "Retiro en el local"),
    node("p", "Total: " + currency.format(order.total) + " · Pago: " + (statuses[order.payment_status] || order.payment_status)),
    ...order.items.map(i => node("p", i.quantity + " × " + (i.product_name || "Producto #" + i.product_id))),
    ...(order.notes ? [node("p", "Notas: " + order.notes)] : []),
  );
  if (!el("order-dialog").open) el("order-dialog").showModal();
}
async function loadCatalog() {
  const products = await api("/products/");
  if (!account) return;
  const admin = account.role === "ADMIN";
  table(el("product-list"), ["Producto", "Precio", "Disponibilidad", ...(admin ? ["Acción"] : [])], products.map(p => [
    p.name, currency.format(p.price), p.active ? "Disponible" : "Inactivo",
    ...(admin ? [action(p.active ? "Desactivar" : "Activar", async () => {
      await api("/products/" + p.id + "/status?active=" + !p.active, "PATCH");
      await loadCatalog();
    })] : []),
  ]), "Todavía no hay productos en el catálogo.");
}
const whatsappSettings = "/businesses/me/whatsapp";

function renderWhatsApp(connection) {
  const connected = connection.mode === "simulated";
  el("wa-status").textContent = connected
    ? "Conexión simulada · " + connection.display_phone
    : "Sin número conectado. Prepará una línea nueva siguiendo los pasos de arriba o explorá la simulación.";
  el("wa-connect").hidden = connected;
  el("wa-test").hidden = el("wa-disconnect").hidden = !connected;
}

async function loadWhatsApp() {
  try {
    renderWhatsApp(await api(whatsappSettings));
  } catch (error) {
    el("wa-status").textContent = error.message;
  }
}

async function loadProfile() {
  const business = await api("/businesses/me");
  el("mercado-pago").hidden = el("whatsapp-settings").hidden = Boolean(account.is_demo);
  el("payment-form").querySelector("button").disabled = Boolean(account.is_demo);
  for (const input of el("payment-form").elements) input.disabled = Boolean(account.is_demo);
  const connection = account.is_demo ? {connected: false} : await api("/businesses/me/mercado-pago");
  for (const name of ["alias", "cbu", "payment_provider"]) el("payment-form").elements.namedItem(name).value = business[name] ?? "";
  el("mp-status").textContent = connection.connected ? "Cuenta vinculada" : "Cuenta sin vincular";
  el("connect").hidden = connection.connected;
  if (!account.is_demo) await loadWhatsApp();
}
async function showTab(tab) {
  currentTab = tab;
  const names = {"demo-chat": "Probar como cliente", orders: "Pedidos", inbox: "Chats y alertas", catalog: "Catálogo", profile: "Perfil"};
  el("panel-title").textContent = names[tab];
  Object.keys(names).forEach(name => { el(name).hidden = name !== tab; });
  document.querySelectorAll("[data-tab]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.tab === tab));
  });
  notice("panel-status");
  await {"demo-chat": loadDemo, orders: loadOrders, inbox: loadInbox, catalog: loadCatalog, profile: loadProfile}[tab]();
}
function formHandler(id, status, handler) {
  el(id).addEventListener("submit", event => {
    event.preventDefault();
    const data = fields(event.currentTarget);
    busy(event.submitter || event.currentTarget.querySelector("button[type=submit], button:not([type])"), () => handler(data), status);
  });
}
el("auth-switch").onclick = () => setMode(!registering);
el("show-password").onclick = () => {
  const show = el("password").type === "password";
  el("password").type = show ? "text" : "password";
  el("show-password").textContent = show ? "Ocultar" : "Mostrar";
  el("show-password").setAttribute("aria-pressed", String(show));
};
el("logout").onclick = endSession;
for (const id of ["order-filter", "new-state"]) {
  if (id === "order-filter") el(id).add(new Option("Todos", ""));
  for (const [value, name] of Object.entries(statuses)) el(id).add(new Option(name, value));
}
el("order-filter").onchange = () => loadOrders().catch(error => notice("panel-status", error.message));
el("reload-orders").onclick = () => busy(el("reload-orders"), loadOrders, "panel-status");
el("reload-profile").onclick = () => busy(el("reload-profile"), loadProfile, "panel-status");
document.querySelectorAll("[data-tab]").forEach(button => {
  button.onclick = () => busy(button, () => showTab(button.dataset.tab), "panel-status");
});
formHandler("auth-form", "auth-status", async data => {
  if (registering) {
    data.alias = data.alias.trim() || null;
    data.cbu = data.cbu.trim() || null;
    if (!data.alias && !data.cbu) throw new Error("Ingresá un alias o CBU/CVU para el perfil del negocio.");
    await api("/auth/register-business", "POST", data);
  }
  const credentials = await api("/auth/login", "POST", {email: data.email, password: data.password});
  token = credentials.access_token;
  sessionStorage.setItem("commercial_session", token);
  el("auth-form").reset();
  try { await startSession(); if (registering) await showTab("profile"); }
  catch (error) {
    if (el("panel").hidden) endSession();
    else { notice("panel-status", error.message); return; }
    throw error;
  }
});
formHandler("product-form", "panel-status", async data => {
  await api("/products/", "POST", data);
  el("product-form").reset();
  await loadCatalog();
  notice("panel-status", "Producto agregado.", "success");
});
formHandler("payment-form", "panel-status", async data => {
  await api("/businesses/me/payment-settings", "PATCH", Object.fromEntries(
    Object.entries(data).map(([key, value]) => [key, value.trim() || null])
  ));
  await loadProfile();
  notice("panel-status", "Datos de cobro guardados.", "success");
});
formHandler("transfer-form", "detail-status", async () => {
  const id = selectedOrder;
  if (!el("transfer-form").elements.namedItem("verified").checked) return;
  await api("/orders/" + id + "/confirm-transfer", "POST");
  if (!el("order-dialog").open || selectedOrder !== id) {
    await loadOrders();
    return;
  }
  await openOrder(id);
  await loadOrders();
  notice("detail-status", "Transferencia confirmada.", "success");
});
formHandler("order-state-form", "detail-status", async () => {
  const id = selectedOrder;
  await api("/orders/" + id + "/status", "PATCH", {status: el("new-state").value});
  await openOrder(id);
  await loadOrders();
  notice("detail-status", "Estado actualizado.", "success");
});
el("wa-connect").onclick = () => {
  notice("wa-dialog-status");
  el("wa-dialog").showModal();
};
el("wa-authorize").onclick = () => busy(el("wa-authorize"), async () => {
  renderWhatsApp(await api(whatsappSettings + "/simulation", "PUT"));
  el("wa-dialog").close();
  el("wa-test").focus();
  notice("panel-status", "Número de prueba conectado.", "success");
}, "wa-dialog-status");
el("wa-test").onclick = () => busy(el("wa-test"), async () => {
  renderWhatsApp(await api(whatsappSettings + "/simulation/test", "POST"));
  notice("panel-status", "El número de prueba está asociado a tu local.", "success");
}, "panel-status");
el("wa-disconnect").onclick = () => busy(el("wa-disconnect"), async () => {
  renderWhatsApp(await api(whatsappSettings + "/simulation", "DELETE"));
  el("wa-connect").focus();
  notice("panel-status", "Conexión de prueba eliminada.", "success");
}, "panel-status");
el("connect").onclick = () => busy(el("connect"), async () => {
  const result = await api("/businesses/me/mercado-pago/connect", "POST");
  const url = new URL(result.authorization_url);
  if (url.origin !== "https://auth.mercadopago.com" || url.pathname !== "/authorization") {
    throw new Error("Mercado Pago devolvió un enlace inesperado.");
  }
  location.assign(url.href);
}, "panel-status");
setMode(true);
if (token) startSession().catch(error => {
  if (el("panel").hidden) {
    endSession();
    notice("auth-status", error.message);
  } else notice("panel-status", error.message);
});


async function refreshAttention() {
  if (currentTab === "inbox") return loadInbox();
  const data = await api("/alerts/");
  if (account) renderAlertCount(data.pending_count);
}
function renderAlertCount(count) {
  el("alert-count").textContent = count ? "(" + count + ")" : "";
  el("alert-summary").hidden = !count;
  el("alert-summary-text").textContent = "Tenés " + count + " alerta" + (count === 1 ? "" : "s") + " pendiente" + (count === 1 ? "" : "s") + " de atención.";
}
async function downloadClientAttachment(id) {
  const sessionToken = token;
  const response = await fetch("/alerts/" + id + "/attachment", {headers: {Authorization: "Bearer " + token}});
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "No se pudo descargar el adjunto.");
  }
  const blob = await response.blob();
  if (token !== sessionToken) throw new Error("La sesión cambió.");
  const url = URL.createObjectURL(blob);
  const link = node("a");
  link.href = url;
  link.download = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "adjunto-cliente";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function loadInbox() {
  const [alerts, chats] = await Promise.all([api("/alerts/"), api("/conversations/")]);
  if (!account) return;
  renderAlertCount(alerts.pending_count);
  const signature = JSON.stringify(alerts.items);
  if (signature !== alertSnapshot || !el("alert-list").childNodes.length) {
    alertSnapshot = signature;
    const names = {complaint: "Reclamo o atención humana", transfer_claim: "Transferencia por verificar", attachment: "Adjunto para revisar"};
    el("alert-list").replaceChildren(...alerts.items.map(a => {
      const card = node("article", undefined, "attention-card");
      card.append(node("h3", names[a.kind] || "Revisión pendiente"),
        node("p", localDate(a.created_at), "muted"), node("p", a.message));
      if (a.kind === "transfer_claim") card.append(node("p", account.is_demo ? "Aviso ficticio de pago: abrí el pedido para simular su aprobación o rechazo." : "El cliente avisó un pago. Verificá los movimientos de la cuenta antes de confirmarlo.", "muted"));
      const buttons = node("div", undefined, "toolbar");
      buttons.append(action("Abrir chat", () => selectChat(a.conversation_id)));
      if (a.order_id) buttons.append(action(a.kind === "transfer_claim" ? (account.is_demo ? "Simular pago del pedido #" : "Verificar pago del pedido #") + a.order_id : "Ver pedido #" + a.order_id, () => openOrder(a.order_id)));
      else buttons.append(node("span", "Sin pedido asociado todavía", "muted"));
      if (a.has_attachment) buttons.append(action("Descargar adjunto", () => downloadClientAttachment(a.id)));
      buttons.append(action("Marcar atendida", async () => {
        await api("/alerts/" + a.id + "/resolve", "PATCH");
        await loadInbox();
        notice("panel-status", "Alerta atendida. El pago y el control del chat no se modificaron.", "success");
      }));
      card.append(buttons);
      return card;
    }));
    if (!alerts.items.length) el("alert-list").append(node("p", "No hay alertas pendientes.", "empty"));
  }
  const chatSignature = JSON.stringify(chats);
  if (chatSignature !== conversationsSnapshot || !el("conversation-list").childNodes.length) {
    conversationsSnapshot = chatSignature;
    el("conversation-list").replaceChildren(...chats.map(c => {
      const button = action(c.phone + " · " + (c.manual ? "Atención manual" : "IA habilitada"), () => selectChat(c.conversation_id));
      button.classList.add("conversation-button");
      button.setAttribute("aria-pressed", String(selectedChat === c.conversation_id));
      return button;
    }));
    if (!chats.length) el("conversation-list").append(node("p", "Todavía no hay conversaciones.", "empty"));
  }
  if (selectedChat) await loadChat(selectedChat);
}
async function selectChat(id) {
  selectedChat = id;
  conversationsSnapshot = "";
  notice("chat-status");
  await api("/conversations/" + encodeURIComponent(id) + "/attention", "PATCH", {action: "read"});
  await loadInbox();
}
async function loadChat(id) {
  const generation = ++chatGeneration;
  const chat = await api("/conversations/" + encodeURIComponent(id));
  if (!account || id !== selectedChat || generation !== chatGeneration) return;
  el("chat-detail").hidden = false;
  el("chat-placeholder").hidden = true;
  el("chat-title").textContent = chat.phone;
  chatManual = chat.manual;
  el("chat-state").textContent = chat.manual ? "Atención manual · IA pausada" : "IA habilitada";
  el("take-chat").disabled = chat.manual;
  el("release-chat").disabled = !chat.manual;
  el("chat-reply").disabled = el("send-chat-reply").disabled = !chat.manual;
  el("chat-order").hidden = !chat.order_id;
  el("chat-order").onclick = () => busy(el("chat-order"), () => openOrder(chat.order_id), "chat-status");
  const history = el("chat-history");
  const atBottom = history.scrollTop + history.clientHeight >= history.scrollHeight - 40;
  const previousTop = history.scrollTop;
  history.replaceChildren(...chat.history.map(t => {
    const bubble = node("div", undefined, "chat-turn " + (t.role === "customer" ? "customer-turn" : "assistant-turn"));
    bubble.append(node("strong", t.role === "customer" ? "Cliente" : "Local / asistente"), node("p", t.text));
    return bubble;
  }));
  history.scrollTop = atBottom ? history.scrollHeight : previousTop;
}
el("reload-inbox").onclick = () => busy(el("reload-inbox"), loadInbox, "panel-status");
el("view-alerts").onclick = () => showTab("inbox").catch(error => notice("panel-status", error.message));
for (const [id, actionName] of [["take-chat", "takeover"], ["release-chat", "release"]]) {
  el(id).onclick = () => busy(el(id), async () => {
    const chat = selectedChat;
    await api("/conversations/" + encodeURIComponent(chat) + "/attention", "PATCH", {action: actionName});
    await loadInbox();
  }, "chat-status").finally(() => {
    if (selectedChat) el(id).disabled = id === "take-chat" ? chatManual : !chatManual;
  });
}
formHandler("chat-reply-form", "chat-status", async data => {
  const id = selectedChat;
  if (!id) return;
  await api("/conversations/" + encodeURIComponent(id) + "/attention", "PATCH", {action: "reply", message: data.message.trim()});
  el("chat-reply-form").reset();
  await loadInbox();
  notice("chat-status", id.startsWith("whatsapp:")
    ? "Respuesta en cola de envío a WhatsApp. El chat sigue en atención manual."
    : "Respuesta guardada en la conversación de prueba. El chat sigue en atención manual.", "success");
});


async function beginDemo(button) {
  if (token && !account?.is_demo) throw new Error("Salí del perfil actual antes de abrir la demo.");
  const credentials = await api("/demo/session", "POST");
  endSession();
  token = credentials.access_token;
  sessionStorage.setItem("commercial_session", token);
  await startSession();
}
el("try-demo").onclick = () => busy(el("try-demo"), () => beginDemo(), "demo-entry-status");
el("new-demo").onclick = () => busy(el("new-demo"), () => beginDemo(), "panel-status");
el("demo-see-orders").onclick = () => busy(el("demo-see-orders"), () => showTab("orders"), "demo-chat-status");

function renderDemo(data) {
  demoWaiting = data.due_at !== null && !data.manual;
  demoManual = data.manual;
  const snapshot = JSON.stringify(data.history);
  if (snapshot !== demoSnapshot) {
    const turns = data.history.map(turn => {
      const item = node("div", undefined, "chat-turn" + (turn.role === "assistant" ? " assistant-turn" : ""));
      item.append(node("strong", turn.role === "customer" ? "Cliente de prueba" : "Atención del local"), node("p", turn.text));
      return item;
    });
    el("demo-messages").replaceChildren(...turns);
    el("demo-messages").scrollTop = el("demo-messages").scrollHeight;
    demoSnapshot = snapshot;
  }
  el("demo-chat-mode").textContent = data.manual
    ? "Atención humana: la IA está pausada en este chat. Podés responder o devolverle el control desde Chats y alertas."
    : demoWaiting ? "Esperando la respuesta del asistente…" : "El asistente está disponible.";
  el("demo-provider").textContent = data.provider === "simulated"
    ? "Modo guiado sin IA: usa reglas locales y ejemplos para explorar el flujo. No consume una API."
    : "IA real · " + data.provider + ". Interpreta mensajes libres; puede equivocarse y pedir aclaraciones.";
  el("demo-send").disabled = demoSending || demoWaiting;
  el("demo-retry").hidden = !demoWaiting;
}
async function loadDemoState() {
  const data = await api("/demo/state");
  if (!account?.is_demo) return;
  renderDemo(data);
}
async function loadDemo() {
  await loadDemoState();
  const products = await api("/products/");
  if (!account?.is_demo) return;
  el("demo-menu").replaceChildren(...products.filter(p => p.active).map(p => node("p", p.name + " · " + currency.format(p.price))));
}
for (const text of ["Hola", "¿Cuánto sale la pizza muzzarella?", "Quiero dos muzzas para retirar y pago por transferencia", "Sí, confirmo", "Ya hice la transferencia", "Quiero hablar con una persona"]) {
  const button = node("button", text, "button conversation-button");
  button.type = "button";
  button.onclick = () => { el("demo-message").value = text; el("demo-message").focus(); };
  el("demo-examples").append(button);
}
formHandler("demo-message-form", "demo-chat-status", async data => {
  if (demoSending || demoWaiting) return;
  const message = data.message.trim();
  if (!message) throw new Error("Escribí un mensaje.");
  demoSending = true;
  el("demo-chat-mode").textContent = "El asistente está procesando el mensaje…";
  try {
    const reply = await api("/demo/messages", "POST", {message, event_id: crypto.randomUUID()});
    el("demo-message-form").reset();
    renderDemo(reply);
    await refreshAttention();
  } catch (error) {
    await loadDemoState().catch(() => {});
    throw error;
  } finally {
    demoSending = false;
    el("demo-send").disabled = demoWaiting;
    // The generic busy helper also restores the button; restore our waiting state afterwards.
    setTimeout(() => { el("demo-send").disabled = demoWaiting; }, 0);
  }
});
el("demo-retry").onclick = () => busy(el("demo-retry"), async () => {
  renderDemo(await api("/demo/process", "POST"));
}, "demo-chat-status");
for (const result of ["approved", "rejected"]) {
  const button = el("demo-payment-" + result);
  button.onclick = () => busy(button, async () => {
    const id = selectedOrder;
    await api("/demo/orders/" + id + "/payment", "POST", {result});
    await openOrder(id);
    notice("detail-status", result === "approved" ? "Pago simulado aprobado. No se cobró dinero." : "Pago simulado rechazado. El pedido sigue pendiente.", "success");
    await loadOrders();
    await refreshAttention();
  }, "detail-status");
}
fetch("/demo/config", {cache: "no-store"}).then(response => {
  if (!response.ok) throw new Error("Demo no disponible");
  return response.json();
}).then(config => {
  el("try-demo").disabled = !config.enabled;
  el("profile-access").hidden = Boolean(config.demo_only);
  el("demo-entry-note").textContent = config.enabled
    ? "Sin registro. Sesión de una hora y datos separados para cada visitante. Pagos simulados."
    : "La demo está deshabilitada en esta instalación. Consultá la guía de instalación.";
}).catch(() => { el("demo-entry-note").textContent = "No pudimos conectar con el servidor. Verificá que esté encendido."; });
