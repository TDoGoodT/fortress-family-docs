# Fortress — Integration Proposal from External Frameworks

## Executive Summary

After analyzing OpenClaw, Hermes Agent, NemoClaw, and Khoj against Fortress's Skills Engine architecture, the strongest integration opportunities are: (1) a self-improving skills system inspired by Hermes Agent's learning loop — where the agent writes skill documents after solving hard problems, (2) a lightweight PII guard layer inspired by NemoClaw's Privacy Router — critical since Fortress already sends data to cloud LLMs via Bedrock/OpenRouter, (3) intent verification before destructive actions — extending the existing confirmation flow with policy-based validation, and (4) RAG over family documents inspired by Khoj — enabling "search my receipts" or "what did the doctor say" queries. OpenClaw's skill packaging format (SKILL.md + AgentSkills standard) is worth adopting as a convention for Fortress skill documentation, but its Gateway architecture is irrelevant since Fortress already has a working WhatsApp pipeline. NemoClaw's full sandbox isolation is overkill for a single-family system. Khoj's multi-user agent creation is unnecessary.

---

## Analysis per Framework

### OpenClaw

#### What They Do Well
- Skill packaging standard: each skill is a folder with `SKILL.md` (YAML frontmatter + instructions), following the AgentSkills open standard. Skills are discoverable, installable, and shareable via ClawHub registry
- Multi-channel Gateway: single control plane for 20+ messaging platforms with session isolation, presence, and routing
- Security defaults: DM pairing (unknown senders get a pairing code), per-session Docker sandboxes for non-main sessions, allowlists per channel
- Agent workspace with injected prompt files: `AGENTS.md`, `SOUL.md`, `TOOLS.md` — declarative personality and tool configuration
- Skill hierarchy: bundled → managed → workspace skills with priority ordering
- Cron + webhooks built into the Gateway

#### What's Relevant to Fortress
- **Skill documentation standard**: Fortress skills currently have no external documentation format. Adopting a `SKILL.md`-like convention per skill would make the system self-documenting and could enable future skill sharing
- **DM pairing concept**: Fortress currently rejects unknown numbers with a static message. A pairing code flow would let new family members self-onboard with parent approval
- **Workspace prompt files**: The `SOUL.md` concept maps directly to Fortress's `personality.py` — but as an editable file rather than hardcoded Python

#### What's NOT Relevant
- Multi-channel Gateway — Fortress is WhatsApp-only by design, and WAHA already handles the bridge
- ClawHub / skill marketplace — a family system doesn't need a public skill registry
- Browser control, Canvas, Voice Wake — desktop/mobile features irrelevant to a WhatsApp bot
- Node.js/TypeScript stack — Fortress is Python, and there's no reason to change
- Multi-agent routing — Fortress has one agent serving one family

#### Proposed Integration

| Concept | Implementation | Effort |
|---------|---------------|--------|
| Skill documentation format | Add `SKILL.md` to each skill folder with Hebrew command reference, trigger patterns, and examples. Used by MorningSkill briefing and `/עזרה` command | Small |
| Member onboarding flow | New `OnboardingSkill`: parent sends "הוסף +972..." → system sends pairing code to new number → new number confirms → added to `family_members` with role | Medium |
| Editable personality file | Move `PERSONALITY` string to `fortress/config/SOUL.md`, load at startup. Allows personality tweaks without code changes | Small |

---

### Hermes Agent

#### What They Do Well
- **Closed learning loop**: after completing a complex task (5+ tool calls), the agent autonomously creates a skill document capturing the workflow. Skills self-improve during use via `patch` operations
- **Memory nudges**: the agent periodically reminds itself to persist important information from conversations. Not just reactive extraction — proactive "did I forget to save something?"
- **Four-tier memory architecture**: MEMORY.md (facts), USER.md (user model), skills (procedural), sessions (episodic). Designed to maximize prompt caching
- **SOUL.md**: a single markdown file that defines the agent's entire personality, loaded as slot #1 in the system prompt. Survives across sessions and model switches
- **Cron scheduler with platform delivery**: scheduled jobs defined in natural language, results delivered to any connected messaging platform
- **Session search with LLM summarization**: FTS5 full-text search across past conversations, with LLM-generated summaries for cross-session recall
- **Progressive skill disclosure**: Level 0 (list) → Level 1 (full content) → Level 2 (reference files). Minimizes token usage
- **Skill categories and conditional activation**: skills can require or fall back based on available toolsets

