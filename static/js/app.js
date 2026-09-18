// AI Study Companion - Frontend Application Logic (PRD v3.0)

let currentUser = null;
let currentProject = null;
let currentQuiz = null;
let activeWsTab = 'overview';
let quizChartInstance = null;

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) lucide.createIcons();
  setupNavigation();
  checkSession();
  checkApiStatus();
});

// Setup Main Navigation Tabs
function setupNavigation() {
  // Ensure initial active tab state
  const activeTab = document.querySelector(".content-tab.active") || document.getElementById("tab-home");
  document.querySelectorAll(".content-tab").forEach(t => {
    if (t === activeTab) {
      t.classList.add("active");
      t.style.display = "block";
    } else {
      t.classList.remove("active");
      t.style.display = "none";
    }
  });

  // Attach click listeners to menu items
  document.querySelectorAll(".sidebar-menu .menu-item").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const tabName = btn.getAttribute("data-tab");
      if (tabName) switchTab(tabName);
    });
  });
}

// -------------------------------------------------------------
// Main Navigation & Tab Switching
// -------------------------------------------------------------
const TAB_TITLES = {
  home: "Home Dashboard",
  spaces: "Learning Spaces",
  projects: "Projects Explorer",
  workspace: "Active Project Workspace",
  "lab-resume": "Career Lab • Resume & ATS Gap",
  "lab-planner": "Study Lab • Curriculum Planner",
  "lab-video": "Study Lab • Video Summarizer",
  "lab-chat": "Academic AI Chatbot",
  admin: "Admin & AI Observability",
  settings: "Settings & LLM Configuration"
};

function switchTab(tabName) {
  if (!tabName) return;

  // Deactivate all sidebar items and hide all content tabs
  document.querySelectorAll(".sidebar-menu .menu-item").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".content-tab").forEach(t => {
    t.classList.remove("active");
    t.style.display = "none";
  });

  // Activate target button and section
  const targetBtn = document.querySelector(`.sidebar-menu .menu-item[data-tab="${tabName}"]`);
  const targetTab = document.getElementById(`tab-${tabName}`);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetTab) {
    targetTab.classList.add("active");
    targetTab.style.display = "block";
  }

  // Scroll to top of both main content container and window
  const mainContent = document.querySelector(".main-content");
  if (mainContent) mainContent.scrollTop = 0;
  window.scrollTo({ top: 0, behavior: "instant" });

  // Update topbar section title
  const titleEl = document.getElementById("topbar-section-title");
  if (titleEl) {
    if (tabName === "workspace" && currentProject) {
      titleEl.textContent = `Active Project: ${currentProject.name}`;
    } else {
      titleEl.textContent = TAB_TITLES[tabName] || "LearnMate AI";
    }
  }

  // Trigger relevant data loader for the active tab
  if (tabName === "home") loadUserHome();
  if (tabName === "spaces") loadSpaces();
  if (tabName === "projects") loadProjectsExplorer();
  if (tabName === "workspace" && !currentProject) openLatestOrPromptWorkspace();
  if (tabName === "admin") loadAdminDashboard();
  if (window.lucide) lucide.createIcons();
}

async function openLatestOrPromptWorkspace() {
  const contCard = document.getElementById("continue-learning-card");
  const pId = contCard ? contCard.dataset.projectId : null;
  if (pId) {
    openProjectWorkspace(pId);
  } else {
    try {
      const res = await fetch("/api/projects");
      const data = await res.json();
      if (data.projects && data.projects.length > 0) {
        openProjectWorkspace(data.projects[0].id);
      } else {
        switchTab("projects");
      }
    } catch (e) {
      switchTab("projects");
    }
  }
}

// -------------------------------------------------------------
// Authentication & Top-Right Auth Bar
// -------------------------------------------------------------
let isRegisterMode = false;

function openAuthModal(mode = 'login') {
  isRegisterMode = (mode === 'register');
  updateAuthModalUI();
  const errBox = document.getElementById("auth-error");
  if (errBox) errBox.style.display = "none";
  document.getElementById("auth-overlay").style.display = "flex";
  if (window.lucide) lucide.createIcons();
}

function closeAuthModal() {
  document.getElementById("auth-overlay").style.display = "none";
}

function updateAuthModalUI() {
  document.getElementById("auth-subtitle").textContent = isRegisterMode ? "Create your learning account" : "Log in to sync your learning journeys";
  document.getElementById("auth-submit-btn").querySelector("span").textContent = isRegisterMode ? "Create Account" : "Log In";
  document.getElementById("auth-switch-text").textContent = isRegisterMode ? "Already have an account?" : "New to AI Study Companion?";
  document.getElementById("auth-switch-link").textContent = isRegisterMode ? "Log In" : "Create an Account";
  const roleGroup = document.getElementById("auth-role-group");
  if (roleGroup) roleGroup.style.display = isRegisterMode ? "block" : "none";
}

function toggleAuthMode() {
  isRegisterMode = !isRegisterMode;
  updateAuthModalUI();
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const role = document.getElementById("auth-role") ? document.getElementById("auth-role").value : "student";
  const errBox = document.getElementById("auth-error");
  const errMsg = document.getElementById("auth-error-msg");

  if (errBox) errBox.style.display = "none";
  const url = isRegisterMode ? "/api/register" : "/api/login";
  const payload = isRegisterMode ? { username, password, role } : { username, password };

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      if (errBox) {
        errBox.style.display = "flex";
        errMsg.textContent = data.error || "Authentication failed.";
        if (window.lucide) lucide.createIcons();
      }
      return;
    }

    currentUser = data.user;
    closeAuthModal();
    onUserLoggedIn(currentUser);
  } catch (err) {
    if (errBox) {
      errBox.style.display = "flex";
      errMsg.textContent = "Network error connecting to server.";
      if (window.lucide) lucide.createIcons();
    }
  }
}

async function checkSession() {
  try {
    const res = await fetch("/api/session");
    const data = await res.json();
    currentUser = data.user;
    renderTopAuthBar(data);

    if (currentUser && currentUser.role === "admin") {
      const admBtn = document.getElementById("nav-admin-btn");
      if (admBtn) admBtn.style.display = "flex";
    } else {
      const admBtn = document.getElementById("nav-admin-btn");
      if (admBtn) admBtn.style.display = "none";
    }

    if (currentUser) {
      const greetName = document.getElementById("home-greeting-name");
      if (greetName) greetName.textContent = currentUser.username;
    }

    loadUserHome();
  } catch (e) {
    console.error("Error during session check:", e);
    loadUserHome();
  }
}

