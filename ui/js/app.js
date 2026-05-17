const { createApp, ref, computed, onMounted } = Vue;

marked.setOptions({ breaks: true, gfm: true });
const md        = (text) => marked.parse(text || "");
const parseTags = (raw)  => raw.split(",").map((t) => t.trim()).filter(Boolean);
const tagsToStr = (tags) => tags.join(", ");
const key       = (p)   => p.project + "/" + p.name;
const AUTH_TOKEN_STORAGE_KEY = "promptman.access_token";
const emptyPromptData = () => ({
  role: "",
  task: "",
  context: "",
  constraints: "",
  output_format: "",
  examples: "",
});
const defaultOptimizeConfig = () => ({
  model_id: "",
  rounds: 2,
  gp_profile: "fast",
  llm_provider: "ollama",
  llm_model: "qwen2.5:0.5b",
  llm_base_url: "http://127.0.0.1:11434",
  llm_timeout_seconds: 300,
  llm_api_token: "",
  effective_model_id: "",
  effective_rounds: 2,
  effective_gp_profile: "fast",
  effective_llm_provider: "ollama",
  effective_llm_model: "qwen2.5:0.5b",
  effective_llm_base_url: "http://127.0.0.1:11434",
  effective_llm_timeout_seconds: 300,
  effective_has_llm_api_token: false,
});
const emptyUserForm = () => ({
  username: "",
  password: "",
  role: "developer",
  projects: [],
  is_active: true,
});
const emptyProjectForm = () => ({
  name: "",
});
const defaultUserRoleOptions = ["admin", "developer"];
const llmProviderConfigs = {
  ollama: {
    label: "Ollama (Local)",
    baseUrl: "http://127.0.0.1:11434",
    models: ["qwen2.5:0.5b", "phi3:mini", "llama3.2:1b", "qwen2.5:1.5b", "gemma2:2b"],
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
  },
  anthropic: {
    label: "Anthropic Claude",
    baseUrl: "https://api.anthropic.com",
    models: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
  },
};
const llmProviderOptions = Object.keys(llmProviderConfigs);
const gpProfileOptions = ["fast", "quality", "ultra"];
const gpRecommendedModels = [
  {
    group: "Gemma",
    value: "google/gemma-2-9b-it",
    label: "Gemma-2-9B-IT",
    supported: "✔",
    quality: "High",
    speed: "Fast",
    vram: "~16-24 GB",
    bestUse: "Primary GreaterPrompt model",
    recommended: true,
  },
  {
    group: "Gemma",
    value: "google/gemma-2-27b-it",
    label: "Gemma-2-27B-IT",
    supported: "✔",
    quality: "Very high",
    speed: "Medium",
    vram: "48+ GB",
    bestUse: "Complex tasks",
    recommended: false,
  },
  {
    group: "LLaMA",
    value: "meta-llama/Meta-Llama-3-8B-Instruct",
    label: "LLaMA-3-8B-Instruct",
    supported: "✔",
    quality: "Medium-high",
    speed: "Fast",
    vram: "16 GB",
    bestUse: "Local optimization",
    recommended: false,
  },
  {
    group: "LLaMA",
    value: "meta-llama/Meta-Llama-3-70B-Instruct",
    label: "LLaMA-3-70B-Instruct",
    supported: "✔",
    quality: "Very high",
    speed: "Slow",
    vram: "80+ GB",
    bestUse: "Maximum quality",
    recommended: false,
  },
  {
    group: "Compatible",
    value: "mistralai/Mistral-7B-Instruct-v0.3",
    label: "Mistral-7B-Instruct",
    supported: "✖",
    quality: "Medium-high",
    speed: "Very fast",
    vram: "8-16 GB",
    bestUse: "Economical option",
    recommended: false,
  },
  {
    group: "Compatible",
    value: "Qwen/Qwen2-7B-Instruct",
    label: "Qwen2-7B-Instruct",
    supported: "✖",
    quality: "High",
    speed: "Fast",
    vram: "8-16 GB",
    bestUse: "Reasoning tasks",
    recommended: false,
  },
];
const gpRecommendedModelGroups = ["Gemma", "LLaMA", "Compatible"];
const defaultLlmModelsByProvider = Object.fromEntries(
  Object.entries(llmProviderConfigs).map(([key, config]) => [key, config.models])
);

// Build markdown from decomposed fields
const buildPromptMarkdown = (fields) => {
  const parts = [];
  if (fields.role?.trim())           parts.push(`**Role:** ${fields.role}`);
  if (fields.task?.trim())           parts.push(`**Task:** ${fields.task}`);
  if (fields.context?.trim())        parts.push(`**Context:** ${fields.context}`);
  if (fields.constraints?.trim())    parts.push(`**Constraints:** ${fields.constraints}`);
  if (fields.output_format?.trim())  parts.push(`**Output format:** ${fields.output_format}`);
  if (fields.examples?.trim())       parts.push(`**Examples:** ${fields.examples}`);
  return parts.join("\n\n");
};