#### What's Relevant to Fortress
- **Memory nudges**: Fortress already extracts memories via Bedrock after conversations (`extract_memories_from_message`), but it's purely reactive. Adding periodic self-nudges ("did the user mention something important I should save?") would catch facts that slip through the extraction prompt
- **Procedural memory (skill creation)**: when ChatSkill successfully handles a complex query (e.g., "how do I renew the car insurance"), the answer could be saved as a reusable knowledge snippet for future similar questions
- **User modeling**: Hermes builds a `USER.md` per user. Fortress has per-member memories but no structured user profile. A structured profile (preferences, communication style, common requests) would improve ChatSkill responses
- **Session search**: Fortress saves all conversations to DB but has no search capability. Adding "מה אמרתי על..." (what did I say about...) would be valuable
- **Enhanced scheduler**: Fortress's APScheduler runs daily at a fixed hour. Hermes allows natural-language cron definitions with delivery to specific platforms

#### What's NOT Relevant
- Terminal backends (Docker, SSH, Modal, Daytona) — Fortress doesn't execute arbitrary code
- Multi-provider model routing with OAuth — Fortress's Bedrock/OpenRouter/Ollama chain is simpler and sufficient
- Git worktree isolation — not a development tool
- Skills Hub / marketplace — family system, not a developer tool
- Delegation / subagents — overkill for household tasks
- TTS/STT — WhatsApp handles voice natively via WAHA

#### Proposed Integration

| Concept | Implementation | Effort |
|---------|---------------|--------|
| Memory nudges | After ChatSkill responds, run a lightweight check: "should I remember something from this exchange?" using a cheap model (OpenRouter free tier). Trigger only when ChatSkill was used (not deterministic skills) | Small |
| Conversation search | New `SearchSkill`: "מה אמרתי על ביטוח" → FTS query on `conversations.message_in` + `conversations.message_out` → return top 5 results with dates. Add `tsvector` column to conversations table | Medium |
| User profile | New `user_profiles` table: `family_member_id`, `profile_json` (structured: preferences, habits, communication_style). Updated periodically from accumulated memories. Injected into ChatSkill prompts | Medium |
| Procedural memory | When ChatSkill handles a query that required memory context, save the Q&A pair as a "knowledge snippet" in a new `knowledge_snippets` table. Future similar queries check snippets before calling LLM | Medium |
| Natural-language cron | Extend RecurringSkill to accept free-text schedules: "תזכיר לי כל יום שני ב-9 בבוקר" → parse with LLM → create APScheduler job. Store in `scheduled_jobs` table | Large |

---

### NemoClaw

#### What They Do Well
- **OpenShell sandbox**: kernel-level isolation (Landlock + seccomp + network namespaces) between agent and host. Filesystem restricted to `/sandbox` and `/tmp`, process isolation prevents privilege escalation
- **Network egress control**: declarative YAML policy defining which external endpoints the agent can reach. Unapproved connections require operator approval. Hot-reloadable at runtime
- **Privacy Router**: intercepts queries to cloud LLMs, applies differential privacy to strip PII before the query leaves the operator's environment. Supports routing to local Nemotron models when hardware allows
- **Intent verification**: before an agent executes a tool call, the intent is validated against operator-defined policy. Out-of-policy actions are blocked before execution
- **Single-command install**: `curl | bash` wraps OpenClaw in the full security stack
- **Declarative policy files**: YAML-based security policies with presets for common integrations (PyPI, Docker Hub, Slack, Jira)

#### What's Relevant to Fortress
- **PII stripping before cloud calls**: Fortress sends user messages to Bedrock and OpenRouter. Family conversations may contain phone numbers, addresses, ID numbers, medical info. A lightweight PII filter before LLM calls would significantly improve privacy
- **Intent verification for destructive actions**: Fortress has a confirmation flow for deletes, but no policy-based verification. Adding a policy layer ("children cannot delete tasks created by parents", "bulk delete requires admin") would strengthen the permission system
- **Action audit with intent logging**: NemoClaw logs what the agent intended to do, not just what it did. Fortress's audit_log captures actions but not the intent that led to them