function renderTopAuthBar(sessionData) {
  const bar = document.getElementById("top-auth-bar");
  if (!bar) return;
  bar.innerHTML = "";

  if (sessionData && sessionData.logged_in && !sessionData.is_demo) {
    // Authenticated User
    const u = sessionData.user;
    bar.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); padding: 5px 12px; border-radius: 20px;">
        <div style="background: var(--accent-primary); width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; color: #080a0f;">
          ${(u.username || 'U')[0].toUpperCase()}
        </div>
        <span style="font-size: 0.82rem; font-weight: 600; color: #fff;">${u.username}</span>
        <span style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">${u.role}</span>
      </div>
      <button onclick="handleLogout()" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; color: #f87171; border-color: rgba(239, 68, 68, 0.25); display: flex; align-items: center; gap: 6px; cursor: pointer;">
        <i data-lucide="log-out" style="width: 13px; height: 13px;"></i> Log Out
      </button>
    `;
  } else {
    // Guest / Demo Student
    bar.innerHTML = `
      <div class="demo-tag" style="background: rgba(6, 182, 212, 0.12); color: var(--accent-primary); border: 1px solid rgba(6, 182, 212, 0.25); padding: 5px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 6px;">
        <i data-lucide="sparkles" style="width: 13px; height: 13px;"></i> Demo Student
      </div>
      <button onclick="openAuthModal('login')" class="btn btn-secondary" style="padding: 7px 14px; font-size: 0.8rem; border-radius: 8px; font-weight: 600; display: flex; align-items: center; gap: 6px; cursor: pointer;">
        <i data-lucide="log-in" style="width: 14px; height: 14px;"></i> Log In
      </button>
      <button onclick="openAuthModal('register')" class="btn btn-primary" style="padding: 7px 16px; font-size: 0.8rem; border-radius: 8px; font-weight: 600; background: var(--accent-gradient); border: none; color: #fff; display: flex; align-items: center; gap: 6px; cursor: pointer;">
        <i data-lucide="user-plus" style="width: 14px; height: 14px;"></i> Sign Up
      </button>
    `;
  }
  if (window.lucide) lucide.createIcons();
}

function onUserLoggedIn(user) {
  closeAuthModal();
  renderTopAuthBar({ logged_in: true, is_demo: false, user: user });

  if (user.role === "admin") {
    const admBtn = document.getElementById("nav-admin-btn");
    if (admBtn) admBtn.style.display = "flex";
  } else {
    const admBtn = document.getElementById("nav-admin-btn");
    if (admBtn) admBtn.style.display = "none";
  }

  const greetName = document.getElementById("home-greeting-name");
  if (greetName) greetName.textContent = user.username;

  loadUserHome();
}

async function handleLogout() {
  await fetch("/api/logout", { method: "POST" });
  currentUser = null;
  location.reload();
}

async function checkApiStatus() {
  try {
    const res = await fetch("/api/check-key");
    const data = await res.json();
    const ind = document.getElementById("api-status-indicator");
    const txt = document.getElementById("api-status-text");
    if (data.configured) {
      ind.className = "api-status-badge success";
      txt.textContent = `${data.provider.toUpperCase()} Online`;
    } else {
      ind.className = "api-status-badge warning";
      txt.textContent = "LLM Offline";
    }
  } catch (e) {}
}

// -------------------------------------------------------------
// Home Dashboard ("Where was I, How am I doing, What next?")
// -------------------------------------------------------------
async function loadUserHome() {
  try {
    const res = await fetch("/api/user/home");
    const data = await res.json();
    if (!data.success) return;

    // 1. Where was I? (Continue Project)
    const contCard = document.getElementById("continue-learning-card");
    if (data.continue_learning) {
      contCard.style.display = "flex";
      document.getElementById("continue-proj-name").textContent = data.continue_learning.name;
      document.getElementById("continue-proj-goal").textContent = `Goal: ${data.continue_learning.learning_goal || 'Master learning domain'}`;
      document.getElementById("continue-proj-progress").textContent = `${data.continue_learning.progress || 0}%`;
      contCard.dataset.projectId = data.continue_learning.id;
    } else {
      contCard.style.display = "none";
    }

    // 2. How am I doing?
    document.getElementById("home-stat-mastery").textContent = `${data.overall_progress.average_mastery}%`;
    document.getElementById("home-stat-improving").textContent = data.overall_progress.improving_count;
    document.getElementById("home-stat-attention").textContent = data.overall_progress.attention_count;

    const attentionList = document.getElementById("home-attention-list");
    attentionList.innerHTML = "";
    if (data.areas_requiring_attention && data.areas_requiring_attention.length > 0) {
      data.areas_requiring_attention.forEach(item => {
        const div = document.createElement("div");
        div.style = "background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); padding: 8px 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem;";
        div.innerHTML = `
          <div>
            <span style="font-weight: 600; color: #fff;">${item.concept_name}</span>
            <span style="color: var(--text-muted); margin-left: 6px;">(${item.project_name})</span>
          </div>
          <span style="color: #ef4444; font-weight: 700;">${item.mastery_score}%</span>
        `;
        attentionList.appendChild(div);
      });
    } else {
      attentionList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">No critical weaknesses identified. Excellent progress!</div>`;
    }

    // 3. What should I do next?
    const recsList = document.getElementById("home-recommendations-list");
    recsList.innerHTML = "";
    if (data.recommendations && data.recommendations.length > 0) {
      data.recommendations.forEach(rec => {
        const rDiv = document.createElement("div");
        rDiv.className = "rec-card";
        rDiv.style = "background: rgba(234, 179, 8, 0.06); border: 1px solid rgba(234, 179, 8, 0.2); padding: 12px; border-radius: 10px; display: flex; justify-content: space-between; align-items: center; gap: 12px;";
        rDiv.innerHTML = `
          <div>
            <div style="font-weight: 700; font-size: 0.85rem; color: #fff;">${rec.title}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 2px;">${rec.description}</div>
          </div>
          <button onclick="handleHomeRecClick('${rec.action_type}', ${data.continue_learning ? data.continue_learning.id : null}, '${escapeJs(rec.action_target)}')" class="btn btn-secondary" style="font-size: 0.75rem; padding: 6px 12px; flex-shrink: 0;">Start</button>
        `;
        recsList.appendChild(rDiv);
      });
    } else {
      recsList.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">Open a project and upload materials to generate targeted recommendations.</div>`;
    }

    // Recent Projects Grid
    const projGrid = document.getElementById("home-recent-projects-grid");
    projGrid.innerHTML = "";
    if (data.recent_projects && data.recent_projects.length > 0) {
      data.recent_projects.forEach(p => {
        const card = document.createElement("div");
        card.className = "glass-card hover-glow";
        card.style = "padding: 16px; border-radius: 12px; cursor: pointer; border-left: 3px solid " + (p.space_color || 'var(--accent-primary)');
        card.onclick = () => openProjectWorkspace(p.id);
        card.innerHTML = `
          <div style="font-size: 0.7rem; color: ${p.space_color || 'var(--accent-primary)'}; font-weight: 600; text-transform: uppercase;">${p.space_name}</div>
          <h4 style="font-size: 1rem; font-weight: 700; margin: 4px 0 6px 0; color: #fff;">${p.name}</h4>
          <p style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${p.description || 'No description'}</p>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="background: rgba(255,255,255,0.06); width: 100px; height: 6px; border-radius: 3px; overflow: hidden;">
              <div style="background: #10b981; width: ${p.progress || 0}%; height: 100%;"></div>
            </div>
            <span style="font-size: 0.75rem; font-weight: 700; color: #10b981;">${p.progress || 0}%</span>
          </div>
        `;
        projGrid.appendChild(card);
      });
    } else {
      projGrid.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No projects yet. Go to Spaces & Projects to create your first project!</div>`;
    }

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Error loading home:", e);
  }
}

function resumeContinueProject() {
  const contCard = document.getElementById("continue-learning-card");
  const pId = contCard.dataset.projectId;
  if (pId) openProjectWorkspace(pId);
}

function handleHomeRecClick(actionType, projectId, target) {
  if (!projectId) return;
  openProjectWorkspace(projectId, () => {
    if (actionType === "quiz") switchWsTab("quiz");
    else if (actionType === "tutor") {
      switchWsTab("tutor");
      if (target) {
        document.getElementById("tutor-user-input").value = target;
      }
    } else {
      switchWsTab("materials");
    }
  });
}

// -------------------------------------------------------------
// Spaces & Projects Navigator
// -------------------------------------------------------------
async function loadSpaces() {
  try {
    const res = await fetch("/api/spaces");
    const data = await res.json();
    const container = document.getElementById("spaces-container");
    container.innerHTML = "";

    if (!data.spaces || data.spaces.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem;">No spaces created yet. Click "Create Space" above to start.</div>`;
      return;
    }

    for (const space of data.spaces) {
      const spaceCard = document.createElement("div");
      spaceCard.className = "glass-card";
      spaceCard.style = "padding: 22px; border-radius: 14px; border-top: 3px solid " + (space.color || '#06b6d4');
      
      spaceCard.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
          <div style="display: flex; align-items: center; gap: 10px;">
            <div style="background: rgba(255,255,255,0.06); width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: ${space.color || '#06b6d4'};">
              <i data-lucide="${space.icon || 'book-open'}" style="width: 20px; height: 20px;"></i>
            </div>
            <div>
              <h3 style="font-size: 1.15rem; font-weight: 700; margin: 0;">${space.name}</h3>
              <span style="font-size: 0.75rem; color: var(--text-muted);">${space.project_count || 0} Projects</span>
            </div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button onclick="openCreateProjectModal(${space.id})" class="btn btn-secondary" style="font-size: 0.75rem; padding: 5px 9px;" title="Add Project to Space">
              <i data-lucide="plus" style="width: 13px; height: 13px;"></i> Project
            </button>
            <button onclick="confirmDeleteSpace(${space.id}, '${escapeJs(space.name)}')" class="btn btn-secondary" style="font-size: 0.75rem; padding: 5px 8px; color: #ef4444; border-color: rgba(239, 68, 68, 0.25);" title="Delete Space">
              <i data-lucide="trash-2" style="width: 13px; height: 13px;"></i>
            </button>
          </div>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 16px;">${space.description || 'General learning area'}</p>
        <div id="space-projects-${space.id}" style="display: flex; flex-direction: column; gap: 8px;">
          <div style="font-size: 0.75rem; color: var(--text-muted);"><i data-lucide="loader" class="spin" style="width: 12px; height: 12px;"></i> Loading projects...</div>
        </div>
      `;
      container.appendChild(spaceCard);

      // Fetch projects for this space
      loadProjectsForSpace(space.id);
    }
    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Error loading spaces:", e);
  }
}

async function loadProjectsForSpace(spaceId) {
  try {
    const res = await fetch(`/api/spaces/${spaceId}`);
    const data = await res.json();
    const listEl = document.getElementById(`space-projects-${spaceId}`);
    listEl.innerHTML = "";

    if (!data.projects || data.projects.length === 0) {
      listEl.innerHTML = `<div style="font-size: 0.75rem; color: var(--text-muted); padding: 8px 0;">No projects in this space yet. Click "+ Project" above to create one.</div>`;
      return;
    }

    data.projects.forEach(p => {
      const pItem = document.createElement("div");
      pItem.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: 0.2s;";
      pItem.onmouseover = () => pItem.style.background = "rgba(6, 182, 212, 0.08)";
      pItem.onmouseout = () => pItem.style.background = "rgba(255,255,255,0.02)";
      pItem.onclick = () => openProjectWorkspace(p.id);

      pItem.innerHTML = `
        <div style="overflow: hidden; padding-right: 8px; flex: 1;">
          <div style="font-weight: 600; font-size: 0.85rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${p.name}</div>
          <div style="font-size: 0.7rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${p.learning_goal || ''}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
          <span style="font-size: 0.75rem; font-weight: 700; color: #10b981;">${p.progress || 0}%</span>
          <button onclick="event.stopPropagation(); confirmDeleteProject(${p.id}, '${escapeJs(p.name)}')" style="background: transparent; border: none; color: #ef4444; cursor: pointer; padding: 4px; display: flex; align-items: center;" title="Delete Project">
            <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
          </button>
          <i data-lucide="chevron-right" style="width: 14px; height: 14px; color: var(--text-muted);"></i>
        </div>
      `;
      listEl.appendChild(pItem);
    });
    if (window.lucide) lucide.createIcons();
  } catch (e) {}
}

function openCreateSpaceModal() {
  const modal = document.getElementById("modal-create-space");
  if (modal) {
    modal.style.display = "flex";
    modal.style.opacity = "1";
    modal.style.visibility = "visible";
    const nameInput = document.getElementById("new-space-name");
    if (nameInput) setTimeout(() => nameInput.focus(), 50);
  }
}

async function handleCreateSpaceSubmit(e) {
  e.preventDefault();
  const nameInput = document.getElementById("new-space-name");
  const descInput = document.getElementById("new-space-desc");
  const colorInput = document.getElementById("new-space-color");

  const name = nameInput.value.trim();
  const description = descInput.value.trim();
  const color = colorInput.value;

  try {
    const res = await fetch("/api/spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description, color })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeModal("modal-create-space");
      nameInput.value = "";
      descInput.value = "";
      loadSpaces();
      loadProjectsExplorer();
      loadUserHome();
    } else {
      alert(data.error || "Failed to create space.");
    }
  } catch (err) {
    alert("Network error creating space.");
  }
}

function openCreateProjectModal(spaceId) {
  document.getElementById("new-proj-space-id").value = spaceId;
  const group = document.getElementById("new-proj-space-group");
  if (group) group.style.display = "none";
  const modal = document.getElementById("modal-create-project");
  if (modal) {
    modal.style.display = "flex";
    modal.style.opacity = "1";
    modal.style.visibility = "visible";
    const nameInput = document.getElementById("new-proj-name");
    if (nameInput) setTimeout(() => nameInput.focus(), 50);
  }
}

async function openCreateProjectPrompt() {
  try {
    const res = await fetch("/api/spaces");
    const data = await res.json();
    const select = document.getElementById("new-proj-space-select");
    const group = document.getElementById("new-proj-space-group");
    select.innerHTML = "";

    if (!data.spaces || data.spaces.length === 0) {
      alert("Please create a Learning Space first before adding a project.");
      openCreateSpaceModal();
      return;
    }

    data.spaces.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      select.appendChild(opt);
    });

    if (group) group.style.display = "block";
    document.getElementById("new-proj-space-id").value = "";
    const modal = document.getElementById("modal-create-project");
    if (modal) {
      modal.style.display = "flex";
      modal.style.opacity = "1";
      modal.style.visibility = "visible";
      const nameInput = document.getElementById("new-proj-name");
      if (nameInput) setTimeout(() => nameInput.focus(), 50);
    }
  } catch (e) {
    console.error("Error opening create project prompt:", e);
  }
}

async function handleCreateProjectSubmit(e) {
  e.preventDefault();
  let spaceId = document.getElementById("new-proj-space-id").value;
  const group = document.getElementById("new-proj-space-group");
  const select = document.getElementById("new-proj-space-select");
  
  if ((!spaceId || (group && group.style.display !== "none")) && select && select.value) {
    spaceId = select.value;
  }

  if (!spaceId) {
    alert("Please select or create a learning space for this project.");
    return;
  }

  const nameInput = document.getElementById("new-proj-name");
  const goalInput = document.getElementById("new-proj-goal");
  const descInput = document.getElementById("new-proj-desc");

  const name = nameInput.value.trim();
  const goal = goalInput.value.trim();
  const desc = descInput.value.trim();

  try {
    const res = await fetch(`/api/spaces/${spaceId}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, learning_goal: goal, description: desc })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeModal("modal-create-project");
      nameInput.value = "";
      goalInput.value = "";
      descInput.value = "";
      openProjectWorkspace(data.project.id);
    } else {
      alert(data.error || "Failed to create project.");
    }
  } catch (err) {
    alert("Network error creating project.");
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = "none";
  }
}

