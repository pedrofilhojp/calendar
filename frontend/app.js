const API_BASE = "/api";
const tokenKey = "agenda.jwt";
const colorKey = "agenda.priorityColors";
const defaultPriorityColors = {
  1: "#22c55e",
  2: "#84cc16",
  3: "#facc15",
  4: "#fb923c",
  5: "#ef4444",
};

let appointments = [];
let currentMonth = new Date();
let calendarView = "month";
let editingAppointmentId = null;
let priorityColors = loadPriorityColors();

const authView = document.querySelector("#auth-view");
const dashboardView = document.querySelector("#dashboard-view");
const authForm = document.querySelector("#auth-form");
const registerButton = document.querySelector("#register-button");
const authMessage = document.querySelector("#auth-message");
const calendarGrid = document.querySelector("#calendar-grid");
const calendarTitle = document.querySelector("#calendar-title");
const monthCalendar = document.querySelector("#month-calendar");
const yearCalendar = document.querySelector("#year-calendar");
const appointmentList = document.querySelector("#appointment-list");
const dialog = document.querySelector("#appointment-dialog");
const appointmentForm = document.querySelector("#appointment-form");
const appointmentMessage = document.querySelector("#appointment-message");
const priorityInput = document.querySelector("#priority");
const priorityLabel = document.querySelector("#priority-label");
const priorityColorsPanel = document.querySelector("#priority-colors");
const appointmentDialogTitle = document.querySelector("#appointment-dialog-title");
const saveAppointmentButton = document.querySelector("#save-appointment-button");

function token() {
  return localStorage.getItem(tokenKey);
}

function setToken(value) {
  localStorage.setItem(tokenKey, value);
}

function clearToken() {
  localStorage.removeItem(tokenKey);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const rawBody = response.status === 204 ? "" : await response.text();
  const body = rawBody ? parseJson(rawBody) : null;

  if (!response.ok) {
    const detail = body?.detail || rawBody || "Erro na requisição";
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail);
  }
  return body;
}