#### What's NOT Relevant
- Full kernel-level sandboxing (Landlock, seccomp, network namespaces) — Fortress runs in Docker Compose on a trusted home network, not in an enterprise environment with untrusted agents
- Network egress control — Fortress's outbound connections are hardcoded (Bedrock, OpenRouter, Ollama, WAHA), not dynamic
- OpenShell runtime — requires Linux with specific kernel features, adds massive complexity for minimal benefit in a family context
- Blueprint lifecycle / artifact verification — enterprise deployment concern
- NVIDIA hardware requirements — Mac Mini M4 doesn't have NVIDIA GPUs

#### Proposed Integration

| Concept | Implementation | Effort |
|---------|---------------|--------|
| PII guard for LLM calls | Middleware function in `ChatSkill._dispatch_llm()`: before sending prompt to any cloud provider, run regex-based PII detection (Israeli ID numbers, phone numbers, credit cards, addresses). Replace with placeholders. Restore in response if needed | Small |
| Enhanced permission policies | Extend `permissions` table with action-level policies: "child cannot delete parent's tasks", "bulk operations require parent role". Enforce in Executor before skill dispatch | Medium |
| Intent logging in audit | Add `intent` and `original_message` fields to `audit_log`. Log what the user asked for, not just the resulting action. Enables "why was this deleted?" queries | Small |
| Sensitive action escalation | For high-risk actions (delete_all, financial operations), send WhatsApp confirmation to admin even if the requesting member has permission. Configurable per-action in a policy table | Medium |

---

### Khoj

#### What They Do Well
- **RAG on personal documents**: indexes PDFs, Markdown, Word docs, Notion files, GitHub repos, and Org-mode files. Semantic search using vector embeddings, not just keyword matching
- **Document chunking and indexing**: splits documents into semantically coherent chunks, embeds them, stores in vector DB for retrieval. Optimal chunk size ~256-512 tokens with overlap
- **Multi-source connectors**: Obsidian, Emacs, web browsers, Notion, GitHub — all feed into the same knowledge base
- **Custom agent creation**: users can create specialized agents with custom knowledge bases, personas, and tool access
- **Scheduled automations**: automated research tasks, personal newsletters, smart notifications delivered on schedule
- **Deep research**: multi-step reasoning that combines web search with personal document context
- **Semantic search**: finds relevant documents by meaning, not just keywords. "What did the doctor recommend?" finds the medical report even if "recommend" isn't in the text
- **Self-hostable with local LLMs**: runs entirely on-device with Ollama or similar

#### What's Relevant to Fortress
- **RAG over family documents**: Fortress already stores documents (receipts, invoices, medical records) but can only list them. Adding semantic search would enable "כמה שילמנו על ביטוח רכב?" (how much did we pay for car insurance?) by searching across stored document content
- **Document indexing pipeline**: Fortress's `DocumentSkill` saves files but doesn't extract or index their content. Adding text extraction (OCR for images, PDF parsing) + chunking + embedding would unlock document Q&A
- **Scheduled research**: combining Khoj's automation pattern with Fortress's scheduler — e.g., "every month, check if any recurring payments are due and summarize"
- **Semantic memory search**: Fortress's memory system uses exact matching. Vector-based semantic search would find related memories even with different wording

#### What's NOT Relevant
- Multi-source connectors (Obsidian, Emacs, GitHub, Notion) — Fortress's only input is WhatsApp messages and media
- Custom agent creation — one family, one agent
- Web browser integration — WhatsApp-only interface
- Cloud hosting / enterprise features — local-first on Mac Mini
- Multi-user with separate knowledge bases — family shares one knowledge base (with permission-based access)

#### Proposed Integration

| Concept | Implementation | Effort |
|---------|---------------|--------|
| Document text extraction | Add `raw_text` extraction pipeline: PDF → `pdfplumber`, images → `pytesseract` OCR (Hebrew support), Word → `python-docx`. Store extracted text in existing `documents.raw_text` column | Medium |
| Document embedding + vector search | Add `pgvector` extension to PostgreSQL. New `document_chunks` table with embeddings. Chunk documents at ~400 tokens with overlap. Embed using local model (Ollama) or Bedrock Titan Embeddings | Large |
| Document Q&A skill | New `SearchDocSkill`: "חפש במסמכים..." → vector search → top-K chunks → LLM generates answer with source citations. Hebrew command patterns: "חפש במסמכים", "מה כתוב ב...", "כמה שילמנו על..." | Medium |
| Semantic memory search | Add embeddings to `memories` table. When ChatSkill loads memories, use semantic similarity instead of just recency. "What did we decide about the renovation?" finds relevant memories even with different wording | Large |
| Monthly document digest | Scheduled job: once a month, summarize all new documents (receipts, invoices) into a financial overview. Send to parents via WhatsApp | Medium |