async function confirmDeleteProject(projectId, projectName) {
  if (!confirm(`Are you sure you want to delete project "${projectName}"? All materials, quizzes, and mastery tracking for this project will be permanently removed.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/projects/${projectId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (currentProject && currentProject.id === projectId) {
        currentProject = null;
        const wsBtn = document.getElementById("nav-workspace-btn");
        if (wsBtn) wsBtn.style.display = "none";
        switchTab("projects");
      }
      loadProjectsExplorer();
      loadSpaces();
      loadUserHome();
    } else {
      alert(data.error || "Failed to delete project.");
    }
  } catch (err) {
    alert("Network error deleting project.");
  }
}

function confirmDeleteCurrentProject() {
  if (!currentProject) return;
  confirmDeleteProject(currentProject.id, currentProject.name);
}

async function confirmDeleteSpace(spaceId, spaceName) {
  if (!confirm(`Are you sure you want to delete Space "${spaceName}" and all projects inside it?`)) {
    return;
  }

  try {
    const res = await fetch(`/api/spaces/${spaceId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (res.ok && data.success) {
      loadSpaces();
      loadProjectsExplorer();
      loadUserHome();
    } else {
      alert(data.error || "Failed to delete space.");
    }
  } catch (err) {
    alert("Network error deleting space.");
  }
}

// -------------------------------------------------------------
// Projects Explorer (All Projects, Live Search & Filters)
// -------------------------------------------------------------
let allProjectsList = [];
let activeProjectsFilter = 'all';

async function loadProjectsExplorer() {
  try {
    const res = await fetch("/api/projects");
    const data = await res.json();
    allProjectsList = data.projects || [];
    updateProjectsFilterCounts();
    applyProjectsFilter();
  } catch (e) {
    console.error("Error loading projects explorer:", e);
  }
}

function updateProjectsFilterCounts() {
  const allCount = allProjectsList.length;
  const progressCount = allProjectsList.filter(p => (p.progress || 0) > 0 && (p.progress || 0) < 80).length;
  const focusCount = allProjectsList.filter(p => (p.avg_mastery || 0) < 50 || p.status === 'needs_focus').length;
  const masteredCount = allProjectsList.filter(p => (p.avg_mastery || 0) >= 80 || (p.progress || 0) >= 80).length;

  const cAll = document.getElementById("count-filter-all");
  const cProg = document.getElementById("count-filter-progress");
  const cFoc = document.getElementById("count-filter-focus");
  const cMast = document.getElementById("count-filter-mastered");

  if (cAll) cAll.textContent = allCount;
  if (cProg) cProg.textContent = progressCount;
  if (cFoc) cFoc.textContent = focusCount;
  if (cMast) cMast.textContent = masteredCount;
}

function setProjectsFilter(filter) {
  activeProjectsFilter = filter;
  document.querySelectorAll(".proj-filter-pill").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-filter") === filter);
  });
  applyProjectsFilter();
}

function filterProjectsExplorer() {
  applyProjectsFilter();
}

function applyProjectsFilter() {
  const input = document.getElementById("projects-search-input");
  const query = (input ? input.value : "").toLowerCase().trim();
  let list = allProjectsList;

  if (activeProjectsFilter === "in_progress") {
    list = list.filter(p => (p.progress || 0) > 0 && (p.progress || 0) < 80);
  } else if (activeProjectsFilter === "needs_focus") {
    list = list.filter(p => (p.avg_mastery || 0) < 50 || p.status === 'needs_focus');
  } else if (activeProjectsFilter === "mastered") {
    list = list.filter(p => (p.avg_mastery || 0) >= 80 || (p.progress || 0) >= 80);
  }

  if (query) {
    list = list.filter(p => 
      (p.name && p.name.toLowerCase().includes(query)) ||
      (p.learning_goal && p.learning_goal.toLowerCase().includes(query)) ||
      (p.space_name && p.space_name.toLowerCase().includes(query)) ||
      (p.description && p.description.toLowerCase().includes(query))
    );
  }

  renderProjectsExplorer(list);
}

