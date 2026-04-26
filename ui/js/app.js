const { createApp, ref, computed, onMounted } = Vue;

marked.setOptions({ breaks: true, gfm: true });
const md        = (text) => marked.parse(text || "");
const parseTags = (raw)  => raw.split(",").map((t) => t.trim()).filter(Boolean);
const tagsToStr = (tags) => tags.join(", ");
const key       = (p)   => p.project + "/" + p.name;
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
  effective_model_id: "",
  effective_rounds: 2,
  effective_gp_profile: "fast",
  effective_llm_provider: "ollama",
  effective_llm_model: "qwen2.5:0.5b",
  effective_llm_base_url: "http://127.0.0.1:11434",
  effective_llm_timeout_seconds: 300,
});
const gpProfileOptions = ["fast", "quality"];
const llmModelOptions = [
  "qwen2.5:0.5b",
  "phi3:mini",
  "llama3.2:1b",
  "qwen2.5:1.5b",
  "gemma2:2b",
];

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

    /* optimizer */
    const createOptimizeMenuOpen = ref(false);
    const browseOptimizeMenuKey = ref(null);
    const optimizerModalOpen = ref(false);
    const optimizerLoading = ref(false);
    const optimizerError = ref("");
    const optimizerEngine = ref("");
    const optimizerNotes = ref([]);
    const optimizedMarkdown = ref("");
    const optimizedDraft = ref(emptyPromptData());
    const optimizeInputSource = ref("create");
    const optimizeTargetPrompt = ref(null);
    const optimizeConfig = ref(defaultOptimizeConfig());
    const optimizeConfigStatus = ref("");

    const fetchPrompts = async (page = browsePage.value) => {
      browsePage.value = Math.max(1, page);
      const p = new URLSearchParams();
      if (filterProject.value.trim()) p.set("project", filterProject.value.trim());
      if (filterTag.value.trim())     p.set("tag",     filterTag.value.trim());
      p.set("limit", String(browsePageSize.value));
      p.set("offset", String((browsePage.value - 1) * browsePageSize.value));
      const q   = p.toString();
      const res = await fetch("/prompts" + (q ? "?" + q : ""));
      if (!res.ok) return;
      items.value = await res.json();
      browseTotalItems.value = Number(res.headers.get("X-Total-Count") || items.value.length || 0);
    };

    const totalBrowsePages = computed(() => {
      const total = Math.ceil(browseTotalItems.value / browsePageSize.value);
      return Math.max(1, total);
    });

    const paginatedItems = computed(() => items.value);

    const setBrowsePage = async (page) => {
      const nextPage = Math.min(Math.max(1, page), totalBrowsePages.value);
      await fetchPrompts(nextPage);
    };

    const browseRangeLabel = computed(() => {
      if (!browseTotalItems.value || !items.value.length) {
        return "Showing 0 of 0";
      }
      const currentPage = Math.min(browsePage.value, totalBrowsePages.value);
      const start = (currentPage - 1) * browsePageSize.value + 1;
      const end = Math.min(start + items.value.length - 1, browseTotalItems.value);
      return `Showing ${start}-${end} of ${browseTotalItems.value}`;
    });

    const loadVersions = async (p) => {
      const res = await fetch("/prompts/" + p.project + "/" + p.name + "/versions");
      expandedVersions.value = res.ok ? await res.json() : [];
    };

    const togglePrompt = async (p) => {
      const k = key(p);
      if (expandedKey.value === k) {
        expandedKey.value = null; expandedVersions.value = [];
        openVersionKey.value = null; editTagsMode.value = false;
        newVersionRole.value = ""; newVersionTask.value = ""; newVersionContext.value = "";
        newVersionConstraints.value = ""; newVersionOutputFormat.value = ""; newVersionExamples.value = "";
        saveStatus.value = "";
        return;
      }
      expandedKey.value       = k;
      editTagsMode.value      = false;
      editTagsStr.value       = tagsToStr(p.tags);
      newVersionRole.value    = p.role || "";
      newVersionTask.value    = p.task || "";
      newVersionContext.value = p.context || "";
      newVersionConstraints.value = p.constraints || "";
      newVersionOutputFormat.value = p.output_format || "";
      newVersionExamples.value = p.examples || "";
      saveStatus.value        = "";
      openVersionKey.value    = null;
      await loadVersions(p);
    };

    const saveNewVersion = async (p) => {
      saveStatus.value = "";
      const res = await fetch("/prompts/" + p.project + "/" + p.name, {
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
      const res = await fetch("/prompts/" + p.project + "/" + p.name + "/tags", {
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
      const payload = {
        name:    form.value.name.trim(),
        project: form.value.project.trim(),
        tags:    parseTags(form.value.tags),
        role:    form.value.role || null,
        task:    form.value.task,
        context: form.value.context || null,
        constraints: form.value.constraints || null,
        output_format: form.value.output_format || null,
        examples: form.value.examples || null,
      };
      const res = await fetch("/prompts", {
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

    const loadOptimizeConfig = async () => {
      const res = await fetch("/optimize/config");
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
      };
    };

    const saveOptimizeConfig = async () => {
      optimizeConfigStatus.value = "";
      const payload = {
        model_id: optimizeConfig.value.model_id || null,
        rounds: Number(optimizeConfig.value.rounds) || 2,
        gp_profile: optimizeConfig.value.gp_profile || "fast",
        llm_provider: optimizeConfig.value.llm_provider || "ollama",
        llm_model: optimizeConfig.value.llm_model || "qwen2.5:0.5b",
        llm_base_url: optimizeConfig.value.llm_base_url || "http://127.0.0.1:11434",
        llm_timeout_seconds: Number(optimizeConfig.value.llm_timeout_seconds) || 300,
      };
      const res = await fetch("/optimize/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        optimizeConfigStatus.value = "Failed to save optimize config (" + res.status + ")";
        return;
      }
      optimizeConfigStatus.value = "Optimize config saved";
      await loadOptimizeConfig();
    };

    const optimizePrompt = async (endpoint, fields, source, target = null) => {
      optimizerLoading.value = true;
      optimizerError.value = "";
      optimizerEngine.value = "";
      optimizerNotes.value = [];
      optimizedMarkdown.value = "";
      optimizeInputSource.value = source;
      optimizeTargetPrompt.value = target;
      optimizerModalOpen.value = true;

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(promptPayload(fields)),
      });

      if (!res.ok) {
        optimizerLoading.value = false;
        optimizerError.value = "Optimization failed (" + res.status + ")";
        return;
      }

      const data = await res.json();
      optimizerLoading.value = false;
      optimizerEngine.value = data.engine || "greaterprompt";
      optimizerNotes.value = data.notes || [];
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

      const res = await fetch("/prompts/" + target.project + "/" + target.name, {
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
      await fetchPrompts();
      await loadOptimizeConfig();
    });

    return {
      activeTab, form, createStatus,
      items, filterProject, filterTag, fetchPrompts, browsePage, browsePageSize, browseTotalItems, totalBrowsePages, paginatedItems, setBrowsePage, browseRangeLabel,
      expandedKey, expandedVersions, openVersionKey,
      editTagsMode, editTagsStr, newVersionRole, newVersionTask, newVersionContext, newVersionConstraints, newVersionOutputFormat, newVersionExamples, saveStatus,
      createOptimizeMenuOpen, browseOptimizeMenuKey,
      optimizerModalOpen, optimizerLoading, optimizerError, optimizerEngine, optimizerNotes,
      optimizedMarkdown, optimizedDraft,
      optimizeConfig, optimizeConfigStatus, llmModelOptions, gpProfileOptions,
      key, togglePrompt, saveNewVersion, saveTags, createPrompt,
      optimizeFromCreate, optimizeFromCreateLLM,
      optimizeFromBrowse, optimizeFromBrowseLLM,
      applyOptimizedPrompt, saveOptimizeConfig,
      md, buildPromptMarkdown,
    };
  },

  template: `
    <header style="margin-bottom:4px">
      <h1>Prompt Manager</h1>
      <p class="subtitle">Versioned prompts with tags &amp; markdown.</p>
    </header>

    <div class="tabs">
      <button class="tab-btn" :class="{active: activeTab==='browse'}" @click="activeTab='browse'">Browse</button>
      <button class="tab-btn" :class="{active: activeTab==='create'}" @click="activeTab='create'">+ Create</button>
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
        <p class="browse-summary">{{ browseRangeLabel }}</p>
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
              </div>
            </div>

            <!-- New version editor -->
            <div class="detail-section">
              <h4>Create new version</h4>
              <div class="create-grid">
                <div class="field">
                  <label>Role (optional)</label>
                  <input v-model="newVersionRole" placeholder="You are a helpful assistant..." />
                </div>
                <div class="field">
                  <label>Task (required)</label>
                  <input v-model="newVersionTask" placeholder="Generate a summary of..." />
                </div>
              </div>
              <div class="field">
                <label>Context (optional)</label>
                <textarea v-model="newVersionContext" style="min-height:80px" placeholder="Background information, data format, target audience..."></textarea>
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
              <div class="field">
                <div class="md-editor">
                  <div>
                    <div class="md-editor-preview-label">Preview</div>
                    <div class="md-editor-preview" :class="{empty: !newVersionTask}" v-html="newVersionTask ? md(buildPromptMarkdown({role: newVersionRole, task: newVersionTask, context: newVersionContext, constraints: newVersionConstraints, output_format: newVersionOutputFormat, examples: newVersionExamples})) : 'Nothing to preview yet\u2026'"></div>
                  </div>
                </div>
              </div>
              <div class="btn-row">
                <button @click="saveNewVersion(p)">Save as new version</button>
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
          <label>Name</label>
          <input v-model="form.name" placeholder="checkout-system" />
        </div>
        <div class="field">
          <label>Project</label>
          <input v-model="form.project" placeholder="payments" />
        </div>
      </div>
      <div class="field">
        <label>Tags (comma-separated, optional)</label>
        <input v-model="form.tags" placeholder="system, production, v1" />
      </div>
      <fieldset class="group-box">
        <legend>Prompt Data</legend>
        <div class="create-grid">
          <div class="field">
            <label>Role (optional)</label>
            <input v-model="form.role" placeholder="You are a helpful assistant..." />
          </div>
          <div class="field">
            <label>Task (required)</label>
            <input v-model="form.task" placeholder="Generate a summary of..." />
          </div>
        </div>
        <div class="field">
          <label>Context (optional)</label>
          <textarea v-model="form.context" style="min-height:80px" placeholder="Background information, data format, target audience..."></textarea>
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
        <div class="md-editor">
          <div>
            <div class="md-editor-preview-label">Preview</div>
            <div class="md-editor-preview" :class="{empty: !form.task}" v-html="form.task ? md(buildPromptMarkdown(form)) : 'Nothing to preview yet\u2026'"></div>
          </div>
        </div>
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

    <div class="modal-backdrop" v-if="optimizerModalOpen" @click.self="optimizerModalOpen=false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Prompt Optimization</h3>
          <button class="ghost" @click="optimizerModalOpen=false">Close</button>
        </div>

        <p class="status-err" v-if="optimizerError">{{ optimizerError }}</p>
        <p v-else-if="optimizerLoading" style="color:var(--muted)">Optimizing prompt...</p>

        <div v-else>
          <p style="margin:0 0 8px;color:var(--muted)">Engine: {{ optimizerEngine }}</p>

          <div class="opt-config-box">
            <h4 style="margin:0 0 8px">Optimization Config</h4>
            <div class="create-grid">
              <div class="field">
                <label>LLM Provider</label>
                <input v-model="optimizeConfig.llm_provider" placeholder="ollama" />
              </div>
              <div class="field">
                <label>GreaterPrompt Profile</label>
                <select v-model="optimizeConfig.gp_profile">
                  <option v-for="p in gpProfileOptions" :key="p" :value="p">{{ p }}</option>
                </select>
              </div>
            </div>
            <div class="create-grid">
              <div class="field">
                <label>LLM Model</label>
                <input v-model="optimizeConfig.llm_model" list="llm-model-options" placeholder="qwen2.5:0.5b" />
                <datalist id="llm-model-options">
                  <option v-for="m in llmModelOptions" :key="m" :value="m"></option>
                </datalist>
              </div>
              <div class="field"></div>
            </div>
            <div class="create-grid">
              <div class="field">
                <label>Ollama Base URL</label>
                <input v-model="optimizeConfig.llm_base_url" placeholder="http://127.0.0.1:11434" />
              </div>
              <div class="field">
                <label>GreaterPrompt Model ID (optional)</label>
                <input v-model="optimizeConfig.model_id" placeholder="meta-llama/..." />
              </div>
            </div>
            <div class="field" style="max-width:180px">
              <label>Gradient Rounds</label>
              <input type="number" min="1" v-model.number="optimizeConfig.rounds" />
            </div>
            <div class="field" style="max-width:220px">
              <label>LLM Timeout (seconds)</label>
              <input type="number" min="5" v-model.number="optimizeConfig.llm_timeout_seconds" />
            </div>
            <div class="btn-row" style="margin-top:6px">
              <button class="secondary" @click="saveOptimizeConfig">Save Config</button>
            </div>
            <p v-if="optimizeConfigStatus" :class="optimizeConfigStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ optimizeConfigStatus }}</p>
            <p style="margin:6px 0 0;color:var(--muted);font-size:0.84rem">
              Active GP profile: {{ optimizeConfig.effective_gp_profile }} | Active LLM model: {{ optimizeConfig.effective_llm_model }} | Active provider: {{ optimizeConfig.effective_llm_provider }} | Timeout: {{ optimizeConfig.effective_llm_timeout_seconds }}s
            </p>
          </div>

          <div class="chips" v-if="optimizerNotes.length">
            <span class="chip" v-for="(note, idx) in optimizerNotes" :key="idx">{{ note }}</span>
          </div>
          <div class="md-content" style="margin-top:10px" v-html="md(optimizedMarkdown || buildPromptMarkdown(optimizedDraft))"></div>
          <div class="btn-row" style="margin-top:12px">
            <button @click="applyOptimizedPrompt">Update Prompt</button>
          </div>
        </div>
      </div>
    </div>
  `,
}).mount("#app");