---

## Prioritized Integration Roadmap

### Phase 1: Quick Wins (1-2 sprints)

| Feature | Source | Maps To | Effort |
|---------|--------|---------|--------|
| PII guard for LLM calls | NemoClaw | `ChatSkill._dispatch_llm()` middleware | Small |
| Intent logging in audit | NemoClaw | `audit_log` table + Executor | Small |
| Skill documentation format | OpenClaw | `SKILL.md` per skill folder | Small |
| Editable personality file | OpenClaw/Hermes | `config/SOUL.md` → loaded at startup | Small |
| Memory nudges | Hermes | Post-ChatSkill hook in `message_handler` | Small |

### Phase 2: Medium Term (3-4 sprints)

| Feature | Source | Maps To | Effort |
|---------|--------|---------|--------|
| Conversation search skill | Hermes | New `SearchSkill` + FTS on conversations | Medium |
| Document text extraction | Khoj | `DocumentSkill` pipeline enhancement | Medium |
| User profile system | Hermes | New `user_profiles` table + ChatSkill context | Medium |
| Enhanced permission policies | NemoClaw | Extended `permissions` table + Executor | Medium |
| Member onboarding flow | OpenClaw | New `OnboardingSkill` | Medium |
| Sensitive action escalation | NemoClaw | Policy table + WhatsApp notification | Medium |
| Procedural memory (knowledge snippets) | Hermes | New `knowledge_snippets` table + ChatSkill | Medium |

### Phase 3: Long Term (5+ sprints)

| Feature | Source | Maps To | Effort |
|---------|--------|---------|--------|
| Document embedding + vector search | Khoj | `pgvector` + `document_chunks` table | Large |
| Document Q&A skill | Khoj | New `SearchDocSkill` | Medium |
| Semantic memory search | Khoj | Embeddings on `memories` table | Large |
| Natural-language cron | Hermes | Extended `RecurringSkill` + APScheduler | Large |
| Monthly document digest | Khoj | Scheduled job + document summarization | Medium |

---

## Technical Recommendations

### New Skills to Create

**SearchSkill** (Phase 2)
- Source inspiration: Hermes Agent session search
- Commands: `חפש <query>`, `מה אמרתי על <topic>`, `search <query>`
- Dependencies: PostgreSQL FTS (`tsvector`/`tsquery`), Hebrew text search configuration
- Effort: Medium

**SearchDocSkill** (Phase 3)
- Source inspiration: Khoj RAG
- Commands: `חפש במסמכים <query>`, `מה כתוב ב...`, `כמה שילמנו על...`
- Dependencies: `pgvector`, embedding model (Ollama or Bedrock Titan), `pdfplumber`, `pytesseract`
- Effort: Medium (after vector infrastructure is in place)

**OnboardingSkill** (Phase 2)
- Source inspiration: OpenClaw DM pairing
- Commands: `הוסף חבר <phone>`, `קוד צירוף` (admin-only creation, new member confirmation)
- Dependencies: WhatsApp message sending via WAHA, random code generation
- Effort: Medium

### Infrastructure Changes

**New DB tables:**
- `user_profiles` — structured per-member profile (JSONB), updated from accumulated memories
- `knowledge_snippets` — procedural memory: Q&A pairs from successful ChatSkill interactions
- `document_chunks` — chunked document text with vector embeddings (Phase 3, requires `pgvector`)
- `action_policies` — configurable per-action permission policies (extends current `permissions`)

**New Docker services:**
- None in Phase 1-2. Phase 3 may benefit from a dedicated embedding service if Ollama is too slow for batch embedding, but the Mac Mini M4 should handle it

**New Python dependencies:**
- Phase 1: None (PII guard uses regex)
- Phase 2: `pdfplumber`, `python-docx`, `pytesseract` (document extraction)
- Phase 3: `pgvector` (PostgreSQL extension), `sentence-transformers` or use Ollama embeddings API