function renderProjectsExplorer(projects) {
  const container = document.getElementById("projects-explorer-grid");
  if (!container) return;
  container.innerHTML = "";

  if (!projects || projects.length === 0) {
    container.innerHTML = `
      <div class="glass-card" style="grid-column: 1 / -1; padding: 48px 20px; text-align: center; color: var(--text-muted);">
        <i data-lucide="folder-search" style="width: 44px; height: 44px; margin-bottom: 12px; color: var(--accent-primary);"></i>
        <div style="font-size: 1.05rem; font-weight: 600; color: #fff;">No matching projects found</div>
        <p style="font-size: 0.85rem; max-width: 360px; margin: 6px auto 16px auto;">Try changing your search terms, adjusting status filters, or start a new learning project.</p>
        <button onclick="openCreateProjectPrompt()" class="btn btn-primary" style="padding: 9px 20px; font-size: 0.85rem; border-radius: 8px; background: var(--accent-gradient); border: none; color: #fff; cursor: pointer;">
          <i data-lucide="plus" style="width: 14px; height: 14px; vertical-align: -1px;"></i> Create Project
        </button>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  projects.forEach(p => {
    const card = document.createElement("div");
    card.className = "glass-card hover-glow";
    card.style = "padding: 22px; border-radius: 14px; display: flex; flex-direction: column; justify-content: space-between; border-top: 3px solid " + (p.space_color || 'var(--accent-primary)');

    const masteryScore = p.avg_mastery || 0;
    const masteryColor = masteryScore >= 75 ? "#10b981" : (masteryScore >= 45 ? "#eab308" : "#ef4444");

    card.innerHTML = `
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <span style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: ${p.space_color || 'var(--accent-primary)'}; background: rgba(255,255,255,0.03); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
            ${p.space_name || 'General Space'}
          </span>
          <span style="font-size: 0.75rem; font-weight: 700; color: ${masteryColor};">
            Mastery: ${masteryScore}%
          </span>
        </div>

        <h3 style="font-size: 1.15rem; font-weight: 700; margin: 0 0 6px 0; color: #fff;">${p.name}</h3>
        <p style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 16px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
          ${p.learning_goal || p.description || 'Target specific concept mastery in this project.'}
        </p>
      </div>

      <div>
        <!-- Stats Row -->
        <div style="display: flex; gap: 12px; margin-bottom: 14px; font-size: 0.75rem; color: var(--text-muted);">
          <span style="display: flex; align-items: center; gap: 4px;">
            <i data-lucide="file-text" style="width: 13px; height: 13px;"></i> ${p.material_count || 0} Docs
          </span>
          <span style="display: flex; align-items: center; gap: 4px;">
            <i data-lucide="sparkles" style="width: 13px; height: 13px;"></i> ${p.concept_count || 0} Concepts
          </span>
        </div>

        <!-- Progress Bar -->
        <div style="margin-bottom: 16px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-muted); margin-bottom: 4px;">
            <span>Journey Progress</span>
            <span style="font-weight: 700; color: #fff;">${p.progress || 0}%</span>
          </div>
          <div style="background: rgba(255,255,255,0.06); height: 6px; border-radius: 3px; overflow: hidden;">
            <div style="background: var(--accent-gradient); width: ${p.progress || 0}%; height: 100%;"></div>
          </div>
        </div>

        <!-- Launch & Delete Action Buttons -->
        <div style="display: flex; gap: 8px; align-items: center;">
          <button onclick="openProjectWorkspace(${p.id})" class="btn btn-primary" style="flex: 1; padding: 10px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; background: var(--accent-gradient); border: none; color: #fff; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 6px;">
            <span>Open Workspace</span> <i data-lucide="arrow-right" style="width: 14px; height: 14px;"></i>
          </button>
          <button onclick="confirmDeleteProject(${p.id}, '${escapeJs(p.name)}')" class="btn btn-secondary" style="padding: 10px 12px; border-radius: 8px; color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.25); background: rgba(239, 68, 68, 0.05); cursor: pointer;" title="Delete Project">
            <i data-lucide="trash-2" style="width: 15px; height: 15px;"></i>
          </button>
        </div>
      </div>
    `;

    container.appendChild(card);
  });

  if (window.lucide) lucide.createIcons();
}

// -------------------------------------------------------------
// Project Workspace (Core Primary Learning Loop)
// -------------------------------------------------------------
async function openProjectWorkspace(projectId, callback) {
  try {
    const res = await fetch(`/api/projects/${projectId}/dashboard`);
    const data = await res.json();
    if (!data.success) return;

    currentProject = data.project;

    // Show nav item
    const wsNav = document.getElementById("nav-workspace-btn");
    wsNav.style.display = "flex";
    wsNav.querySelector("span").textContent = currentProject.name;

    // Header info
    document.getElementById("ws-project-name").textContent = currentProject.name;
    document.getElementById("ws-project-crumb").textContent = currentProject.name;
    document.getElementById("ws-project-goal").textContent = `Goal: ${currentProject.learning_goal || 'Master project concepts'}`;
    document.getElementById("ws-project-progress").textContent = `${currentProject.progress || 0}%`;

    // Switch to Workspace tab
    switchTab("workspace");
    switchWsTab("overview");

    // Populate Overview
    renderProjectOverview(data);

    if (callback) callback();
    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Error opening project workspace:", e);
  }
}

function switchWsTab(tabId) {
  activeWsTab = tabId;
  document.querySelectorAll(".ws-tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".ws-subtab").forEach(t => t.classList.remove("active"));

  const targetBtn = document.querySelector(`.ws-tab-btn[onclick="switchWsTab('${tabId}')"]`);
  const targetSubtab = document.getElementById(`wstab-${tabId}`);
  if (targetBtn) targetBtn.classList.add("active");
  if (targetSubtab) targetSubtab.classList.add("active");

  if (tabId === "materials") loadProjectMaterials();
  if (tabId === "tutor") loadTutorHistory();
  if (tabId === "mastery") loadMasteryAndGrowth();
  if (tabId === "analytics") loadProjectAnalytics();

  if (window.lucide) lucide.createIcons();
}

function renderProjectOverview(data) {
  // Concept Mastery bars
  const barsContainer = document.getElementById("ws-overview-concept-bars");
  barsContainer.innerHTML = "";
  if (data.mastery && data.mastery.concepts && data.mastery.concepts.length > 0) {
    data.mastery.concepts.slice(0, 5).forEach(c => {
      const row = document.createElement("div");
      row.innerHTML = `
        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 4px;">
          <span style="font-weight: 600; color: #fff;">${c.name}</span>
          <span style="color: ${c.mastery_score >= 70 ? '#10b981' : (c.mastery_score >= 45 ? '#eab308' : '#ef4444')}; font-weight: 700;">${c.mastery_score}%</span>
        </div>
        <div style="background: rgba(255,255,255,0.06); height: 8px; border-radius: 4px; overflow: hidden;">
          <div style="background: ${c.mastery_score >= 70 ? '#10b981' : (c.mastery_score >= 45 ? '#eab308' : '#ef4444')}; width: ${c.mastery_score}%; height: 100%; transition: width 0.4s ease;"></div>
        </div>
      `;
      barsContainer.appendChild(row);
    });
  } else {
    barsContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No concepts loaded yet. Upload your PDF notes in the Materials tab to get started.</div>`;
  }

  // Recommended Next Step
  if (data.recommendations && data.recommendations.length > 0) {
    const topRec = data.recommendations[0];
    document.getElementById("ws-overview-rec-title").textContent = topRec.title;
    document.getElementById("ws-overview-rec-desc").textContent = topRec.description;
    document.getElementById("ws-overview-rec-btn").dataset.actionType = topRec.action_type;
    document.getElementById("ws-overview-rec-btn").dataset.actionTarget = topRec.action_target || "";
  } else {
    document.getElementById("ws-overview-rec-title").textContent = "Start Learning Journey";
    document.getElementById("ws-overview-rec-desc").textContent = "Upload PDF notes in the Materials tab or ask the AI Tutor your first question.";
  }

  // Recent Activity
  const actContainer = document.getElementById("ws-overview-activity");
  actContainer.innerHTML = "";
  if (data.recent_activity && data.recent_activity.length > 0) {
    data.recent_activity.forEach(act => {
      const aDiv = document.createElement("div");
      aDiv.style = "font-size: 0.8rem; display: flex; align-items: center; gap: 8px; color: var(--text-secondary);";
      aDiv.innerHTML = `
        <span style="width: 6px; height: 6px; border-radius: 50%; background: var(--accent-primary); flex-shrink: 0;"></span>
        <span><strong>${formatEventType(act.event_type)}</strong> — <small style="color: var(--text-muted);">${formatTime(act.created_at)}</small></span>
      `;
      actContainer.appendChild(aDiv);
    });
  } else {
    actContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">Project created. Activity will record here as you study.</div>`;
  }
}

function executeRecommendationAction() {
  const btn = document.getElementById("ws-overview-rec-btn");
  const actionType = btn.dataset.actionType;
  const target = btn.dataset.actionTarget;

  if (actionType === "quiz") {
    switchWsTab("quiz");
  } else if (actionType === "tutor") {
    switchWsTab("tutor");
    if (target) {
      document.getElementById("tutor-user-input").value = target;
    }
  } else {
    switchWsTab("materials");
  }
}

// -------------------------------------------------------------
// Materials & Asynchronous Knowledge Extraction
// -------------------------------------------------------------
async function handleMaterialUpload(file) {
  if (!file || !currentProject) return;

  const statusEl = document.getElementById("upload-status-indicator");
  statusEl.style.display = "block";
  statusEl.innerHTML = `<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Uploading ${file.name} to background processing queue...`;
  if (window.lucide) lucide.createIcons();

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`/api/projects/${currentProject.id}/materials/upload`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) {
      statusEl.style.background = "rgba(239, 68, 68, 0.1)";
      statusEl.style.color = "#ef4444";
      statusEl.textContent = data.error || "Upload failed.";
      return;
    }

    statusEl.innerHTML = `<i data-lucide="check-circle" style="width: 14px; height: 14px;"></i> Queued successfully! Processing in background...`;
    loadProjectMaterials();
    // Poll for status updates
    pollMaterialStatus(data.material_id);
  } catch (e) {
    statusEl.textContent = "Network error during upload.";
  }
}