createApp({
  setup() {
    /* auth */
    const authReady = ref(false);
    const authToken = ref(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "");
    const currentUser = ref(null);
    const authMode = ref("login");
    const authForm = ref({ username: "", password: "" });
    const authError = ref("");
    const authStatus = ref("");
    const authBusy = ref(false);
    const authBootstrapRequired = ref(false);

    /* tabs */
    const activeTab = ref("browse");

    /* create form */
    const form         = ref({ name: "", project: "", tags: "", role: "", task: "", context: "", constraints: "", output_format: "", examples: "" });
    const createStatus = ref("");

    /* browse */
    const items         = ref([]);
    const filterProject = ref("");
    const filterTag     = ref("");
    const browsePage    = ref(1);
    const browsePageSize = ref(10);
    const browseTotalItems = ref(0);

    /* expanded prompt state */
    const expandedKey       = ref(null);
    const expandedVersions  = ref([]);
    const openVersionKey    = ref(null);
    const editTagsMode      = ref(false);
    const editTagsStr       = ref("");
    const newVersionRole    = ref("");
    const newVersionTask    = ref("");
    const newVersionContext = ref("");
    const newVersionConstraints = ref("");
    const newVersionOutputFormat = ref("");
    const newVersionExamples = ref("");
    const saveStatus        = ref("");
    const deleteStatus      = ref("");
    const newVersionEditorOpen = ref(false);

    /* optimizer */
    const createOptimizeMenuOpen = ref(false);
    const browseOptimizeMenuKey = ref(null);
    const optimizerModalOpen = ref(false);
    const optimizerLoading = ref(false);
    const optimizerError = ref("");
    const optimizerStatus = ref("");
    const optimizerMode = ref("greaterprompt");
    const optimizerLogs = ref([]);
    const optimizerEngine = ref("");
    const optimizerNotes = ref([]);
    const optimizedMarkdown = ref("");
    const optimizedDraft = ref(emptyPromptData());
    const optimizeInputSource = ref("create");
    const optimizeTargetPrompt = ref(null);
    const optimizeEndpoint = ref("/optimize/greaterprompt");
    const optimizeConfig = ref(defaultOptimizeConfig());
    const optimizeConfigStatus = ref("");
    const availableLlmModels = ref([...defaultLlmModelsByProvider.ollama]);
    const llmModelsLoading = ref(false);
    const llmModelsLoadError = ref("");

    /* admin */
    const roleOptions = ref([...defaultUserRoleOptions]);
    const projects = ref([]);
    const projectsLoading = ref(false);
    const projectsStatus = ref("");
    const newProjectForm = ref(emptyProjectForm());
    const editingProjectId = ref(null);
    const editProjectForm = ref(emptyProjectForm());
    const users = ref([]);
    const usersLoading = ref(false);
    const usersStatus = ref("");
    const newUserForm = ref(emptyUserForm());
    const editingUserId = ref(null);
    const editUserForm = ref(emptyUserForm());

    const gpModelsByGroup = Object.fromEntries(
      gpRecommendedModelGroups.map((group) => [
        group,
        gpRecommendedModels.filter((model) => model.group === group),
      ])
    );

    const selectedGpModelMeta = computed(() => {
      return gpRecommendedModels.find((model) => model.value === optimizeConfig.value.model_id) || null;
    });
    const isAuthenticated = computed(() => !!currentUser.value);
    const isAdmin = computed(() => currentUser.value?.role === "admin");
    const availableProjectNames = computed(() => projects.value.map((project) => project.name));
    const currentUserProjectsLabel = computed(() => {
      if (!currentUser.value) return "";
      if (currentUser.value.role === "admin") return "All projects";
      return (currentUser.value.projects || []).length ? currentUser.value.projects.join(", ") : "No assigned projects";
    });

    const nowTime = () => new Date().toLocaleTimeString("ru-RU", { hour12: false });

    const setDefaultActiveTab = () => {
      activeTab.value = currentUser.value?.role === "admin" ? "admin" : "browse";
    };

    const normalizeProjects = (raw) => {
      if (Array.isArray(raw)) {
        return raw.map((item) => String(item || "").trim()).filter(Boolean);
      }
      return String(raw || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    };

    const saveToken = (token) => {
      authToken.value = token || "";
      if (authToken.value) {
        window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authToken.value);
      } else {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
    };

    const clearSession = (reason = "") => {
      saveToken("");
      currentUser.value = null;
      activeTab.value = "browse";
      items.value = [];
      browseTotalItems.value = 0;
      expandedKey.value = null;
      expandedVersions.value = [];
      optimizerModalOpen.value = false;
      users.value = [];
      projects.value = [];
      optimizeConfig.value = defaultOptimizeConfig();
      if (reason) {
        authError.value = reason;
      }
    };

    const authHeaders = (headers = {}) => {
      const merged = { ...headers };
      if (authToken.value) {
        merged.Authorization = `Bearer ${authToken.value}`;
      }
      return merged;
    };

    const apiFetch = async (url, options = {}, allow401 = false) => {
      const requestOptions = {
        ...options,
        headers: authHeaders(options.headers || {}),
      };
      const response = await fetch(url, requestOptions);
      if (response.status === 401 && !allow401) {
        clearSession("Session expired. Please sign in again.");
      }
      return response;
    };

    const fetchAuthStatus = async () => {
      try {
        const res = await fetch("/auth/status");
        if (!res.ok) {
          authBootstrapRequired.value = false;
          authMode.value = "login";
          return;
        }
        const payload = await res.json();
        authBootstrapRequired.value = !!payload.bootstrap_required;
        authMode.value = payload.bootstrap_required ? "bootstrap" : "login";
      } catch (err) {
        authBootstrapRequired.value = false;
        authMode.value = "login";
      }
    };

    const loadUsers = async () => {
      if (!isAdmin.value) {
        users.value = [];
        return;
      }
      usersLoading.value = true;
      usersStatus.value = "";
      const res = await apiFetch("/users");
      if (!res.ok) {
        usersLoading.value = false;
        usersStatus.value = `Failed to load users (${res.status})`;
        return;
      }
      users.value = await res.json();
      usersLoading.value = false;
    };

    const loadProjects = async () => {
      if (!isAdmin.value) {
        projects.value = [];
        return;
      }
      projectsLoading.value = true;
      projectsStatus.value = "";
      const res = await apiFetch("/projects");
      if (!res.ok) {
        projectsLoading.value = false;
        projectsStatus.value = `Failed to load projects (${res.status})`;
        return;
      }
      projects.value = await res.json();
      projectsLoading.value = false;
    };

    const loadRoles = async () => {
      if (!isAdmin.value) {
        roleOptions.value = [...defaultUserRoleOptions];
        return;
      }
      const res = await apiFetch("/roles");
      if (!res.ok) {
        roleOptions.value = [...defaultUserRoleOptions];
        return;
      }
      const roles = await res.json();
      roleOptions.value = Array.isArray(roles) && roles.length
        ? roles.map((item) => item.name)
        : [...defaultUserRoleOptions];
    };

    const initializeAuthenticatedApp = async () => {
      setDefaultActiveTab();
      await fetchPrompts();
      await loadOptimizeConfig();
      await loadRoles();
      await loadProjects();
      await loadUsers();
    };

    const loadCurrentUser = async () => {
      if (!authToken.value) {
        return false;
      }
      const res = await apiFetch("/auth/me", {}, true);
      if (!res.ok) {
        clearSession("");
        return false;
      }
      currentUser.value = await res.json();
      return true;
    };

    const submitAuth = async () => {
      authBusy.value = true;
      authError.value = "";
      authStatus.value = "";
      const endpoint = authMode.value === "bootstrap" ? "/auth/bootstrap-admin" : "/auth/login";
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: authForm.value.username.trim(),
            password: authForm.value.password,
          }),
        });
        if (!res.ok) {
          if (res.status === 409 && authMode.value === "bootstrap") {
            authBootstrapRequired.value = false;
            authMode.value = "login";
            authError.value = "Bootstrap is no longer available. Sign in with an existing account.";
            return;
          }
          const detail = await res.text();
          authError.value = detail || `Authentication failed (${res.status})`;
          return;
        }
        const payload = await res.json();
        saveToken(payload.access_token || "");
        currentUser.value = payload.user || null;
        authForm.value.password = "";
        authStatus.value = authMode.value === "bootstrap" ? "Admin account created." : "Signed in.";
        await initializeAuthenticatedApp();
      } catch (err) {
        authError.value = "Authentication request failed.";
      } finally {
        authBusy.value = false;
      }
    };

    const logout = () => {
      clearSession("");
      authStatus.value = "Signed out.";
      fetchAuthStatus();
    };

    const beginEditUser = (user) => {
      editingUserId.value = user.id;
      editUserForm.value = {
        username: user.username || "",
        password: "",
        role: user.role || "developer",
        projects: [...(user.projects || [])],
        is_active: !!user.is_active,
      };
      usersStatus.value = "";
    };

    const resolveFormState = (formRef) => formRef?.value ?? formRef ?? {};

    const toggleProjectSelection = (formRef, projectName) => {
      const formState = resolveFormState(formRef);
      const current = new Set(normalizeProjects(formState.projects));
      if (current.has(projectName)) {
        current.delete(projectName);
      } else {
        current.add(projectName);
      }
      formState.projects = [...current].sort((left, right) => left.localeCompare(right));
    };

    const isProjectSelected = (formRef, projectName) => {
      const formState = resolveFormState(formRef);
      return normalizeProjects(formState.projects).includes(projectName);
    };

    const cancelUserEdit = () => {
      editingUserId.value = null;
      editUserForm.value = emptyUserForm();
    };

    const createProjectRecord = async () => {
      projectsStatus.value = "";
      const res = await apiFetch("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newProjectForm.value.name.trim() }),
      });
      if (!res.ok) {
        projectsStatus.value = `Failed to create project (${res.status})`;
        return;
      }
      newProjectForm.value = emptyProjectForm();
      projectsStatus.value = "Project created";
      await loadProjects();
    };

    const beginEditProject = (project) => {
      editingProjectId.value = project.id;
      editProjectForm.value = { name: project.name || "" };
      projectsStatus.value = "";
    };

    const cancelProjectEdit = () => {
      editingProjectId.value = null;
      editProjectForm.value = emptyProjectForm();
    };

    const saveProjectEdit = async (projectId) => {
      projectsStatus.value = "";
      const res = await apiFetch(`/projects/${projectId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editProjectForm.value.name.trim() }),
      });
      if (!res.ok) {
        projectsStatus.value = `Failed to update project (${res.status})`;
        return;
      }
      projectsStatus.value = "Project updated";
      cancelProjectEdit();
      await loadProjects();
      await loadUsers();
      await fetchPrompts();
    };

    const deleteProjectRecord = async (project) => {
      projectsStatus.value = "";
      if (!window.confirm(`Delete project ${project.name}? All related prompts and access rules will be removed.`)) return;
      const res = await apiFetch(`/projects/${project.id}`, { method: "DELETE" });
      if (!res.ok) {
        projectsStatus.value = `Failed to delete project (${res.status})`;
        return;
      }
      projectsStatus.value = "Project deleted";
      await loadProjects();
      await loadUsers();
      await fetchPrompts(1);
    };

    const createUserAccount = async () => {
      usersStatus.value = "";
      const payload = {
        username: newUserForm.value.username.trim(),
        password: newUserForm.value.password,
        role: newUserForm.value.role,
        projects: normalizeProjects(newUserForm.value.projects),
        is_active: !!newUserForm.value.is_active,
      };
      const res = await apiFetch("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        usersStatus.value = `Failed to create user (${res.status})`;
        return;
      }
      newUserForm.value = emptyUserForm();
      usersStatus.value = "User created";
      await loadUsers();
    };

    const saveUserEdit = async (userId) => {
      usersStatus.value = "";
      const payload = {
        username: editUserForm.value.username.trim(),
        role: editUserForm.value.role,
        projects: normalizeProjects(editUserForm.value.projects),
        is_active: !!editUserForm.value.is_active,
      };
      if (editUserForm.value.password) {
        payload.password = editUserForm.value.password;
      }
      const res = await apiFetch(`/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        usersStatus.value = `Failed to update user (${res.status})`;
        return;
      }
      usersStatus.value = "User updated";
      cancelUserEdit();
      await loadUsers();
      if (currentUser.value?.id === userId) {
        await loadCurrentUser();
      }
    };

    const deleteUserAccount = async (user) => {
      usersStatus.value = "";
      if (!window.confirm(`Delete user ${user.username}?`)) return;
      const res = await apiFetch(`/users/${user.id}`, { method: "DELETE" });
      if (!res.ok) {
        usersStatus.value = `Failed to delete user (${res.status})`;
        return;
      }
      usersStatus.value = "User deleted";
      await loadUsers();
    };

    const pushOptimizerLog = (message, level = "info") => {
      optimizerLogs.value.push({
        ts: nowTime(),
        level,
        message,
      });
    };

    const normalizePageNumber = (page) => {
      const parsed = Number(page);
      return Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : 1;
    };

    const fetchPrompts = async (page = browsePage.value) => {
      if (!currentUser.value) {
        items.value = [];
        browseTotalItems.value = 0;
        return;
      }
      browsePage.value = normalizePageNumber(page);
      const p = new URLSearchParams();
      if (filterProject.value.trim()) p.set("project", filterProject.value.trim());
      if (filterTag.value.trim())     p.set("tag",     filterTag.value.trim());
      p.set("limit", String(browsePageSize.value));
      p.set("offset", String((browsePage.value - 1) * browsePageSize.value));
      const q   = p.toString();
      const res = await apiFetch("/prompts" + (q ? "?" + q : ""));
      if (!res.ok) {
        console.error("fetchPrompts failed:", res.status, res.statusText);
        items.value = [];
        browseTotalItems.value = 0;
        return;
      }
      items.value = await res.json();
      browseTotalItems.value = Number(res.headers.get("X-Total-Count") || items.value.length || 0);
    };

    const totalBrowsePages = computed(() => {
      const total = Math.ceil(browseTotalItems.value / browsePageSize.value);
      return Math.max(1, total);
    });

    const paginatedItems = computed(() => items.value);

    const setBrowsePage = async (page) => {
      const nextPage = Math.min(normalizePageNumber(page), totalBrowsePages.value);
      await fetchPrompts(nextPage);
    };

    const browseSummaryLabel = computed(() => {
      return `Total ${browseTotalItems.value || 0}`;
    });

    const loadVersions = async (p) => {
      const res = await apiFetch("/prompts/" + p.project + "/" + p.name + "/versions");
      expandedVersions.value = res.ok ? await res.json() : [];
    };

    const togglePrompt = async (p) => {
      const k = key(p);
      if (expandedKey.value === k) {
        expandedKey.value = null; expandedVersions.value = [];
        openVersionKey.value = null; editTagsMode.value = false;
        newVersionEditorOpen.value = false;
        newVersionRole.value = ""; newVersionTask.value = ""; newVersionContext.value = "";
        newVersionConstraints.value = ""; newVersionOutputFormat.value = ""; newVersionExamples.value = "";
        saveStatus.value = "";
        deleteStatus.value = "";
        return;
      }
      expandedKey.value       = k;
      editTagsMode.value      = false;
      newVersionEditorOpen.value = false;
      editTagsStr.value       = tagsToStr(p.tags);
      newVersionRole.value    = p.role || "";
      newVersionTask.value    = p.task || "";
      newVersionContext.value = p.context || "";
      newVersionConstraints.value = p.constraints || "";
      newVersionOutputFormat.value = p.output_format || "";
      newVersionExamples.value = p.examples || "";
      saveStatus.value        = "";
      deleteStatus.value      = "";
      openVersionKey.value    = null;
      await loadVersions(p);
    };

    const deletePrompt = async (p) => {
      deleteStatus.value = "";
      const confirmed = window.confirm(`Delete prompt ${p.project} / ${p.name}? This cannot be undone.`);
      if (!confirmed) return;

      const res = await apiFetch("/prompts/" + p.project + "/" + p.name, {
        method: "DELETE",
      });

      if (!res.ok) {
        deleteStatus.value = "Delete failed (" + res.status + ")";
        return;
      }

      deleteStatus.value = "Prompt deleted";
      expandedKey.value = null;
      expandedVersions.value = [];
      openVersionKey.value = null;
      editTagsMode.value = false;
      await fetchPrompts();
    };

    const saveNewVersion = async (p) => {
      saveStatus.value = "";
      const res = await apiFetch("/prompts/" + p.project + "/" + p.name, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: newVersionRole.value || null,
          task: newVersionTask.value,
          context: newVersionContext.value || null,
          constraints: newVersionConstraints.value || null,
          output_format: newVersionOutputFormat.value || null,
          examples: newVersionExamples.value || null,
        }),
      });
      if (!res.ok) { saveStatus.value = "Save failed (" + res.status + ")"; return; }
      saveStatus.value = "Version saved";
      await fetchPrompts();
      await loadVersions(p);
      const updated = items.value.find((i) => key(i) === expandedKey.value);
      if (updated) {
        newVersionRole.value    = updated.role || "";
        newVersionTask.value    = updated.task || "";
        newVersionContext.value = updated.context || "";
        newVersionConstraints.value = updated.constraints || "";
        newVersionOutputFormat.value = updated.output_format || "";
        newVersionExamples.value = updated.examples || "";
      }
    };

    const saveTags = async (p) => {
      saveStatus.value = "";
      const res = await apiFetch("/prompts/" + p.project + "/" + p.name + "/tags", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: parseTags(editTagsStr.value) }),
      });
      if (!res.ok) { saveStatus.value = "Tag save failed (" + res.status + ")"; return; }
      saveStatus.value = "Tags updated";
      editTagsMode.value = false;
      await fetchPrompts();
    };

    const createPrompt = async () => {
      createStatus.value = "";
      const name = form.value.name.trim();
      const project = form.value.project.trim();
      if (!name || !project) {
        createStatus.value = "Name and Project are required";
        return;
      }

      const payload = {
        name,
        project,
        tags:    parseTags(form.value.tags),
        role:    form.value.role || null,
        task:    form.value.task,
        context: form.value.context || null,
        constraints: form.value.constraints || null,
        output_format: form.value.output_format || null,
        examples: form.value.examples || null,
      };
      const res = await apiFetch("/prompts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) { createStatus.value = "Create failed (" + res.status + ")"; return; }
      form.value = { name: "", project: "", tags: "", role: "", task: "", context: "", constraints: "", output_format: "", examples: "" };
      createStatus.value = "Prompt created";
      await fetchPrompts();
      activeTab.value = "browse";
    };

    const promptPayload = (fields) => ({
      role: fields.role || null,
      task: fields.task || "",
      context: fields.context || null,
      constraints: fields.constraints || null,
      output_format: fields.output_format || null,
      examples: fields.examples || null,
    });

    const getDefaultProviderModels = (provider) => {
      const key = String(provider || "").toLowerCase();
      return [...(defaultLlmModelsByProvider[key] || [])];
    };

    const getProviderConfig = (provider) => {
      const key = String(provider || "").toLowerCase();
      return llmProviderConfigs[key] || llmProviderConfigs.ollama;
    };

    const getProviderLabel = (provider) => {
      return getProviderConfig(provider).label || provider;
    };

    const getProviderDefaultBaseUrl = (provider) => {
      return getProviderConfig(provider).baseUrl || "http://127.0.0.1:11434";
    };

    const getProviderDefaultModel = (provider) => {
      return getDefaultProviderModels(provider)[0] || "";
    };

    const updateProviderBaseUrl = (provider = optimizeConfig.value.llm_provider) => {
      optimizeConfig.value.llm_base_url = getProviderDefaultBaseUrl(provider);
      optimizeConfig.value.llm_model = getProviderDefaultModel(provider);
    };

    const modelRequiresToken = (provider = optimizeConfig.value.llm_provider) => {
      const key = String(provider || "").toLowerCase();
      return ["openai", "anthropic"].includes(key);
    };

    const loadAvailableLlmModels = async (provider = optimizeConfig.value.llm_provider, preserveCurrentModel = true) => {
      llmModelsLoading.value = true;
      llmModelsLoadError.value = "";

      const selectedProvider = String(provider || "ollama").toLowerCase();
      const fallbackModels = getDefaultProviderModels(selectedProvider);

      try {
        const params = new URLSearchParams();
        if ((optimizeConfig.value.llm_base_url || "").trim()) {
          params.set("base_url", optimizeConfig.value.llm_base_url.trim());
        }
        if ((optimizeConfig.value.llm_api_token || "").trim()) {
          params.set("api_token", optimizeConfig.value.llm_api_token.trim());
        }
        params.set("timeout_seconds", "5");

        const res = await apiFetch(`/optimize/providers/${encodeURIComponent(selectedProvider)}/models?${params.toString()}`);
        if (!res.ok) {
          llmModelsLoadError.value = `Failed to load provider models (${res.status})`;
          availableLlmModels.value = fallbackModels;
        } else {
          const discovered = await res.json();
          const clean = Array.isArray(discovered)
            ? discovered.filter((m) => typeof m === "string" && m.trim())
            : [];
          availableLlmModels.value = clean.length ? clean : fallbackModels;
          if (!clean.length) {
            llmModelsLoadError.value = "No models discovered for selected provider. Showing fallback list.";
          }
        }
      } catch (err) {
        llmModelsLoadError.value = "Unable to connect to provider for model discovery.";
        availableLlmModels.value = fallbackModels;
      } finally {
        const currentModel = (optimizeConfig.value.llm_model || "").trim();
        if (preserveCurrentModel && currentModel && !availableLlmModels.value.includes(currentModel)) {
          availableLlmModels.value = [currentModel, ...availableLlmModels.value];
        }
        if (!currentModel || !availableLlmModels.value.includes(currentModel)) {
          if (availableLlmModels.value.length) {
            optimizeConfig.value.llm_model = availableLlmModels.value[0];
          }
        }
        llmModelsLoading.value = false;
      }
    };

    const loadOptimizeConfig = async () => {
      if (!currentUser.value) {
        optimizeConfig.value = defaultOptimizeConfig();
        return;
      }
      const res = await apiFetch("/optimize/config");
      if (!res.ok) {
        optimizeConfigStatus.value = "Failed to load optimize config (" + res.status + ")";
        return;
      }
      const cfg = await res.json();
      optimizeConfig.value = {
        ...defaultOptimizeConfig(),
        ...cfg,
        model_id: cfg.runtime_model_id || "",
        rounds: cfg.runtime_rounds || cfg.effective_rounds || 2,
        gp_profile: cfg.runtime_gp_profile || cfg.effective_gp_profile || "fast",
        llm_provider: cfg.runtime_llm_provider || cfg.effective_llm_provider || "ollama",
        llm_model: cfg.runtime_llm_model || cfg.effective_llm_model || "qwen2.5:0.5b",
        llm_base_url: cfg.runtime_llm_base_url || cfg.effective_llm_base_url || "http://127.0.0.1:11434",
        llm_timeout_seconds: cfg.runtime_llm_timeout_seconds || cfg.effective_llm_timeout_seconds || 300,
        llm_api_token: "",  // Never populate token from response for security
        effective_has_llm_api_token: cfg.effective_has_llm_api_token || false,
      };
      await loadAvailableLlmModels(optimizeConfig.value.llm_provider);
    };

    const persistOptimizeConfig = async (showSuccessMessage = true) => {
      optimizeConfigStatus.value = "";
      const payload = {
        model_id: optimizeConfig.value.model_id || null,
        rounds: Number(optimizeConfig.value.rounds) || 2,
        gp_profile: optimizeConfig.value.gp_profile || "fast",
        llm_provider: optimizeConfig.value.llm_provider || "ollama",
        llm_model: optimizeConfig.value.llm_model || "qwen2.5:0.5b",
        llm_base_url: optimizeConfig.value.llm_base_url || "http://127.0.0.1:11434",
        llm_timeout_seconds: Number(optimizeConfig.value.llm_timeout_seconds) || 300,
        llm_api_token: optimizeConfig.value.llm_api_token || null,
      };
      const res = await apiFetch("/optimize/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        optimizeConfigStatus.value = "Failed to save optimize config (" + res.status + ")";
        return false;
      }
      if (showSuccessMessage) {
        optimizeConfigStatus.value = "Optimize config saved";
      }
      await loadOptimizeConfig();
      return true;
    };

    const saveOptimizeConfig = async () => {
      await persistOptimizeConfig(true);
    };

    const optimizePrompt = async (endpoint, fields, source, target = null) => {
      optimizerLoading.value = true;
      optimizerError.value = "";
      optimizerStatus.value = "Optimization started";
      optimizerEngine.value = "";
      optimizerNotes.value = [];
      optimizerLogs.value = [];
      optimizedMarkdown.value = "";
      optimizeEndpoint.value = endpoint;
      optimizeInputSource.value = source;
      optimizeTargetPrompt.value = target;
      optimizerMode.value = endpoint.includes("/llm") ? "llm" : "greaterprompt";
      optimizerModalOpen.value = true;

      pushOptimizerLog(
        `Started ${optimizerMode.value === "llm" ? "LLM" : "GreaterPrompt"} optimization from ${source}.`
      );
      pushOptimizerLog("Saving active optimization config before request ...");

      const saved = await persistOptimizeConfig(false);
      if (!saved) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Unable to save optimization config before optimization.";
        pushOptimizerLog("Failed to save optimization config before optimization.", "error");
        return;
      }

      pushOptimizerLog("Optimization config saved and applied.", "success");
      if (optimizerMode.value === "llm") {
        pushOptimizerLog(
          `Using provider=${optimizeConfig.value.effective_llm_provider || optimizeConfig.value.llm_provider}, model=${optimizeConfig.value.effective_llm_model || optimizeConfig.value.llm_model}, timeout=${optimizeConfig.value.effective_llm_timeout_seconds || optimizeConfig.value.llm_timeout_seconds}s.`
        );
      } else {
        const activeGpModel = optimizeConfig.value.effective_model_id || optimizeConfig.value.model_id || "lightweight mode";
        pushOptimizerLog(
          `Using GP profile=${optimizeConfig.value.effective_gp_profile || optimizeConfig.value.gp_profile}, rounds=${optimizeConfig.value.effective_rounds || optimizeConfig.value.rounds}, model=${activeGpModel}.`
        );
      }
      pushOptimizerLog(`Sending request to ${endpoint} ...`);

      let res;
      try {
        res = await apiFetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(promptPayload(fields)),
        });
      } catch (err) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Optimization request failed before response.";
        pushOptimizerLog("Request failed: network/server error.", "error");
        return;
      }

      if (!res.ok) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        let details = "";
        try {
          details = await res.text();
        } catch (err) {
          details = "";
        }
        optimizerError.value = "Optimization failed (" + res.status + ")";
        pushOptimizerLog(
          `Optimization failed with HTTP ${res.status}${details ? `: ${details.slice(0, 220)}` : ""}`,
          "error"
        );
        return;
      }

      pushOptimizerLog(`Response received (HTTP ${res.status}). Parsing payload ...`);

      let data;
      try {
        data = await res.json();
      } catch (err) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Optimization response is not valid JSON.";
        pushOptimizerLog("Response parse failed: invalid JSON payload.", "error");
        return;
      }

      optimizerLoading.value = false;
      optimizerEngine.value = data.engine || "greaterprompt";
      optimizerNotes.value = data.notes || [];
      optimizerStatus.value = optimizerEngine.value.includes("fallback")
        ? "Optimization finished with fallback"
        : "Optimization completed";

      pushOptimizerLog(`Completed. Engine: ${optimizerEngine.value}.`, optimizerEngine.value.includes("fallback") ? "warn" : "success");
      if (Array.isArray(optimizerNotes.value) && optimizerNotes.value.length) {
        optimizerNotes.value.forEach((note) => {
          const level = String(note || "").toLowerCase().includes("failed") ? "warn" : "info";
          pushOptimizerLog(String(note), level);
        });
      }

      optimizedMarkdown.value = data.optimized_markdown || "";
      optimizedDraft.value = {
        role: data.optimized.role || "",
        task: data.optimized.task || "",
        context: data.optimized.context || "",
        constraints: data.optimized.constraints || "",
        output_format: data.optimized.output_format || "",
        examples: data.optimized.examples || "",
      };
    };

    const reoptimizePrompt = async () => {
      optimizerError.value = "";
      pushOptimizerLog("Reoptimize clicked. Saving config before restart ...");
      const saved = await persistOptimizeConfig(false);
      if (!saved) {
        optimizerStatus.value = "Reoptimize failed";
        optimizerError.value = "Reoptimize failed: unable to save optimization config.";
        pushOptimizerLog("Failed to save optimization config before reoptimize.", "error");
        return;
      }

      pushOptimizerLog("Config saved. Restarting optimization ...");

      await optimizePrompt(
        optimizeEndpoint.value,
        optimizedDraft.value,
        optimizeInputSource.value,
        optimizeTargetPrompt.value
      );
    };

    const optimizeFromCreate = async () => {
      createOptimizeMenuOpen.value = false;
      await optimizePrompt("/optimize/greaterprompt", form.value, "create", null);
    };

    const optimizeFromCreateLLM = async () => {
      createOptimizeMenuOpen.value = false;
      await optimizePrompt("/optimize/llm", form.value, "create", null);
    };

    const optimizeFromBrowse = async (p) => {
      browseOptimizeMenuKey.value = null;
      await optimizePrompt(
        "/optimize/greaterprompt",
        {
          role: p.role || "",
          task: p.task || "",
          context: p.context || "",
          constraints: p.constraints || "",
          output_format: p.output_format || "",
          examples: p.examples || "",
        },
        "browse",
        { project: p.project, name: p.name }
      );
    };

    const optimizeFromBrowseLLM = async (p) => {
      browseOptimizeMenuKey.value = null;
      await optimizePrompt(
        "/optimize/llm",
        {
          role: p.role || "",
          task: p.task || "",
          context: p.context || "",
          constraints: p.constraints || "",
          output_format: p.output_format || "",
          examples: p.examples || "",
        },
        "browse",
        { project: p.project, name: p.name }
      );
    };

    const applyOptimizedPrompt = async () => {
      if (optimizeInputSource.value === "create") {
        form.value.role = optimizedDraft.value.role || "";
        form.value.task = optimizedDraft.value.task || "";
        form.value.context = optimizedDraft.value.context || "";
        form.value.constraints = optimizedDraft.value.constraints || "";
        form.value.output_format = optimizedDraft.value.output_format || "";
        form.value.examples = optimizedDraft.value.examples || "";
        optimizerModalOpen.value = false;
        return;
      }

      const target = optimizeTargetPrompt.value;
      if (!target) {
        optimizerError.value = "No prompt selected for update.";
        return;
      }

      const res = await apiFetch("/prompts/" + target.project + "/" + target.name, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(promptPayload(optimizedDraft.value)),
      });

      if (!res.ok) {
        optimizerError.value = "Update failed (" + res.status + ")";
        return;
      }

      await fetchPrompts();
      const updated = items.value.find((i) => key(i) === expandedKey.value);
      if (updated) {
        await loadVersions(updated);
      }
      optimizerModalOpen.value = false;
      saveStatus.value = "Version saved";
    };

    onMounted(async () => {
      await fetchAuthStatus();
      if (await loadCurrentUser()) {
        await initializeAuthenticatedApp();
      }
      authReady.value = true;
    });

    return {
      authReady, authToken, currentUser, authMode, authForm, authError, authStatus, authBusy, authBootstrapRequired, isAuthenticated, isAdmin, currentUserProjectsLabel,
      activeTab, form, createStatus,
      items, filterProject, filterTag, fetchPrompts, browsePage, browsePageSize, browseTotalItems, totalBrowsePages, paginatedItems, setBrowsePage, browseSummaryLabel,
      expandedKey, expandedVersions, openVersionKey,
      editTagsMode, editTagsStr, newVersionRole, newVersionTask, newVersionContext, newVersionConstraints, newVersionOutputFormat, newVersionExamples, saveStatus,
      newVersionEditorOpen,
      createOptimizeMenuOpen, browseOptimizeMenuKey,
      optimizerModalOpen, optimizerLoading, optimizerError, optimizerStatus, optimizerMode, optimizerLogs, optimizerEngine, optimizerNotes,
      optimizedMarkdown, optimizedDraft,
      optimizeConfig, optimizeConfigStatus, llmProviderOptions, availableLlmModels, llmModelsLoading, llmModelsLoadError, gpProfileOptions,
      roleOptions, projects, projectsLoading, projectsStatus, newProjectForm, editingProjectId, editProjectForm,
      users, usersLoading, usersStatus, newUserForm, editingUserId, editUserForm, availableProjectNames,
      gpRecommendedModels, gpRecommendedModelGroups, gpModelsByGroup, selectedGpModelMeta,
      key, togglePrompt, saveNewVersion, saveTags, createPrompt,
      deletePrompt,
      optimizeFromCreate, optimizeFromCreateLLM,
      optimizeFromBrowse, optimizeFromBrowseLLM,
      applyOptimizedPrompt, reoptimizePrompt, saveOptimizeConfig, loadAvailableLlmModels, updateProviderBaseUrl, getProviderLabel, modelRequiresToken,
      submitAuth, logout, createProjectRecord, beginEditProject, cancelProjectEdit, saveProjectEdit, deleteProjectRecord,
      createUserAccount, beginEditUser, cancelUserEdit, saveUserEdit, deleteUserAccount, loadUsers, loadProjects,
      toggleProjectSelection, isProjectSelected,
      md, buildPromptMarkdown,
      deleteStatus,
    };
  },

  template: `
    <div v-if="!authReady" class="auth-shell">
      <div class="auth-card">
        <h1>Prompt Man</h1>
        <p class="subtitle">Loading session...</p>
      </div>
    </div>

    <div v-else-if="!isAuthenticated" class="auth-shell">
      <div class="auth-card">
        <h1>Prompt Man</h1>
        <p class="subtitle">{{ authBootstrapRequired ? 'Create the first admin account for this workspace.' : 'Sign in to access prompts and personal optimization config.' }}</p>
        <div class="field">
          <label>Username</label>
          <input v-model="authForm.username" placeholder="admin" />
        </div>
        <div class="field">
          <label>Password</label>
          <input type="password" v-model="authForm.password" placeholder="Enter password" @keyup.enter="submitAuth" />
        </div>
        <div class="btn-row auth-actions">
          <button @click="submitAuth" :disabled="authBusy || !authForm.username.trim() || !authForm.password">{{ authBusy ? 'Please wait...' : (authMode === 'bootstrap' ? 'Create Admin' : 'Sign In') }}</button>
          <button class="ghost" v-if="!authBootstrapRequired" @click="authMode='login'">Use login</button>
        </div>
        <p v-if="authStatus" class="status-ok">{{ authStatus }}</p>
        <p v-if="authError" class="status-err">{{ authError }}</p>
      </div>
    </div>

    <template v-else>
    <header style="margin-bottom:4px">
      <div class="header-topline">
        <div>
          <h1>Prompt Man</h1>
          <p class="subtitle">Versioned prompts with tags, markdown, and per-user optimization config.</p>
        </div>
        <div class="auth-banner">
          <div>
            <div class="auth-banner-user">{{ currentUser.username }}</div>
            <div class="auth-banner-meta">Role: {{ currentUser.role }} | Projects: {{ currentUserProjectsLabel }}</div>
          </div>
          <button class="ghost" @click="logout">Logout</button>
        </div>
      </div>
    </header>

    <div class="tabs">
      <button class="tab-btn" :class="{active: activeTab==='browse'}" @click="activeTab='browse'">Browse</button>
      <button class="tab-btn" :class="{active: activeTab==='create'}" @click="activeTab='create'">+ Create</button>
      <button class="tab-btn" :class="{active: activeTab==='config'}" @click="activeTab='config'">Config</button>
      <button v-if="isAdmin" class="tab-btn" :class="{active: activeTab==='admin'}" @click="activeTab='admin'">Admin</button>
    </div>

    <!-- BROWSE TAB -->
    <div class="tab-panel" v-if="activeTab==='browse'">
      <div class="filter-row">
        <div class="field">
          <label>Project</label>
          <input v-model="filterProject" placeholder="payments" />
        </div>
        <div class="field">
          <label>Tag</label>
          <input v-model="filterTag" placeholder="production" />
        </div>
        <div style="padding-bottom:1px">
          <button class="secondary" @click="fetchPrompts">Refresh</button>
        </div>
      </div>

      <div class="browse-toolbar" v-if="browseTotalItems>0">
        <p class="browse-summary">{{ browseSummaryLabel }}</p>
        <div class="browse-pagination-controls">
          <label class="browse-page-size-label">
            Per page
            <select v-model.number="browsePageSize" @change="fetchPrompts(1)">
              <option :value="5">5</option>
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>
        </div>
      </div>

      <p v-if="browseTotalItems===0" style="color:var(--muted)">No prompts found.</p>

      <div class="prompt-list">
        <div class="prompt-card" v-for="p in paginatedItems" :key="key(p)">

          <div class="prompt-header" @click="togglePrompt(p)">
            <h3>{{ p.project }} / {{ p.name }}</h3>
            <span class="ver-badge">v{{ p.latest_version }}</span>
            <div class="chips" style="margin-top:0; flex:2">
              <span class="chip" v-for="t in p.tags" :key="t">{{ t }}</span>
            </div>
            <span class="expand-icon" :class="{open: expandedKey===key(p)}">&#9660;</span>
          </div>

          <div class="prompt-detail" v-if="expandedKey===key(p)">

            <!-- Tags -->
            <div class="detail-section">
              <h4>Tags</h4>
              <div v-if="!editTagsMode">
                <div class="chips">
                  <span class="chip" v-for="t in p.tags" :key="t">{{ t }}</span>
                  <em v-if="p.tags.length===0" style="color:var(--muted);font-size:0.85rem">none</em>
                </div>
                <div class="btn-row">
                  <button class="ghost" @click="editTagsMode=true; editTagsStr=p.tags.join(', ')">Edit tags</button>
                </div>
              </div>
              <div v-else>
                <div class="field">
                  <label>Tags (comma-separated)</label>
                  <input v-model="editTagsStr" placeholder="alpha, beta, prod" />
                </div>
                <div class="btn-row">
                  <button @click="saveTags(p)">Save tags</button>
                  <button class="ghost" @click="editTagsMode=false">Cancel</button>
                </div>
              </div>
            </div>

            <!-- Latest content rendered as markdown -->
            <div class="detail-section">
              <h4>Latest content &mdash; v{{ p.latest_version }}</h4>
              <div class="md-content" v-html="md(buildPromptMarkdown(p))"></div>
              <div class="btn-row" style="margin-top:12px">
                <div class="split-wrap">
                  <button class="split-btn secondary" @click.stop="optimizeFromBrowse(p)">
                    <span class="split-main-label">Optimize Prompt</span>
                    <span class="split-arrow" @click.stop="browseOptimizeMenuKey = (browseOptimizeMenuKey===key(p) ? null : key(p))">&#9662;</span>
                  </button>
                  <div class="split-menu" v-if="browseOptimizeMenuKey===key(p)">
                    <button class="split-menu-item" @click.stop="optimizeFromBrowse(p)">Optimize with GreaterPrompt</button>
                    <button class="split-menu-item" @click.stop="optimizeFromBrowseLLM(p)">Optimize Prompt with LLM</button>
                  </div>
                </div>
                <button class="danger" @click.stop="deletePrompt(p)">Delete Prompt</button>
              </div>
              <p v-if="deleteStatus" :class="deleteStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ deleteStatus }}</p>
            </div>

            <!-- New version editor -->
            <div class="detail-section">
              <div class="section-title-row">
                <h4 style="margin:0">Create new version</h4>
                <button class="ghost" @click="newVersionEditorOpen = !newVersionEditorOpen">
                  {{ newVersionEditorOpen ? 'Hide' : 'Show' }}
                </button>
              </div>
              <div class="new-version-editor" v-if="newVersionEditorOpen">
                <div class="new-version-group">
                  <p class="new-version-group-title">Prompt components</p>
                  <div class="field">
                    <label>Role (optional)</label>
                    <input v-model="newVersionRole" placeholder="You are a helpful assistant..." />
                  </div>
                  <div class="field">
                    <label>Task (required)</label>
                    <textarea v-model="newVersionTask" style="min-height:160px" placeholder="Generate a summary of..."></textarea>
                  </div>
                  <div class="field">
                    <label>Context (optional)</label>
                    <textarea v-model="newVersionContext" style="min-height:160px" placeholder="Background information, data format, target audience..."></textarea>
                  </div>
                  <div class="field">
                    <label>Constraints (optional)</label>
                    <textarea v-model="newVersionConstraints" style="min-height:80px" placeholder="Limitations, rules, format restrictions..."></textarea>
                  </div>
                  <div class="field">
                    <label>Output Format (optional)</label>
                    <textarea v-model="newVersionOutputFormat" style="min-height:80px" placeholder="JSON, CSV, markdown, bullet points..."></textarea>
                  </div>
                  <div class="field">
                    <label>Examples (optional)</label>
                    <textarea v-model="newVersionExamples" style="min-height:80px" placeholder="Input/output examples..."></textarea>
                  </div>
                </div>
                <div class="new-version-group">
                  <p class="new-version-group-title">Composed preview</p>
                  <div class="field">
                    <div class="md-editor-preview-label">Preview</div>
                    <div class="md-editor-preview" :class="{empty: !newVersionTask}" v-html="newVersionTask ? md(buildPromptMarkdown({role: newVersionRole, task: newVersionTask, context: newVersionContext, constraints: newVersionConstraints, output_format: newVersionOutputFormat, examples: newVersionExamples})) : 'Nothing to preview yet\u2026'"></div>
                  </div>
                </div>
              </div>
              <div class="btn-row">
                <button v-if="newVersionEditorOpen" @click="saveNewVersion(p)">Save as new version</button>
              </div>
              <p v-if="saveStatus" :class="saveStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ saveStatus }}</p>
            </div>

            <!-- Version history -->
            <div class="detail-section">
              <h4>Version history ({{ expandedVersions.length }})</h4>
              <div class="version-list">
                <div class="version-item" v-for="v in expandedVersions.slice().reverse()" :key="v.version">
                  <div class="version-item-header" @click="openVersionKey = (openVersionKey===v.version ? null : v.version)">
                    <span>Version {{ v.version }}</span>
                    <span style="font-size:0.75rem;color:var(--muted)">{{ openVersionKey===v.version ? 'hide' : 'show' }}</span>
                  </div>
                  <div class="version-item-body" v-if="openVersionKey===v.version">
                    <div class="md-content" v-html="md(buildPromptMarkdown(v))"></div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      <div class="browse-pagination" v-if="browseTotalItems > browsePageSize">
        <button class="ghost" :disabled="browsePage===1" @click="setBrowsePage(browsePage - 1)">Previous</button>
        <span class="browse-page-indicator">Page {{ browsePage }} of {{ totalBrowsePages }}</span>
        <button class="ghost" :disabled="browsePage===totalBrowsePages" @click="setBrowsePage(browsePage + 1)">Next</button>
      </div>
    </div>

    <!-- CREATE TAB -->
    <div class="tab-panel" v-if="activeTab==='create'">
      <h2 style="margin-top:0">New Prompt</h2>
      <div class="create-grid">
        <div class="field">
          <label>Name (required)</label>
          <input v-model="form.name" placeholder="checkout-system" required />
        </div>
        <div class="field">
          <label>Project (required)</label>
          <input v-model="form.project" placeholder="payments" required />
        </div>
      </div>
      <div class="field">
        <label>Tags (comma-separated, optional)</label>
        <input v-model="form.tags" placeholder="system, production, v1" />
      </div>
      <fieldset class="group-box">
        <legend>Prompt Data</legend>
        <div class="field">
          <label>Role (optional)</label>
          <input v-model="form.role" placeholder="You are a helpful assistant..." />
        </div>
        <div class="field">
          <label>Task (required)</label>
          <textarea v-model="form.task" style="min-height:160px" placeholder="Generate a summary of..."></textarea>
        </div>
        <div class="field">
          <label>Context (optional)</label>
          <textarea v-model="form.context" style="min-height:160px" placeholder="Background information, data format, target audience..."></textarea>
        </div>
        <div class="field">
          <label>Constraints (optional)</label>
          <textarea v-model="form.constraints" style="min-height:80px" placeholder="Limitations, rules, format restrictions..."></textarea>
        </div>
        <div class="field">
          <label>Output format (optional)</label>
          <textarea v-model="form.output_format" style="min-height:80px" placeholder="JSON, CSV, markdown, bullet points..."></textarea>
        </div>
        <div class="field">
          <label>Examples (optional)</label>
          <textarea v-model="form.examples" style="min-height:80px" placeholder="Input/output examples..."></textarea>
        </div>
      </fieldset>
      <div class="field">
        <div class="md-editor-preview-label">Preview</div>
        <div class="md-editor-preview" :class="{empty: !form.task}" v-html="form.task ? md(buildPromptMarkdown(form)) : 'Nothing to preview yet\u2026'"></div>
      </div>
      <div class="btn-row">
        <div class="split-wrap">
          <button class="split-btn secondary" @click.stop="optimizeFromCreate">
            <span class="split-main-label">Optimize Prompt</span>
            <span class="split-arrow" @click.stop="createOptimizeMenuOpen = !createOptimizeMenuOpen">&#9662;</span>
          </button>
          <div class="split-menu" v-if="createOptimizeMenuOpen">
            <button class="split-menu-item" @click.stop="optimizeFromCreate">Optimize with GreaterPrompt</button>
            <button class="split-menu-item" @click.stop="optimizeFromCreateLLM">Optimize Prompt with LLM</button>
          </div>
        </div>
        <button @click="createPrompt">Save Prompt</button>
      </div>
      <p v-if="createStatus" :class="createStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ createStatus }}</p>
    </div>

    <!-- CONFIG TAB -->
    <div class="tab-panel" v-if="activeTab==='config'">
      <h2 style="margin-top:0">Optimization Config</h2>
      <p style="margin:0 0 12px;color:var(--muted)">Manage active settings for LLM and GreaterPrompt optimization. These settings are stored per user.</p>

      <div class="opt-config-box opt-config-box-standalone">
        <div class="opt-settings-group">
          <h5>LLM Settings</h5>
          <div class="opt-settings-toolbar">
            <button
              class="ghost opt-refresh-btn"
              @click="loadAvailableLlmModels(optimizeConfig.llm_provider)"
              :disabled="llmModelsLoading"
              title="Refresh available models for current API key"
            >
              {{ llmModelsLoading ? "Loading..." : "Refresh Models" }}
            </button>
          </div>
          <div class="create-grid">
            <div class="field">
              <label>LLM Provider</label>
              <select class="select-pretty" v-model="optimizeConfig.llm_provider" @change="updateProviderBaseUrl(optimizeConfig.llm_provider); loadAvailableLlmModels(optimizeConfig.llm_provider, false)">
                <option v-for="provider in llmProviderOptions" :key="provider" :value="provider">{{ getProviderLabel(provider) }}</option>
              </select>
            </div>
            <div class="field">
              <label>LLM Model</label>
              <select class="select-pretty" v-model="optimizeConfig.llm_model" :disabled="llmModelsLoading">
                <option v-for="m in availableLlmModels" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
          </div>
          <div class="create-grid">
            <div class="field">
              <label>Base URL</label>
              <input v-model="optimizeConfig.llm_base_url" @change="loadAvailableLlmModels(optimizeConfig.llm_provider)" placeholder="http://127.0.0.1:11434" />
            </div>
            <div class="field" v-if="modelRequiresToken()" style="max-width:220px">
              <label>API Token</label>
              <input type="password" v-model="optimizeConfig.llm_api_token" :placeholder="optimizeConfig.effective_has_llm_api_token ? 'Token already set' : 'Enter your API token'" />
              <p v-if="optimizeConfig.effective_has_llm_api_token" style="margin:4px 0 0;color:var(--muted);font-size:0.82rem">✓ Token is configured</p>
            </div>
            <div class="field" v-else style="max-width:220px">
              <label>LLM Timeout (seconds)</label>
              <input type="number" min="5" v-model.number="optimizeConfig.llm_timeout_seconds" />
            </div>
          </div>
          <div class="create-grid" v-if="modelRequiresToken()">
            <div class="field" style="max-width:220px">
              <label>LLM Timeout (seconds)</label>
              <input type="number" min="5" v-model.number="optimizeConfig.llm_timeout_seconds" />
            </div>
          </div>
          <p v-if="llmModelsLoading" style="margin:4px 0 0;color:var(--muted);font-size:0.84rem">Loading available models...</p>
          <p v-if="llmModelsLoadError" style="margin:4px 0 0;color:var(--muted);font-size:0.84rem">{{ llmModelsLoadError }}</p>
        </div>

        <div class="opt-settings-group opt-settings-group-gp">
          <h5>GreaterPrompt Settings</h5>
          <div class="create-grid">
            <div class="field">
              <label>GreaterPrompt Profile</label>
              <select class="select-pretty" v-model="optimizeConfig.gp_profile">
                <option v-for="p in gpProfileOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="field">
              <label>GreaterPrompt Model (optional)</label>
              <select class="select-pretty" v-model="optimizeConfig.model_id">
                <option value="">No model selected (lightweight mode)</option>
                <optgroup v-for="group in gpRecommendedModelGroups" :key="group" :label="group">
                  <option
                    v-for="model in gpModelsByGroup[group]"
                    :key="model.value"
                    :value="model.value"
                  >
                    {{ model.label }}{{ model.recommended ? ' - recommended' : '' }}
                  </option>
                </optgroup>
              </select>
              <p class="gp-model-hint" v-if="selectedGpModelMeta">
                {{ selectedGpModelMeta.label }}: {{ selectedGpModelMeta.bestUse }} | VRAM {{ selectedGpModelMeta.vram }}
              </p>
              <p class="gp-model-hint" v-else>
                Empty value keeps GreaterPrompt in lightweight mode without loading a local gradient model.
              </p>
            </div>
          </div>
          <div class="field" style="max-width:180px">
            <label>Gradient Rounds</label>
            <input type="number" min="1" v-model.number="optimizeConfig.rounds" />
          </div>
          <div class="gp-model-table-wrap">
            <div class="gp-model-table-title">Recommended Models</div>
            <div class="gp-model-cards gp-model-cards-empty">
              <button
                type="button"
                class="gp-model-card gp-model-card-empty"
                :class="{ active: !optimizeConfig.model_id }"
                @click="optimizeConfig.model_id = ''"
              >
                <div class="gp-model-card-top">
                  <div class="gp-model-card-title">No model</div>
                  <span class="gp-model-support gp-model-support-light">Lightweight</span>
                </div>
                <div class="gp-model-card-meta">Runs without loading a gradient model</div>
                <div class="gp-model-card-grid">
                  <div><span>Quality</span><strong>Lightweight</strong></div>
                  <div><span>Speed</span><strong>Fastest</strong></div>
                  <div><span>VRAM</span><strong>Minimal</strong></div>
                  <div><span>Use</span><strong>Heuristic mode</strong></div>
                </div>
              </button>
            </div>

            <div
              class="gp-model-group"
              v-for="group in gpRecommendedModelGroups"
              :key="group"
            >
              <div class="gp-model-group-title">{{ group }}</div>
              <div class="gp-model-cards">
                <button
                  type="button"
                  class="gp-model-card"
                  :class="{
                    active: optimizeConfig.model_id === model.value,
                    'gp-model-card-supported': model.supported === '✔',
                    'gp-model-card-compatible': model.supported !== '✔'
                  }"
                  v-for="model in gpModelsByGroup[group]"
                  :key="model.value"
                  @click="optimizeConfig.model_id = model.value"
                >
                  <div class="gp-model-card-top">
                    <div>
                      <div class="gp-model-card-title">{{ model.label }}</div>
                      <div class="gp-model-card-group">{{ model.group }}</div>
                    </div>
                    <div class="gp-model-card-badges">
                      <span class="gp-model-support" :class="model.supported === '✔' ? 'gp-model-support-official' : 'gp-model-support-compatible'">
                        {{ model.supported === '✔' ? 'Official' : 'Compatible' }}
                      </span>
                      <span class="gp-model-badge" v-if="model.recommended">Recommended</span>
                    </div>
                  </div>
                  <div class="gp-model-card-meta">{{ model.supported === '✔' ? 'Official GreaterPrompt support' : 'Works as a compatible alternative' }}</div>
                  <div class="gp-model-card-grid">
                    <div><span>Quality</span><strong>{{ model.quality }}</strong></div>
                    <div><span>Speed</span><strong>{{ model.speed }}</strong></div>
                    <div><span>VRAM</span><strong>{{ model.vram }}</strong></div>
                    <div><span>Best use</span><strong>{{ model.bestUse }}</strong></div>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="btn-row" style="margin-top:12px">
          <button class="secondary" @click="saveOptimizeConfig">Save Config</button>
        </div>
        <p v-if="optimizeConfigStatus" :class="optimizeConfigStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ optimizeConfigStatus }}</p>
        <p style="margin:6px 0 0;color:var(--muted);font-size:0.84rem">
          Active GP profile: {{ optimizeConfig.effective_gp_profile }} | Active LLM model: {{ optimizeConfig.effective_llm_model }} | Active provider: {{ optimizeConfig.effective_llm_provider }} | Timeout: {{ optimizeConfig.effective_llm_timeout_seconds }}s
        </p>
      </div>

      <div v-if="isAdmin" class="admin-panel">
        <div class="admin-panel-header">
          <div>
            <h3>Admin tools moved</h3>
            <p>Project and user management are now available in the dedicated Admin tab.</p>
          </div>
          <button class="secondary" @click="activeTab='admin'">Open Admin</button>
        </div>
      </div>
    </div>

    <div class="tab-panel" v-if="activeTab==='admin' && isAdmin">
      <div class="admin-panel" style="margin-top:0;border-top:none;padding-top:0">
        <div class="admin-panel-header">
          <div>
            <h3>Administration</h3>
            <p>Manage projects, users, and project access rights.</p>
          </div>
          <button class="ghost" @click="Promise.all([loadRoles(), loadProjects(), loadUsers()])" :disabled="usersLoading || projectsLoading">{{ (usersLoading || projectsLoading) ? 'Loading...' : 'Refresh Admin Data' }}</button>
        </div>

        <div class="admin-grid">
          <div class="admin-card">
            <h4>Projects</h4>
            <div class="field">
              <label>New Project Name</label>
              <input v-model="newProjectForm.name" placeholder="payments" />
            </div>
            <div class="btn-row">
              <button class="secondary" @click="createProjectRecord">Create Project</button>
            </div>
            <p v-if="projectsStatus" :class="projectsStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ projectsStatus }}</p>
            <p v-if="!projects.length && !projectsLoading" style="color:var(--muted)">No projects yet.</p>
            <div class="project-list">
              <div class="project-row" v-for="project in projects" :key="project.id">
                <div v-if="editingProjectId===project.id" class="project-edit-row">
                  <input v-model="editProjectForm.name" />
                  <div class="btn-row">
                    <button class="secondary" @click="saveProjectEdit(project.id)">Save</button>
                    <button class="ghost" @click="cancelProjectEdit">Cancel</button>
                  </div>
                </div>
                <div v-else class="project-row-static">
                  <div class="project-name">{{ project.name }}</div>
                  <div class="btn-row">
                    <button class="ghost" @click="beginEditProject(project)">Rename</button>
                    <button class="danger" @click="deleteProjectRecord(project)">Delete</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="admin-card">
            <h4>Create User</h4>
            <div class="field">
              <label>Username</label>
              <input v-model="newUserForm.username" placeholder="developer-1" />
            </div>
            <div class="field">
              <label>Password</label>
              <input type="password" v-model="newUserForm.password" placeholder="Temporary password" />
            </div>
            <div class="create-grid">
              <div class="field">
                <label>Role</label>
                <select class="select-pretty" v-model="newUserForm.role">
                  <option v-for="roleName in roleOptions" :key="roleName" :value="roleName">{{ roleName }}</option>
                </select>
              </div>
              <div class="field">
                <label>Status</label>
                <select class="select-pretty" v-model="newUserForm.is_active">
                  <option :value="true">active</option>
                  <option :value="false">inactive</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label>Projects</label>
              <div class="project-selector" v-if="availableProjectNames.length">
                <button
                  type="button"
                  class="project-pill"
                  :class="{ active: isProjectSelected(newUserForm, projectName) }"
                  v-for="projectName in availableProjectNames"
                  :key="projectName"
                  @click="toggleProjectSelection(newUserForm, projectName)"
                >
                  {{ projectName }}
                </button>
              </div>
              <p v-else class="project-selector-empty">Create at least one project before assigning rights.</p>
            </div>
            <div class="btn-row">
              <button class="secondary" @click="createUserAccount">Create User</button>
            </div>
          </div>

          <div class="admin-card admin-card-wide admin-card-full">
            <h4>Existing Users</h4>
            <p v-if="usersStatus" :class="usersStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ usersStatus }}</p>
            <p v-if="!users.length && !usersLoading" style="color:var(--muted)">No users found.</p>
            <div class="user-list">
              <div class="user-card" v-for="user in users" :key="user.id">
                <div class="user-card-header">
                  <div>
                    <div class="user-card-title">{{ user.username }}</div>
                    <div class="user-card-meta">Role: {{ user.role }} | {{ user.is_active ? 'active' : 'inactive' }}</div>
                  </div>
                  <div class="chips">
                    <span class="chip" v-for="project in user.projects" :key="project">{{ project }}</span>
                    <span class="chip" v-if="!user.projects.length">all / none assigned</span>
                  </div>
                </div>

                <div v-if="editingUserId===user.id" class="user-editor">
                  <div class="field">
                    <label>Username</label>
                    <input v-model="editUserForm.username" />
                  </div>
                  <div class="create-grid">
                    <div class="field">
                      <label>Role</label>
                      <select class="select-pretty" v-model="editUserForm.role">
                        <option v-for="roleName in roleOptions" :key="roleName" :value="roleName">{{ roleName }}</option>
                      </select>
                    </div>
                    <div class="field">
                      <label>Status</label>
                      <select class="select-pretty" v-model="editUserForm.is_active">
                        <option :value="true">active</option>
                        <option :value="false">inactive</option>
                      </select>
                    </div>
                  </div>
                  <div class="field">
                    <label>New Password (optional)</label>
                    <input type="password" v-model="editUserForm.password" placeholder="Leave empty to keep current password" />
                  </div>
                  <div class="field">
                    <label>Projects</label>
                    <div class="project-selector" v-if="availableProjectNames.length">
                      <button
                        type="button"
                        class="project-pill"
                        :class="{ active: isProjectSelected(editUserForm, projectName) }"
                        v-for="projectName in availableProjectNames"
                        :key="projectName"
                        @click="toggleProjectSelection(editUserForm, projectName)"
                      >
                        {{ projectName }}
                      </button>
                    </div>
                    <p v-else class="project-selector-empty">Create at least one project before assigning rights.</p>
                  </div>
                  <div class="btn-row">
                    <button class="secondary" @click="saveUserEdit(user.id)">Save</button>
                    <button class="ghost" @click="cancelUserEdit">Cancel</button>
                  </div>
                </div>

                <div v-else class="btn-row">
                  <button class="ghost" @click="beginEditUser(user)">Edit</button>
                  <button class="danger" :disabled="currentUser.id===user.id" @click="deleteUserAccount(user)">Delete</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="modal-backdrop" v-if="optimizerModalOpen" @click.self="optimizerModalOpen=false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Prompt Optimization</h3>
          <button class="ghost" @click="optimizerModalOpen=false">Close</button>
        </div>

        <p class="status-err" v-if="optimizerError">{{ optimizerError }}</p>
        <p v-if="optimizerStatus" style="margin:0 0 8px;color:var(--muted)">
          Status: {{ optimizerStatus }}
        </p>
        <p v-if="optimizerLoading" style="margin:0 0 10px;color:var(--muted)">Optimization is running on backend ...</p>

        <div class="optimizer-log-box">
          <div class="optimizer-log-title">Execution log</div>
          <div class="optimizer-log-empty" v-if="!optimizerLogs.length">No log entries yet.</div>
          <div
            class="optimizer-log-line"
            v-for="(entry, idx) in optimizerLogs"
            :key="idx"
            :class="'log-' + entry.level"
          >
            [{{ entry.ts }}] {{ entry.message }}
          </div>
        </div>

        <div v-if="!optimizerLoading">
          <p style="margin:0 0 8px;color:var(--muted)">Mode: {{ optimizerMode === 'llm' ? 'LLM' : 'GreaterPrompt' }}</p>
          <p style="margin:0 0 8px;color:var(--muted)">Engine: {{ optimizerEngine }}</p>
          <p style="margin:0 0 10px;color:var(--muted);font-size:0.9rem">
            Active GP profile: {{ optimizeConfig.effective_gp_profile }} | Active LLM model: {{ optimizeConfig.effective_llm_model }} | Active provider: {{ optimizeConfig.effective_llm_provider }} | Timeout: {{ optimizeConfig.effective_llm_timeout_seconds }}s
          </p>

          <div class="chips" v-if="optimizerNotes.length">
            <span class="chip" v-for="(note, idx) in optimizerNotes" :key="idx">{{ note }}</span>
          </div>
          <div class="md-content" style="margin-top:10px" v-html="md(optimizedMarkdown || buildPromptMarkdown(optimizedDraft))"></div>
          <div class="btn-row" style="margin-top:12px">
            <button class="secondary" :disabled="optimizerLoading" @click="reoptimizePrompt">Reoptimize</button>
            <button @click="applyOptimizedPrompt">Update Prompt</button>
          </div>
        </div>
      </div>
    </div>
    </template>
  `,
}).mount("#app");