**PostgreSQL extensions:**
- Phase 2: Enable `pg_trgm` for fuzzy text search (already available in PostgreSQL 16)
- Phase 3: Install `pgvector` for vector similarity search

### Architecture Changes

**base_skill.py:**
- No changes needed. The `BaseSkill` interface is flexible enough for all proposed skills

**executor.py:**
- Phase 1: Add intent logging — capture `command.skill`, `command.action`, and original message text in audit log
- Phase 2: Add policy check step between permission check and skill execution. New function `check_action_policy(db, member, command)` that validates against `action_policies` table

**command_parser.py:**
- No changes needed. New skills register their patterns through the existing registry mechanism

**message_handler.py:**
- Phase 1: Add memory nudge hook after ChatSkill response — lightweight LLM call to check if anything should be saved
- Phase 1: Add PII guard wrapper around the ChatSkill LLM path

**config.py:**
- Phase 1: Add `SOUL_MD_PATH` config for editable personality file location
- Phase 2: Add `EMBEDDING_MODEL` config for vector search

**personality.py:**
- Phase 1: Refactor to load personality from `SOUL.md` file with fallback to current hardcoded string
- Phase 2: Add templates for new skills (search results, document Q&A, onboarding)

---

## What NOT to Do

- **Full OpenShell sandboxing** — Fortress runs on a trusted home network in Docker Compose. Kernel-level isolation (Landlock, seccomp, network namespaces) adds massive complexity for zero practical benefit. The threat model is "kids shouldn't see financial data", not "untrusted agents executing arbitrary code"
- **Multi-channel Gateway** — Fortress is WhatsApp-only by design. Adding Telegram/Discord/Slack support would fragment the family experience and multiply maintenance burden. WAHA already handles the WhatsApp bridge well
- **Skill marketplace / ClawHub** — a family of 4-6 people doesn't need a public skill registry. Skills are internal
- **Agent delegation / subagents** — Fortress handles one message at a time from one family member. Spawning subagents for parallel workstreams is enterprise complexity with no family use case
- **Full Khoj-style multi-source connectors** — Obsidian, Emacs, GitHub, Notion integrations are irrelevant. The only input channel is WhatsApp
- **Custom agent creation per user** — one agent, one personality, one family. Per-user agents would confuse the family dynamic
- **Node.js/TypeScript migration** — OpenClaw and NemoClaw are Node.js. Fortress is Python. There is zero reason to switch
- **Voice Wake / Talk Mode** — WhatsApp handles voice messages natively. Adding wake word detection to a server-side bot makes no sense
- **Browser automation** — Fortress is a household assistant, not a web scraper. No use case for CDP/Playwright
- **Git worktree isolation** — Fortress is not a development tool
- **RL training / trajectory generation** — Hermes's research features are for training new models, not running a family bot
- **Differential privacy for PII** — NemoClaw uses sophisticated differential privacy techniques. For Fortress, simple regex-based PII detection and replacement is sufficient and doesn't require a PhD to maintain
- **NVIDIA hardware dependency** — Mac Mini M4 has Apple Silicon, not NVIDIA GPUs. Any solution must work with CPU or Apple Metal

---

## Constraints Respected

1. ✅ Skills Engine architecture preserved — all proposals are new skills or middleware, not architectural changes
2. ✅ 90% deterministic / 10% LLM ratio maintained — new skills use regex patterns for commands, LLM only for search/Q&A
3. ✅ Local-first, privacy-focused — PII guard strengthens privacy; document processing runs locally
4. ✅ WhatsApp is the only interface — no new interfaces proposed
5. ✅ Hebrew is the primary language — all commands and responses in Hebrew
6. ✅ Mac Mini M4 (24GB RAM) — no NVIDIA dependencies; Ollama embeddings fit in memory alongside existing services
7. ✅ No npm/node/frontend — all proposals are Python
8. ✅ Every new skill follows BaseSkill pattern — SearchSkill, SearchDocSkill, OnboardingSkill all extend BaseSkill
9. ✅ Every action is DB-verified — new skills include verify() implementations
10. ✅ Memory exclusions respected — PII guard adds a layer; memory nudges still check exclusions before saving