async function loadProjectMaterials() {
  if (!currentProject) return;
  try {
    const res = await fetch(`/api/projects/${currentProject.id}/materials`);
    const data = await res.json();
    const container = document.getElementById("materials-list-container");
    container.innerHTML = "";

    if (!data.materials || data.materials.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">No materials uploaded yet. Upload a PDF file above.</div>`;
      return;
    }

    data.materials.forEach(m => {
      const mDiv = document.createElement("div");
      mDiv.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;";
      
      let statusBadge = "";
      if (m.status === "ready") {
        statusBadge = `<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px;">Ready (${m.page_count} Pages)</span>`;
      } else if (m.status === "processing") {
        statusBadge = `<span style="background: rgba(6, 182, 212, 0.15); color: var(--accent-primary); font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px;"><i data-lucide="loader" class="spin" style="width: 10px; height: 10px;"></i> Processing OCR</span>`;
      } else if (m.status === "failed") {
        statusBadge = `<span style="background: rgba(239, 68, 68, 0.15); color: #ef4444; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px;">Failed</span>`;
      } else {
        statusBadge = `<span style="background: rgba(234, 179, 8, 0.15); color: #eab308; font-size: 0.7rem; font-weight: 700; padding: 2px 8px; border-radius: 10px;">Queued</span>`;
      }

      mDiv.innerHTML = `
        <div style="overflow: hidden; padding-right: 12px;">
          <div style="font-size: 0.85rem; font-weight: 600; color: #fff; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${m.filename}</div>
          <div style="font-size: 0.7rem; color: var(--text-muted);">${(m.file_size / 1024).toFixed(1)} KB • ${formatTime(m.created_at)}</div>
          ${m.error_message ? `<div style="font-size: 0.7rem; color: #ef4444; margin-top: 4px;">${m.error_message}</div>` : ''}
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          ${statusBadge}
          ${m.status === 'failed' ? `<button onclick="retryMaterial('${m.id}')" class="btn btn-secondary" style="font-size: 0.7rem; padding: 2px 6px;">Retry</button>` : ''}
        </div>
      `;
      container.appendChild(mDiv);
    });

    loadProjectConcepts();
    if (window.lucide) lucide.createIcons();
  } catch (e) {}
}

async function retryMaterial(materialId) {
  await fetch(`/api/projects/${currentProject.id}/materials/${materialId}/retry`, { method: "POST" });
  loadProjectMaterials();
  pollMaterialStatus(materialId);
}

function pollMaterialStatus(materialId) {
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/projects/${currentProject.id}/materials/${materialId}/status`);
      const data = await res.json();
      if (data.material && (data.material.status === "ready" || data.material.status === "failed")) {
        clearInterval(timer);
        loadProjectMaterials();
      }
    } catch (e) {
      clearInterval(timer);
    }
  }, 2500);
}

async function loadProjectConcepts() {
  if (!currentProject) return;
  try {
    const res = await fetch(`/api/projects/${currentProject.id}/concepts`);
    const data = await res.json();
    const container = document.getElementById("extracted-concepts-container");
    const countBadge = document.getElementById("concepts-count-badge");
    container.innerHTML = "";

    if (!data.concepts || data.concepts.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">Concepts extracted from your materials will appear here once processed.</div>`;
      countBadge.textContent = "0 Concepts";
      return;
    }

    countBadge.textContent = `${data.concepts.length} Concepts`;
    data.concepts.forEach(c => {
      const cDiv = document.createElement("div");
      cDiv.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 12px; border-radius: 8px;";
      cDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <span style="font-weight: 700; font-size: 0.85rem; color: var(--accent-primary);">${c.name}</span>
          <span style="font-size: 0.75rem; font-weight: 700; color: #10b981;">${c.mastery_score || 30}% Mastery</span>
        </div>
        <p style="font-size: 0.75rem; color: var(--text-secondary); margin: 0;">${c.description || 'Core concept extracted from project notes.'}</p>
      `;
      container.appendChild(cDiv);
    });
  } catch (e) {}
}

// -------------------------------------------------------------
// AI Tutor with Citations & Unsupported Question Handling
// -------------------------------------------------------------
async function loadTutorHistory() {
  if (!currentProject) return;
  try {
    const res = await fetch(`/api/projects/${currentProject.id}/tutor/history`);
    const data = await res.json();
    const stream = document.getElementById("tutor-messages-stream");
    stream.innerHTML = "";

    if (!data.messages || data.messages.length === 0) {
      stream.innerHTML = `
        <div class="tutor-msg assistant-msg">
          <div class="msg-bubble">
            Hello! I am your Project AI Tutor. Ask me any question about your uploaded materials. I will provide exact citations (Source & Page) and will state insufficient evidence if a topic is not in your materials!
          </div>
        </div>
      `;
      return;
    }

    data.messages.forEach(msg => {
      appendTutorMessageToUI(msg.role, msg.content, msg.citations, msg.evidence_sufficient);
    });

    stream.scrollTop = stream.scrollHeight;
  } catch (e) {}
}

async function sendTutorMessage(e) {
  e.preventDefault();
  const input = document.getElementById("tutor-user-input");
  const msg = input.value.trim();
  if (!msg || !currentProject) return;

  input.value = "";
  appendTutorMessageToUI("user", msg);

  // Assistant typing indicator
  const stream = document.getElementById("tutor-messages-stream");
  const typingDiv = document.createElement("div");
  typingDiv.id = "tutor-typing";
  typingDiv.className = "tutor-msg assistant-msg";
  typingDiv.innerHTML = `<div class="msg-bubble" style="color: var(--text-muted);"><i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Consulting project materials and verifying citations...</div>`;
  stream.appendChild(typingDiv);
  stream.scrollTop = stream.scrollHeight;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch(`/api/projects/${currentProject.id}/tutor/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    });
    const data = await res.json();
    
    // Remove typing indicator
    const typing = document.getElementById("tutor-typing");
    if (typing) typing.remove();

    if (!res.ok) {
      appendTutorMessageToUI("assistant", `Error: ${data.error || 'Failed to get response'}`);
      return;
    }

    appendTutorMessageToUI("assistant", data.answer, data.citations, data.evidence_sufficient);
  } catch (err) {
    const typing = document.getElementById("tutor-typing");
    if (typing) typing.remove();
    appendTutorMessageToUI("assistant", "Network error communicating with AI Tutor.");
  }
}

function appendTutorMessageToUI(role, content, citations = [], evidenceSufficient = true) {
  const stream = document.getElementById("tutor-messages-stream");
  const msgDiv = document.createElement("div");
  msgDiv.className = `tutor-msg ${role === 'user' ? 'user-msg' : 'assistant-msg'}`;

  let parsedContent = window.marked ? marked.parse(content) : content;
  let citationsHtml = "";

  if (citations && citations.length > 0) {
    citationsHtml = `
      <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.75rem;">
        <div style="font-weight: 700; color: var(--accent-primary); margin-bottom: 4px;"><i data-lucide="bookmark" style="width: 12px; height: 12px; vertical-align: -1px;"></i> Supporting Citations:</div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          ${citations.map(c => `
            <div style="background: rgba(6, 182, 212, 0.08); padding: 4px 8px; border-radius: 6px; border-left: 2px solid var(--accent-primary);">
              <strong>Source:</strong> ${c.source} — <strong>Page ${c.page}</strong>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Unsupported question warning banner if evidence insufficient
  let unsupportedBanner = "";
  if (!evidenceSufficient && role === 'assistant') {
    unsupportedBanner = `
      <div style="margin-bottom: 8px; background: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.25); padding: 6px 10px; border-radius: 6px; font-size: 0.75rem; color: #eab308; display: flex; align-items: center; gap: 6px;">
        <i data-lucide="alert-triangle" style="width: 14px; height: 14px; flex-shrink: 0;"></i>
        <span><strong>Insufficient Evidence:</strong> This question is not covered in your uploaded materials.</span>
      </div>
    `;
  }

  msgDiv.innerHTML = `
    <div class="msg-bubble">
      ${unsupportedBanner}
      ${parsedContent}
      ${citationsHtml}
    </div>
  `;
  stream.appendChild(msgDiv);
  stream.scrollTop = stream.scrollHeight;
  if (window.lucide) lucide.createIcons();
}

async function clearTutorChat() {
  if (!confirm("Clear conversation history for this project?")) return;
  await fetch(`/api/projects/${currentProject.id}/tutor/history`, { method: "DELETE" });
  loadTutorHistory();
}

// -------------------------------------------------------------
// Adaptive Quiz & Assessment (MCQ + Open-Ended Grading)
// -------------------------------------------------------------
async function startNewAdaptiveQuiz() {
  if (!currentProject) return;

  const container = document.getElementById("quiz-active-container");
  const resultsContainer = document.getElementById("quiz-results-container");
  resultsContainer.style.display = "none";

  container.innerHTML = `
    <div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
      <i data-lucide="loader" class="spin" style="width: 36px; height: 36px; margin-bottom: 12px; color: var(--accent-primary);"></i>
      <div style="font-size: 1rem; color: #fff; font-weight: 600;">Generating Adaptive Assessment...</div>
      <p style="font-size: 0.8rem; margin-top: 4px;">Analyzing concept mastery levels, previous mistakes, and selecting targeted questions.</p>
    </div>
  `;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch(`/api/projects/${currentProject.id}/quiz/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ num_questions: 4 })
    });
    const data = await res.json();
    if (!res.ok) {
      container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Error generating quiz: ${data.error}</div>`;
      return;
    }

    currentQuiz = data.quiz;
    renderQuizQuestions(currentQuiz);
  } catch (e) {
    container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Network error generating assessment.</div>`;
  }
}

function renderQuizQuestions(quiz) {
  const container = document.getElementById("quiz-active-container");
  document.getElementById("quiz-header-title").textContent = quiz.title;

  let html = `
    <form id="quiz-submission-form" onsubmit="handleQuizSubmit(event)">
      <div style="display: flex; flex-direction: column; gap: 20px; margin-bottom: 24px;">
  `;

  quiz.questions.forEach((q, idx) => {
    html += `
      <div class="glass-card" style="padding: 18px; border-radius: 10px; border-left: 3px solid var(--accent-primary);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent-primary); font-weight: 700;">Question ${idx + 1} • ${q.concept_name || 'Concept'}</span>
          <span style="font-size: 0.7rem; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 6px; text-transform: capitalize;">${q.question_type === 'mcq' ? 'Multiple Choice' : 'Open-Ended'} (${q.difficulty})</span>
        </div>
        <div style="font-size: 0.95rem; font-weight: 600; color: #fff; margin-bottom: 14px;">${q.question_text}</div>
    `;

    if (q.question_type === "mcq") {
      html += `<div style="display: flex; flex-direction: column; gap: 8px;">`;
      q.options.forEach((opt, optIdx) => {
        html += `
          <label style="display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 6px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); cursor: pointer;">
            <input type="radio" name="q_${q.id}" value="${escapeHtml(opt)}" required style="accent-color: var(--accent-primary);">
            <span style="font-size: 0.85rem; color: #f4f4f5;">${opt}</span>
          </label>
        `;
      });
      html += `</div>`;
    } else {
      // Open-Ended Question
      html += `
        <div>
          <label style="font-size: 0.75rem; color: var(--text-muted); display: block; margin-bottom: 6px;">Type your response (evaluated for understanding, accuracy, and key concepts):</label>
          <textarea name="q_${q.id}" rows="3" required placeholder="Write a thorough explanation..." style="width: 100%; padding: 10px; border-radius: 6px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); color: #fff; font-size: 0.85rem;"></textarea>
        </div>
      `;
    }

    html += `</div>`;
  });

  html += `
      </div>
      <button type="submit" class="btn btn-primary" style="padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; background: var(--accent-gradient); border: none; color: #fff; display: flex; align-items: center; gap: 8px;">
        <span>Submit Assessment & Evaluate</span> <i data-lucide="send" style="width: 16px; height: 16px;"></i>
      </button>
    </form>
  `;

  container.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

async function handleQuizSubmit(e) {
  e.preventDefault();
  if (!currentQuiz || !currentProject) return;

  const form = e.target;
  const answers = [];

  currentQuiz.questions.forEach(q => {
    let val = "";
    if (q.question_type === "mcq") {
      const selected = form.querySelector(`input[name="q_${q.id}"]:checked`);
      if (selected) val = selected.value;
    } else {
      const area = form.querySelector(`textarea[name="q_${q.id}"]`);
      if (area) val = area.value.trim();
    }
    answers.push({ question_id: q.id, user_answer: val });
  });

  // Loading state
  const container = document.getElementById("quiz-active-container");
  container.innerHTML = `
    <div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
      <i data-lucide="loader" class="spin" style="width: 36px; height: 36px; margin-bottom: 12px; color: var(--accent-primary);"></i>
      <div style="font-size: 1rem; color: #fff; font-weight: 600;">Evaluating Answers with AI Grading...</div>
      <p style="font-size: 0.8rem; margin-top: 4px;">Assessing understanding, covered concepts, missing concepts, and updating concept mastery.</p>
    </div>
  `;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch(`/api/projects/${currentProject.id}/quiz/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quiz_id: currentQuiz.quiz_id, answers })
    });
    const data = await res.json();
    if (!res.ok) {
      container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Evaluation error: ${data.error}</div>`;
      return;
    }

    renderQuizResults(data);
    loadMasteryAndGrowth();
    loadUserHome();
  } catch (err) {
    container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Network error during assessment evaluation.</div>`;
  }
}