function parseJson(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function loadPriorityColors() {
  try {
    return { ...defaultPriorityColors, ...JSON.parse(localStorage.getItem(colorKey) || "{}") };
  } catch {
    return { ...defaultPriorityColors };
  }
}

function savePriorityColors() {
  localStorage.setItem(colorKey, JSON.stringify(priorityColors));
}

function colorForPriority(priority) {
  return priorityColors[priority] || defaultPriorityColors[priority] || "#94a3b8";
}

function textColorForBackground(hex) {
  const value = hex.replace("#", "");
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return (r * 299 + g * 587 + b * 114) / 1000 > 145 ? "#07111f" : "#ffffff";
}

function applyPriorityStyles(element, priority) {
  const color = colorForPriority(priority);
  element.style.backgroundColor = color;
  element.style.color = textColorForBackground(color);
}

function showDashboard() {
  authView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
}

function showAuth() {
  dashboardView.classList.add("hidden");
  authView.classList.remove("hidden");
}

async function submitAuth(mode) {
  authMessage.textContent = "";
  const email = document.querySelector("#email").value.trim();
  const password = document.querySelector("#password").value;
  try {
    const data = await api(`/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token);
    showDashboard();
    await loadAppointments();
  } catch (error) {
    authMessage.textContent = error.message;
  }
}

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function sameDate(a, b) {
  return (
    a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
  );
}

function appointmentStartForDate(date) {
  const selected = new Date(date);
  const now = new Date();
  if (sameDate(selected, now)) {
    selected.setHours(now.getHours() + 1, 0, 0, 0);
    return selected;
  }
  selected.setHours(9, 0, 0, 0);
  return selected;
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function toDatetimeLocal(value) {
  const date = new Date(value);
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return offsetDate.toISOString().slice(0, 16);
}

function renderMetrics() {
  const now = new Date();
  const urgent = appointments.filter((item) => item.priority === 5 && new Date(item.event_time) >= now);
  const guests = appointments.reduce((total, item) => total + item.guest_emails.length, 0);
  document.querySelector("#metric-total").textContent = appointments.length;
  document.querySelector("#metric-urgent").textContent = urgent.length;
  document.querySelector("#metric-guests").textContent = guests;
}

function renderCalendar() {
  if (calendarView === "year") {
    renderYearCalendar();
    return;
  }
  monthCalendar.classList.remove("hidden");
  yearCalendar.classList.add("hidden");
  calendarGrid.innerHTML = "";
  const first = monthStart(currentMonth);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  calendarTitle.textContent = new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
  }).format(currentMonth);

  for (let index = 0; index < 42; index += 1) {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    const cell = document.createElement("article");
    cell.className = [
      "calendar-day",
      date.getMonth() !== currentMonth.getMonth() ? "outside" : "",
      sameDate(date, new Date()) ? "today" : "",
    ].filter(Boolean).join(" ");
    cell.tabIndex = 0;
    cell.title = "Adicionar compromisso";
    cell.addEventListener("click", () => openCreateDialog(date));
    cell.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openCreateDialog(date);
      }
    });
    const number = document.createElement("span");
    number.className = "day-number";
    number.textContent = date.getDate();
    cell.appendChild(number);

    appointments
      .filter((item) => sameDate(new Date(item.event_time), date))
      .forEach((item) => {
        const event = document.createElement("span");
        event.className = "event-pill";
        event.title = `${item.title} - ${formatDateTime(item.event_time)}`;
        event.textContent = item.title;
        applyPriorityStyles(event, item.priority);
        event.addEventListener("click", (clickEvent) => {
          clickEvent.stopPropagation();
          openEditDialog(item);
        });
        cell.appendChild(event);
      });
    calendarGrid.appendChild(cell);
  }
}

function renderYearCalendar() {
  monthCalendar.classList.add("hidden");
  yearCalendar.classList.remove("hidden");
  yearCalendar.innerHTML = "";
  calendarTitle.textContent = String(currentMonth.getFullYear());

  for (let month = 0; month < 12; month += 1) {
    const monthDate = new Date(currentMonth.getFullYear(), month, 1);
    const card = document.createElement("article");
    card.className = "year-month";
    const title = document.createElement("button");
    title.className = "year-month-title";
    title.type = "button";
    title.textContent = new Intl.DateTimeFormat("pt-BR", { month: "long" }).format(monthDate);
    title.addEventListener("click", () => {
      currentMonth = monthDate;
      setCalendarView("month");
    });
    card.appendChild(title);

    const grid = document.createElement("div");
    grid.className = "mini-month-grid";
    ["D", "S", "T", "Q", "Q", "S", "S"].forEach((day) => {
      const label = document.createElement("span");
      label.className = "mini-weekday";
      label.textContent = day;
      grid.appendChild(label);
    });

    const start = new Date(monthDate);
    start.setDate(monthDate.getDate() - monthDate.getDay());
    for (let index = 0; index < 42; index += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const events = appointments.filter((item) => sameDate(new Date(item.event_time), date));
      const day = document.createElement("button");
      day.type = "button";
      day.className = [
        "mini-day",
        date.getMonth() !== month ? "outside" : "",
        sameDate(date, new Date()) ? "today" : "",
      ].filter(Boolean).join(" ");
      day.textContent = date.getDate();
      if (events.length) {
        const highestPriority = Math.max(...events.map((item) => item.priority));
        applyPriorityStyles(day, highestPriority);
        day.title = events.map((item) => item.title).join(", ");
      }
      day.addEventListener("click", () => {
        openCreateDialog(date);
      });
      grid.appendChild(day);
    }

    card.appendChild(grid);
    yearCalendar.appendChild(card);
  }
}

function renderList() {
  appointmentList.innerHTML = "";
  const upcoming = [...appointments].sort((a, b) => new Date(a.event_time) - new Date(b.event_time));
  if (!upcoming.length) {
    appointmentList.innerHTML = '<p class="message">Nenhum compromisso agendado.</p>';
    return;
  }
  upcoming.forEach((item) => {
    const article = document.createElement("article");
    article.className = "appointment-item";
    article.innerHTML = `
      <header>
        <div>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${formatDateTime(item.event_time)}</p>
        </div>
        <div class="item-actions">
          <button class="edit-button" aria-label="Editar compromisso" data-id="${item.id}">Editar</button>
          <button class="delete-button" aria-label="Cancelar compromisso" data-id="${item.id}">×</button>
        </div>
      </header>
      <p><span class="priority-dot" data-priority="${item.priority}"></span> Prioridade ${item.priority} · ${item.guest_emails.length} convidados</p>
      <p>${escapeHtml(item.description || "")}</p>
    `;
    appointmentList.appendChild(article);
    applyPriorityStyles(article.querySelector(".priority-dot"), item.priority);
  });
}

function renderPriorityColors() {
  priorityColorsPanel.innerHTML = "";
  for (let priority = 1; priority <= 5; priority += 1) {
    const label = document.createElement("label");
    label.className = "color-control";
    label.innerHTML = `
      <span>Prioridade ${priority}</span>
      <input type="color" value="${colorForPriority(priority)}" data-priority="${priority}" />
    `;
    priorityColorsPanel.appendChild(label);
  }
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function render() {
  renderMetrics();
  renderCalendar();
  renderList();
  renderPriorityColors();
}

async function loadAppointments() {
  appointments = await api("/appointments");
  render();
}

function parseGuests(value) {
  return value
    .split(",")
    .map((email) => email.trim())
    .filter(Boolean);
}

function setCalendarView(view) {
  calendarView = view;
  document.querySelector("#month-view-button").classList.toggle("active", view === "month");
  document.querySelector("#year-view-button").classList.toggle("active", view === "year");
  renderCalendar();
}

function appointmentPayload() {
  const eventTime = document.querySelector("#event-time").value;
  return {
    title: document.querySelector("#title").value.trim(),
    description: document.querySelector("#description").value.trim(),
    event_time: new Date(eventTime).toISOString(),
    priority: Number(priorityInput.value),
    guest_emails: parseGuests(document.querySelector("#guests").value),
  };
}

function openCreateDialog(date = null) {
  editingAppointmentId = null;
  appointmentMessage.textContent = "";
  appointmentDialogTitle.textContent = "Novo compromisso";
  saveAppointmentButton.textContent = "Salvar e notificar";
  appointmentForm.reset();
  if (date) {
    document.querySelector("#event-time").value = toDatetimeLocal(appointmentStartForDate(date));
  }
  priorityInput.value = "3";
  priorityLabel.textContent = "3";
  dialog.showModal();
}

function openEditDialog(appointment) {
  editingAppointmentId = appointment.id;
  appointmentMessage.textContent = "";
  appointmentDialogTitle.textContent = "Editar compromisso";
  saveAppointmentButton.textContent = "Salvar alterações";
  document.querySelector("#title").value = appointment.title;
  document.querySelector("#description").value = appointment.description || "";
  document.querySelector("#event-time").value = toDatetimeLocal(appointment.event_time);
  priorityInput.value = appointment.priority;
  priorityLabel.textContent = appointment.priority;
  document.querySelector("#guests").value = appointment.guest_emails.join(", ");
  dialog.showModal();
}

authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth("login");
});

registerButton.addEventListener("click", () => submitAuth("register"));

document.querySelector("#logout-button").addEventListener("click", () => {
  clearToken();
  showAuth();
});

document.querySelector("#new-appointment-button").addEventListener("click", () => {
  openCreateDialog();
});

document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());

priorityInput.addEventListener("input", () => {
  priorityLabel.textContent = priorityInput.value;
});

document.querySelector("#prev-period").addEventListener("click", () => {
  const delta = calendarView === "month" ? -1 : -12;
  currentMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1);
  renderCalendar();
});

document.querySelector("#next-period").addEventListener("click", () => {
  const delta = calendarView === "month" ? 1 : 12;
  currentMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1);
  renderCalendar();
});

document.querySelector("#month-view-button").addEventListener("click", () => setCalendarView("month"));
document.querySelector("#year-view-button").addEventListener("click", () => setCalendarView("year"));

priorityColorsPanel.addEventListener("input", (event) => {
  if (event.target.type !== "color") return;
  priorityColors[event.target.dataset.priority] = event.target.value;
  savePriorityColors();
  renderCalendar();
  renderList();
});

appointmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  appointmentMessage.textContent = "";
  try {
    const path = editingAppointmentId ? `/appointments/${editingAppointmentId}` : "/appointments";
    const method = editingAppointmentId ? "PUT" : "POST";
    await api(path, {
      method,
      body: JSON.stringify(appointmentPayload()),
    });
    dialog.close();
    await loadAppointments();
  } catch (error) {
    appointmentMessage.textContent = error.message;
  }
});

appointmentList.addEventListener("click", async (event) => {
  const editButton = event.target.closest(".edit-button");
  const deleteButton = event.target.closest(".delete-button");
  if (editButton) {
    const appointment = appointments.find((item) => item.id === Number(editButton.dataset.id));
    if (appointment) openEditDialog(appointment);
    return;
  }
  if (deleteButton) {
    await api(`/appointments/${deleteButton.dataset.id}`, { method: "DELETE" });
    await loadAppointments();
  }
});

if (token()) {
  showDashboard();
  loadAppointments().catch(() => {
    clearToken();
    showAuth();
  });
} else {
  showAuth();
}