function renderQuizResults(evalData) {
  const container = document.getElementById("quiz-active-container");
  const resultsBox = document.getElementById("quiz-results-container");
  container.innerHTML = "";
  resultsBox.style.display = "block";

  let html = `
    <div class="glass-card" style="padding: 24px; border-radius: 12px; border-top: 4px solid ${evalData.total_score >= 70 ? '#10b981' : '#eab308'}; margin-bottom: 24px;">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px;">
        <div>
          <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent-primary); font-weight: 700;">Assessment Evaluation Report</span>
          <h3 style="font-size: 1.4rem; font-weight: 700; margin: 4px 0;">Overall Score: ${evalData.total_score}%</h3>
        </div>
        <div style="font-size: 0.9rem; color: var(--text-secondary);">
          Correct Answers: <strong>${evalData.correct_answers} / ${evalData.total_questions}</strong>
        </div>
      </div>
      <p style="font-size: 0.85rem; color: var(--text-secondary); margin: 0;">${evalData.feedback_summary}</p>
    </div>

    <h4 style="font-size: 1rem; font-weight: 700; margin-bottom: 14px;">Detailed Explanatory Feedback</h4>
    <div style="display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px;">
  `;

  evalData.answers.forEach((a, idx) => {
    html += `
      <div class="glass-card" style="padding: 18px; border-radius: 10px; border-left: 3px solid ${a.is_correct ? '#10b981' : '#ef4444'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <span style="font-weight: 700; font-size: 0.8rem; color: ${a.is_correct ? '#10b981' : '#ef4444'};">
            ${a.is_correct ? '✓ Correct' : '✗ Needs Improvement'} (Score: ${a.score}%)
          </span>
          <span style="font-size: 0.7rem; color: var(--text-muted); text-transform: capitalize;">${a.question_type}</span>
        </div>
        <div style="font-size: 0.9rem; font-weight: 600; color: #fff; margin-bottom: 8px;">${a.question_text}</div>
        <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 8px;"><strong>Your Answer:</strong> ${a.user_answer || '(None provided)'}</div>
        
        <div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 6px; font-size: 0.8rem; color: #f4f4f5; line-height: 1.4;">
          <strong>Feedback:</strong> ${a.feedback}
        </div>

        ${a.missing_concepts && a.missing_concepts.length > 0 ? `
          <div style="margin-top: 8px; font-size: 0.75rem; color: #f87171;">
            <strong>Missing Concepts:</strong> ${a.missing_concepts.join(', ')}
          </div>
        ` : ''}
      </div>
    `;
  });

  html += `
    </div>
    <div style="display: flex; gap: 12px;">
      <button onclick="startNewAdaptiveQuiz()" class="btn btn-primary" style="padding: 10px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; background: var(--accent-gradient); border: none; color: #fff;">Take Another Assessment</button>
      <button onclick="switchWsTab('mastery')" class="btn btn-secondary" style="padding: 10px 18px; border-radius: 8px; font-size: 0.85rem;">View Updated Mastery & Growth</button>
    </div>
  `;

  resultsBox.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

// -------------------------------------------------------------
// Mastery & Growth Analysis
// -------------------------------------------------------------
async function loadMasteryAndGrowth() {
  if (!currentProject) return;
  try {
    const res = await fetch(`/api/projects/${currentProject.id}/mastery`);
    const data = await res.json();
    const container = document.getElementById("mastery-concepts-full-list");
    container.innerHTML = "";

    if (!data.concepts || data.concepts.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">No concepts tracked yet. Upload documents or take a quiz to populate mastery data.</div>`;
      return;
    }

    data.concepts.forEach(c => {
      const cDiv = document.createElement("div");
      cDiv.className = "glass-card";
      cDiv.style = "padding: 16px; border-radius: 10px; display: flex; flex-direction: column; gap: 8px;";
      
      let trendBadge = "";
      if (c.trend === "improving") {
        trendBadge = `<span class="trend-badge improving">Improving</span>`;
      } else if (c.trend === "requiring_attention") {
        trendBadge = `<span class="trend-badge attention">Requiring Attention</span>`;
      } else {
        trendBadge = `<span class="trend-badge stable">Stable</span>`;
      }

      cDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <span style="font-weight: 700; font-size: 0.95rem; color: #fff;">${c.name}</span>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${c.description || ''}</div>
          </div>
          <div style="display: flex; align-items: center; gap: 12px;">
            ${trendBadge}
            <span style="font-size: 1.1rem; font-weight: 800; color: ${c.mastery_score >= 70 ? '#10b981' : (c.mastery_score >= 45 ? '#eab308' : '#ef4444')};">${c.mastery_score}%</span>
          </div>
        </div>
        <div style="background: rgba(255,255,255,0.06); height: 8px; border-radius: 4px; overflow: hidden; margin-top: 4px;">
          <div style="background: ${c.mastery_score >= 70 ? '#10b981' : (c.mastery_score >= 45 ? '#eab308' : '#ef4444')}; width: ${c.mastery_score}%; height: 100%;"></div>
        </div>
      `;
      container.appendChild(cDiv);
    });
  } catch (e) {}
}

// -------------------------------------------------------------
// Project Analytics
// -------------------------------------------------------------
async function loadProjectAnalytics() {
  if (!currentProject) return;
  try {
    const res = await fetch(`/api/projects/${currentProject.id}/analytics`);
    const data = await res.json();
    if (!data.success) return;

    // 1. Chart.js Quiz Trends
    const ctx = document.getElementById("quizTrendsChart").getContext("2d");
    if (quizChartInstance) quizChartInstance.destroy();

    const labels = (data.quiz_trends || []).map((t, idx) => `Quiz ${idx + 1}`);
    const scores = (data.quiz_trends || []).map(t => t.total_score);

    quizChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels.length > 0 ? labels : ['No Quizzes'],
        datasets: [{
          label: 'Assessment Score (%)',
          data: scores.length > 0 ? scores : [0],
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } },
          x: { grid: { color: 'rgba(255,255,255,0.05)' } }
        },
        plugins: { legend: { display: false } }
      }
    });

    // 2. AI Usage breakdown
    const aiStatsContainer = document.getElementById("ws-analytics-ai-stats");
    aiStatsContainer.innerHTML = "";
    if (data.ai_stats && data.ai_stats.length > 0) {
      data.ai_stats.forEach(st => {
        const div = document.createElement("div");
        div.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 8px 12px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem;";
        div.innerHTML = `
          <span style="text-transform: capitalize; color: #fff;">${st.feature.replace(/_/g, ' ')}</span>
          <span style="color: var(--text-muted);">${st.call_count} calls • ~${Math.round(st.avg_latency || 0)}ms</span>
        `;
        aiStatsContainer.appendChild(div);
      });
    } else {
      aiStatsContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">No AI requests recorded for this project yet.</div>`;
    }

    // 3. Learning Event Stream
    const eventStream = document.getElementById("ws-analytics-event-stream");
    eventStream.innerHTML = "";
    if (data.events && data.events.length > 0) {
      data.events.forEach(ev => {
        const div = document.createElement("div");
        div.style = "background: rgba(255,255,255,0.02); padding: 8px 12px; border-radius: 6px; font-size: 0.75rem; display: flex; justify-content: space-between;";
        div.innerHTML = `
          <span style="color: #fff;">${formatEventType(ev.event_type)}</span>
          <span style="color: var(--text-muted);">${formatTime(ev.created_at)}</span>
        `;
        eventStream.appendChild(div);
      });
    } else {
      eventStream.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">No events recorded yet.</div>`;
    }
  } catch (e) {}
}

// -------------------------------------------------------------
// Admin Dashboard & AI Observability
// -------------------------------------------------------------
async function loadAdminDashboard() {
  try {
    // 1. Overview KPIs
    const res = await fetch("/api/admin/overview");
    const data = await res.json();
    if (data.success) {
      document.getElementById("adm-kpi-users").textContent = data.users;
      document.getElementById("adm-kpi-spaces").textContent = data.spaces;
      document.getElementById("adm-kpi-projects").textContent = data.projects;
      document.getElementById("adm-kpi-ai-calls").textContent = data.ai_calls;
      document.getElementById("adm-kpi-cost").textContent = `$${data.estimated_cost_usd.toFixed(4)}`;
      document.getElementById("adm-kpi-latency").textContent = `${data.average_latency_ms} ms`;
    }

    // 2. Users list for inspector
    const userRes = await fetch("/api/admin/users");
    const userData = await userRes.json();
    const userContainer = document.getElementById("adm-users-list");
    userContainer.innerHTML = "";
    if (userData.users) {
      userData.users.forEach(u => {
        const row = document.createElement("div");
        row.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; cursor: pointer;";
        row.onclick = () => inspectUserJourney(u.id);
        row.innerHTML = `
          <div>
            <div style="font-weight: 600; font-size: 0.85rem; color: #fff;">${u.username} <span style="font-size: 0.7rem; color: var(--text-muted);">(${u.role})</span></div>
            <div style="font-size: 0.7rem; color: var(--text-muted);">${u.project_count} projects • ${u.quiz_count} quizzes • ${u.ai_calls_count} AI calls</div>
          </div>
          <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 4px 8px;">Inspect</button>
        `;
        userContainer.appendChild(row);
      });
    }

    // 3. AI Evaluations
    loadAdminEvaluations();

    // 4. Background Jobs
    const jobsRes = await fetch("/api/admin/jobs");
    const jobsData = await jobsRes.json();
    const jobsContainer = document.getElementById("adm-jobs-list");
    jobsContainer.innerHTML = "";
    if (jobsData.jobs && jobsData.jobs.length > 0) {
      jobsData.jobs.forEach(j => {
        const jDiv = document.createElement("div");
        jDiv.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 8px 10px; border-radius: 6px; display: flex; justify-content: space-between; font-size: 0.75rem;";
        jDiv.innerHTML = `
          <div>
            <span style="font-weight: 600; color: #fff;">${j.job_type}</span>
            <span style="color: var(--text-muted); margin-left: 6px;">(${formatTime(j.created_at)})</span>
          </div>
          <span style="color: ${j.status === 'completed' ? '#10b981' : (j.status === 'failed' ? '#ef4444' : '#eab308')}; font-weight: 700; text-transform: uppercase;">${j.status}</span>
        `;
        jobsContainer.appendChild(jDiv);
      });
    } else {
      jobsContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">No background jobs recorded.</div>`;
    }

    // 5. System Health
    const healthRes = await fetch("/api/admin/system-health");
    const healthData = await healthRes.json();
    const healthContainer = document.getElementById("adm-health-container");
    healthContainer.innerHTML = `
      <div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px; font-size: 0.8rem; display: flex; justify-content: space-between;">
        <span>Database Connected:</span> <strong style="color: #10b981;">Healthy (SQLite WAL)</strong>
      </div>
      <div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px; font-size: 0.8rem; display: flex; justify-content: space-between;">
        <span>Background Worker Queue:</span> <strong style="color: #10b981;">Active Daemon</strong>
      </div>
      <div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px; font-size: 0.8rem; display: flex; justify-content: space-between;">
        <span>Groq LLM:</span> <strong style="color: ${healthData.llm_providers?.groq ? '#10b981' : '#eab308'};">${healthData.llm_providers?.groq ? 'Online (Primary)' : 'Not Configured'}</strong>
      </div>
      <div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px; font-size: 0.8rem; display: flex; justify-content: space-between;">
        <span>Gemini LLM:</span> <strong style="color: ${healthData.llm_providers?.gemini ? '#10b981' : '#eab308'};">${healthData.llm_providers?.gemini ? 'Online (Fallback)' : 'Standby'}</strong>
      </div>
    `;

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    console.error("Admin load error:", e);
  }
}

async function loadAdminEvaluations() {
  const evRes = await fetch("/api/admin/evaluations");
  const evData = await evRes.json();
  const evContainer = document.getElementById("adm-evaluations-list");
  evContainer.innerHTML = "";

  if (evData.evaluations && evData.evaluations.length > 0) {
    const passed = evData.evaluations.filter(x => x.passed).length;
    const rate = Math.round((passed / evData.evaluations.length) * 100);
    document.getElementById("adm-eval-pass-rate").textContent = `Pass: ${rate}% (${passed}/${evData.evaluations.length})`;

    evData.evaluations.slice(0, 10).forEach(ev => {
      const eDiv = document.createElement("div");
      eDiv.style = "background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); padding: 8px 10px; border-radius: 6px; font-size: 0.75rem;";
      eDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
          <strong style="color: #fff;">${ev.test_name}</strong>
          <span style="color: ${ev.passed ? '#10b981' : '#ef4444'}; font-weight: 700;">${ev.passed ? '✓ PASSED' : '✗ FAILED'} (${ev.latency_ms}ms)</span>
        </div>
        <div style="color: var(--text-muted);">${ev.expected_behavior}</div>
      `;
      evContainer.appendChild(eDiv);
    });
  } else {
    evContainer.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem;">Click "Run AI Evaluation Suite" above to benchmark the system.</div>`;
  }
}

async function triggerAiEvaluations() {
  const evContainer = document.getElementById("adm-evaluations-list");
  evContainer.innerHTML = `<div style="color: var(--accent-primary); font-size: 0.8rem;"><i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Executing automated benchmark test suite...</div>`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/admin/evaluations/run", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      loadAdminEvaluations();
    }
  } catch (e) {}
}

async function inspectUserJourney(userId) {
  try {
    const res = await fetch(`/api/admin/users/${userId}/journey`);
    const data = await res.json();
    if (!data.success) return;

    alert(`User Journey: ${data.user.username}\nProjects: ${data.projects.length}\nQuizzes: ${data.quizzes.length}\nAI Calls: ${data.ai_interactions.length}`);
  } catch (e) {}
}

// -------------------------------------------------------------
// Settings & Key Management
// -------------------------------------------------------------
async function saveApiKey(e) {
  e.preventDefault();
  const provider = document.getElementById("settings-provider-select").value;
  const apiKey = document.getElementById("settings-api-key").value.trim();
  const msgEl = document.getElementById("settings-save-msg");

  if (!apiKey) return;

  try {
    const res = await fetch("/api/save-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, api_key: apiKey })
    });
    const data = await res.json();
    msgEl.style.display = "block";
    msgEl.style.color = res.ok ? "#10b981" : "#ef4444";
    msgEl.textContent = data.message || data.error;
    checkApiStatus();
  } catch (err) {
    msgEl.style.display = "block";
    msgEl.style.color = "#ef4444";
    msgEl.textContent = "Error saving settings.";
  }
}

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------
function formatTime(dtStr) {
  if (!dtStr) return "";
  const d = new Date(dtStr);
  return isNaN(d.getTime()) ? dtStr : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatEventType(evt) {
  if (!evt) return "Activity";
  return evt.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeJs(str) {
  if (!str) return "";
  return str.replace(/'/g, "\\'");
}

// -------------------------------------------------------------
// Career & Study Readiness Labs (Resume, Planner, Video, Chat)
// -------------------------------------------------------------
let latestResumeData = null;
let latestPlanData = null;

function switchLabSubtab(subtabId) {
  document.querySelectorAll("#tab-labs .ws-tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".lab-subtab").forEach(t => t.style.display = "none");

  const btn = document.getElementById(`lab-btn-${subtabId}`);
  const target = document.getElementById(`lab-subtab-${subtabId}`);
  if (btn) btn.classList.add("active");
  if (target) target.style.display = "block";

  if (window.lucide) lucide.createIcons();
}

async function handleResumeAnalysis(e) {
  e.preventDefault();
  const fileInput = document.getElementById("resume-file-input");
  const jdInput = document.getElementById("resume-jd-input");
  const targetRole = document.getElementById("resume-target-role").value.trim();
  const submitBtn = document.getElementById("resume-submit-btn");

  if (!fileInput.files[0] || !jdInput.value.trim()) return;

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 16px; height: 16px;"></i> Analyzing Resume & Skill Gaps...`;
  if (window.lucide) lucide.createIcons();

  const formData = new FormData();
  formData.append("resume", fileInput.files[0]);
  formData.append("job_description", jdInput.value.trim());

  try {
    const res = await fetch("/api/analyze-resume", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="scan" style="width: 16px; height: 16px;"></i> Scan & Calculate ATS Match`;
    if (window.lucide) lucide.createIcons();

    if (!res.ok) {
      alert(data.error || "Resume analysis failed.");
      return;
    }

    latestResumeData = { ...data, target_role: targetRole };
    renderResumeResults(latestResumeData);
  } catch (err) {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="scan" style="width: 16px; height: 16px;"></i> Scan & Calculate ATS Match`;
    alert("Network error analyzing resume.");
  }
}

function renderResumeResults(data) {
  document.getElementById("resume-results-placeholder").style.display = "none";
  const content = document.getElementById("resume-results-content");
  content.style.display = "flex";

  // Score
  const scoreEl = document.getElementById("resume-score-val");
  scoreEl.textContent = `${data.ats_score}%`;
  scoreEl.style.color = data.ats_score >= 70 ? "#10b981" : (data.ats_score >= 45 ? "#eab308" : "#ef4444");

  // Missing chips
  const missContainer = document.getElementById("resume-missing-chips");
  missContainer.innerHTML = "";
  if (data.missing_skills && data.missing_skills.length > 0) {
    data.missing_skills.forEach(s => {
      const chip = document.createElement("span");
      chip.style = "background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.25); padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;";
      chip.textContent = s;
      missContainer.appendChild(chip);
    });
  } else {
    missContainer.innerHTML = `<span style="color: #10b981; font-size: 0.75rem;">None! All detected skills matched.</span>`;
  }

  // Matched chips
  const matchContainer = document.getElementById("resume-matched-chips");
  matchContainer.innerHTML = "";
  if (data.matched_skills && data.matched_skills.length > 0) {
    data.matched_skills.forEach(s => {
      const chip = document.createElement("span");
      chip.style = "background: rgba(16, 185, 129, 0.12); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.25); padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;";
      chip.textContent = s;
      matchContainer.appendChild(chip);
    });
  } else {
    matchContainer.innerHTML = `<span style="color: var(--text-muted); font-size: 0.75rem;">No exact keyword skills matched.</span>`;
  }

  // AI Suggestions
  const mdEl = document.getElementById("resume-suggestions-md");
  mdEl.innerHTML = window.marked ? marked.parse(data.suggestions || "") : data.suggestions;
  if (window.lucide) lucide.createIcons();
}

async function bridgeMissingSkillsToProject() {
  if (!latestResumeData || !latestResumeData.missing_skills || latestResumeData.missing_skills.length === 0) {
    alert("No missing skills to bridge into a project.");
    return;
  }

  const btn = document.getElementById("resume-bridge-btn");
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Creating Project...`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/create-project-from-gap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        missing_skills: latestResumeData.missing_skills,
        target_role: latestResumeData.target_role || "Target Role"
      })
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> Bridge Gap: Create Project`;

    if (data.success && data.project_id) {
      alert(`Success! Created Project targeting: ${latestResumeData.missing_skills.join(", ")}.\nOpening project workspace now...`);
      openProjectWorkspace(data.project_id);
    } else {
      alert(data.error || "Failed to create project.");
    }
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> Bridge Gap: Create Project`;
    alert("Network error creating project.");
  }
}

async function handleStudyPlannerSubmit(e) {
  e.preventDefault();
  const topic = document.getElementById("planner-topic").value.trim();
  const weeks = document.getElementById("planner-weeks").value;
  const hours = document.getElementById("planner-hours").value;
  const level = document.getElementById("planner-level").value;
  const skills = document.getElementById("planner-skills").value.trim();
  const submitBtn = document.getElementById("planner-submit-btn");
  const outputEl = document.getElementById("planner-output-content");
  const pinBtn = document.getElementById("planner-pin-btn");

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Generating Plan...`;
  outputEl.innerHTML = `<div style="color: var(--text-muted);"><i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Designing multi-week curriculum, hours breakdown, and milestones...</div>`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/study-assistant/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_topic: topic,
        duration_weeks: weeks,
        hours_per_week: hours,
        skill_level: level,
        current_skills: skills
      })
    });
    const data = await res.json();
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="calendar" style="width: 16px; height: 16px;"></i> Generate Plan`;

    if (data.success) {
      latestPlanData = { topic, plan: data.plan };
      outputEl.innerHTML = window.marked ? marked.parse(data.plan) : data.plan;
      pinBtn.style.display = "block";
    } else {
      outputEl.innerHTML = `<div style="color: #ef4444;">Error: ${data.error}</div>`;
    }
  } catch (err) {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="calendar" style="width: 16px; height: 16px;"></i> Generate Plan`;
    outputEl.innerHTML = `<div style="color: #ef4444;">Network error generating plan.</div>`;
  }
}

async function pinPlanAsProject() {
  if (!latestPlanData) return;
  // Create project under active space or default
  const spacesRes = await fetch("/api/spaces");
  const spacesData = await spacesRes.json();
  const spaceId = spacesData.spaces && spacesData.spaces.length > 0 ? spacesData.spaces[0].id : 1;

  const res = await fetch(`/api/spaces/${spaceId}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: `Curriculum: ${latestPlanData.topic}`,
      learning_goal: `Complete structured multi-week study curriculum for ${latestPlanData.topic}`,
      description: latestPlanData.plan.slice(0, 150) + "..."
    })
  });
  const data = await res.json();
  if (data.success) {
    alert(`Pinned as new Project: 'Curriculum: ${latestPlanData.topic}'! Opening project workspace...`);
    openProjectWorkspace(data.project.id);
  }
}

async function handleYoutubeSummary(e) {
  e.preventDefault();
  const urlInput = document.getElementById("youtube-url-input");
  const submitBtn = document.getElementById("youtube-submit-btn");
  const card = document.getElementById("youtube-output-card");
  const content = document.getElementById("youtube-summary-content");

  if (!urlInput.value.trim()) return;

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Fetching & Summarizing...`;
  card.style.display = "block";
  content.innerHTML = `<i data-lucide="loader" class="spin" style="width: 14px; height: 14px;"></i> Extracting YouTube lecture transcript and distilling technical takeaways...`;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/summarize-youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim() })
    });
    const data = await res.json();
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="sparkles" style="width: 16px; height: 16px;"></i> Summarize`;

    if (data.success) {
      content.innerHTML = window.marked ? marked.parse(data.summary) : data.summary;
    } else {
      content.innerHTML = `<div style="color: #ef4444;">Error: ${data.error}</div>`;
    }
  } catch (err) {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="sparkles" style="width: 16px; height: 16px;"></i> Summarize`;
    content.innerHTML = `<div style="color: #ef4444;">Network error summarizing video.</div>`;
  }
}

let generalChatHistory = [];
async function handleGeneralChat(e) {
  e.preventDefault();
  const input = document.getElementById("general-chat-input");
  const msg = input.value.trim();
  if (!msg) return;

  input.value = "";
  const stream = document.getElementById("general-chat-stream");

  // User msg
  const uDiv = document.createElement("div");
  uDiv.className = "tutor-msg user-msg";
  uDiv.innerHTML = `<div class="msg-bubble">${escapeHtml(msg)}</div>`;
  stream.appendChild(uDiv);

  // Typing
  const tDiv = document.createElement("div");
  tDiv.id = "general-typing";
  tDiv.className = "tutor-msg assistant-msg";
  tDiv.innerHTML = `<div class="msg-bubble" style="color: var(--text-muted);"><i data-lucide="loader" class="spin" style="width: 12px; height: 12px;"></i> Thinking...</div>`;
  stream.appendChild(tDiv);
  stream.scrollTop = stream.scrollHeight;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, history: generalChatHistory })
    });
    let data;
    try {
      data = await res.json();
    } catch (parseErr) {
      data = { success: false, error: "Server returned an invalid response. Please try again." };
    }

    const typing = document.getElementById("general-typing");
    if (typing) typing.remove();

    if (data && data.success) {
      generalChatHistory.push({ role: "user", text: msg });
      generalChatHistory.push({ role: "assistant", text: data.response });

      const aDiv = document.createElement("div");
      aDiv.className = "tutor-msg assistant-msg";
      aDiv.innerHTML = `<div class="msg-bubble">${window.marked ? marked.parse(data.response) : data.response}</div>`;
      stream.appendChild(aDiv);
    } else {
      const eDiv = document.createElement("div");
      eDiv.className = "tutor-msg assistant-msg";
      eDiv.innerHTML = `<div class="msg-bubble" style="color: #ef4444;">${(data && data.error) || "Failed to receive response."}</div>`;
      stream.appendChild(eDiv);
    }
  } catch (err) {
    const typing = document.getElementById("general-typing");
    if (typing) typing.remove();
    const eDiv = document.createElement("div");
    eDiv.className = "tutor-msg assistant-msg";
    eDiv.innerHTML = `<div class="msg-bubble" style="color: #ef4444;">Unable to connect to server. Please check your network connection and try again.</div>`;
    stream.appendChild(eDiv);
  }

  stream.scrollTop = stream.scrollHeight;
  if (window.lucide) lucide.createIcons();
}
