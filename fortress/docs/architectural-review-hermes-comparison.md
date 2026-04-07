# Fortress vs Hermes Agent — Architectural Review

> Requested: open architectural review before building more custom tools.
> Reference: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
> Date: April 2026

---

## A. Findings

### 1. Tool System

**Hermes is stronger here.**

Hermes uses a self-registering tool pattern: each tool file calls `registry.register()` at import time with a handler function, a JSON schema, a `check_fn` for availability gating, and a toolset assignment. Adding a tool touches 3 files. The registry handles async bridging, error wrapping (always returns JSON strings), and availability filtering automatically. Tools are grouped into composable **toolsets** that can be enabled/disabled per platform.

Fortress uses a split approach: tool *schemas* are defined as static Bedrock `toolSpec` dicts in `tool_registry.py`, while tool *behavior* lives in skill classes. The `_TOOL_MAP` dict manually maps tool names to `(skill_name, action_name)` tuples. Adding a tool means: (1) add a schema to `_TOOL_SCHEMAS`, (2) add a mapping to `_TOOL_MAP`, (3) add a regex pattern to the skill's `commands` property, (4) add a handler method to the skill class, (5) optionally add it to `_INTENT_TOOLS` in `tool_router.py`. That's 5 files for one tool.

**Verdict:** Fortress's tool registration is scattered and manual. Hermes's self-registration pattern is objectively better engineering — less boilerplate, fewer places to forget, and the `check_fn` pattern for conditional availability is something Fortress completely lacks.

### 2. Skill / Plugin Architecture

**Different concepts — both have merit, but Hermes's model is more extensible.**

Hermes skills are *prompt documents* (SKILL.md files) that the agent loads on demand. They're procedural memory — instructions the agent follows, not code. The agent can create, edit, and delete its own skills. Skills are compatible with the agentskills.io open standard and can be installed from multiple hubs (skills.sh, GitHub, well-known endpoints). This is a fundamentally different abstraction from Fortress skills.

Fortress skills are *code modules* — Python classes with regex patterns, execute methods, verification hooks, and permission checks. They're deterministic handlers, not prompt-based. This is appropriate for Fortress's domain (family WhatsApp bot with structured operations like task CRUD, document management, fact storage) where you need guaranteed behavior, not LLM-interpreted instructions.

Hermes also has a **plugin system** (3 discovery sources: user, project, pip entry points) that can register tools, hooks, and CLI commands. Fortress has no plugin system.

**Verdict:** Fortress skills should stay as code modules — the domain demands deterministic execution. But Fortress should adopt Hermes's concept of *prompt-based skills* as a separate layer for non-critical, extensible behaviors (e.g., "how to respond to emotional messages", "recipe formatting preferences"). The plugin system is overkill for Fortress's single-deployment model.

### 3. Orchestration / Agent Loop

**Comparable, with Fortress having some unique strengths.**

Both use a tool-calling loop: build system prompt → call LLM → execute tool calls → loop until text response. Both have fallback mechanisms.

Hermes supports 3 API modes (chat completions, Codex responses, Anthropic messages) and 18+ providers. Fortress is Bedrock-only with Ollama fallback. Hermes has context compression and prompt caching. Fortress has neither.

However, Fortress has a **dual-path execution model** (agent loop + deterministic regex fallback) that's actually well-suited to its domain. The `_should_prefer_structured_path()` logic that bypasses the agent for task/system/fact/deploy commands is smart — it prevents the LLM from hallucinating when deterministic execution is critical. Hermes doesn't need this because it doesn't have the same structured-data requirements.

Fortress's **intent-based tool filtering** (tool_router.py selecting 5-8 relevant tools per intent group) is a pragmatic optimization that reduces token cost and improves tool selection accuracy. Hermes sends all enabled tools to the model.

**Verdict:** Fortress's dual-path model and intent-based tool filtering are genuine advantages for its domain. Keep them. But the lack of context compression is a real gap — long conversations will blow up token costs.

### 4. Memory System

**Hermes is significantly stronger.**

Hermes has a layered memory architecture:
- MEMORY.md (agent's notes, 2200 chars) — injected into system prompt
- USER.md (user profile, 1375 chars) — injected into system prompt
- Session search (FTS5 full-text search across all past sessions)
- 8 external memory provider plugins (Honcho, Mem0, etc.)
- Automatic capacity management with consolidation
- Security scanning on memory entries

Fortress has:
- A `Memory` table with categories, expiration, and access tracking
- Memories loaded into the agent's system prompt (up to 10)
- LLM-based memory extraction from conversations
- Exclusion patterns

Fortress's memory is functional but lacks: bounded capacity management, memory consolidation, cross-session search, and the agent's ability to self-manage its own memory. The LLM-based extraction is a good idea but there's no evidence it's working well in practice (no consolidation, no dedup beyond exclusion patterns).

**Verdict:** Fortress should adopt Hermes's bounded memory model with explicit capacity limits and agent-managed curation. The current unbounded approach will degrade prompt quality over time.

### 5. Provider / Model Management

**Hermes is more flexible, Fortress is more cost-aware.**

Hermes supports 18+ providers with a unified runtime resolver. Switch models with a single command. No lock-in.

Fortress has a sophisticated 5-tier model routing system (`model_selector.py`) with:
- Task-type → tier mapping (classify=economy, agent=strong, etc.)
- Session-level tier overrides with user confirmation
- Auto-downgrade after N consecutive normal messages
- Upgrade trigger detection from message content

This is actually more sophisticated than Hermes's model selection for a cost-sensitive deployment. The dynamic routing based on task complexity is a real feature.

**Verdict:** Fortress's model routing is a genuine strength. Keep it. But the single-provider lock-in (Bedrock + Ollama) is a risk. Consider abstracting the provider interface.

### 6. External Integrations / Gateway

**Hermes is massively stronger.**

Hermes has 14 platform adapters (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, etc.) with unified session routing, user authorization, and cross-platform conversation continuity.

Fortress has one integration: WhatsApp via WAHA. The `whatsapp_client.py` is 70 lines of httpx calls.

**Verdict:** This is fine for Fortress's scope. It's a family bot, not a platform. But if you ever want to add Telegram or other channels, you should look at Hermes's gateway architecture for the adapter pattern.

### 7. Where Fortress is Reinventing Unnecessarily

1. **Tool registration** — The manual `_TOOL_MAP` + `_TOOL_SCHEMAS` + skill regex pattern approach is 3x the code of Hermes's self-registration. Every new tool requires touching 5 files.

2. **Intent detection / tool routing** — Fortress has *three* overlapping intent detection systems:
   - `intent_detector.py` (regex-based, barely used)
   - `command_parser.py` (regex-based, used for deterministic path)
   - `tool_router.py` (regex-based, used for agent path tool filtering)
   
   These share patterns but don't share code. The `intent_detector.py` is nearly dead code.

3. **LLM dispatch** — There are *three* separate LLM calling patterns:
   - `bedrock_client.py` (direct Bedrock calls)
   - `llm_client.py` (Ollama client)
   - `llm_dispatch.py` (Bedrock-primary/Ollama-fallback wrapper)
   - Plus `ChatSkill._dispatch_llm()` which duplicates `llm_dispatch.py`'s logic
   
   Hermes has one provider resolution path. Fortress has 4 overlapping ones.

4. **Async/sync bridging** — Fortress uses `concurrent.futures.ThreadPoolExecutor` with `asyncio.run()` in multiple places to bridge sync skills into the async agent loop. This is fragile and creates nested event loop risks. Hermes handles this cleanly with a centralized `_run_async()` bridge.

### 8. Where Fortress Should Stay Custom

1. **Skill execution pipeline** — The `execute()` → `verify()` → `update_state()` → `audit()` pipeline in `executor.py` is well-designed for Fortress's domain. Hermes doesn't need this because it doesn't have structured data operations with verification requirements.

2. **Document processing pipeline** — The multi-step ingestion (extract → classify → extract facts → summarize → name → tag) is domain-specific and well-structured. Nothing in Hermes replaces this.

3. **Conversation state management** — The pending confirmation flow, entity tracking, and model upgrade negotiation are Fortress-specific UX patterns that work well for WhatsApp.

4. **Permission system** — Role-based access (parent/child/other + admin flag) is appropriate for a family bot. Hermes has DM pairing and allowlists, which is a different model.

5. **Hebrew-first design** — The personality system, SOUL.md, Hebrew regex patterns, and RTL-aware formatting are all Fortress-specific.

---

## B. Recommendation

### Adopt from Hermes

1. **Self-registering tool pattern** — Replace the manual `_TOOL_MAP` / `_TOOL_SCHEMAS` split with a decorator-based or `register()` call pattern where each tool defines its own schema, handler, and availability check in one place. This is the single highest-impact change.

2. **Bounded memory with agent curation** — Add explicit capacity limits to memory, let the agent consolidate/replace entries, and add a simple session search capability.

3. **Centralized async bridging** — Replace the scattered `ThreadPoolExecutor` + `asyncio.run()` calls with a single utility function.

4. **Context compression** — Implement conversation summarization when context exceeds a threshold. This directly reduces Bedrock costs.

5. **Tool availability gating** — Add `check_fn` to tools so they can be conditionally excluded (e.g., dev tools only when admin, document tools only when storage is configured).

### Ignore from Hermes

1. **Multi-provider support** — Fortress doesn't need 18 providers. Bedrock + Ollama is fine for a single-family deployment.

2. **Plugin system** — Overkill. Fortress has one deployment, one user base.

3. **Prompt-based skills** — Hermes skills are prompt documents, not code. Fortress's code-based skills are correct for its deterministic requirements.

4. **Skills Hub / marketplace** — Irrelevant for a private family bot.

5. **Terminal backends** — Docker/SSH/Modal execution environments are for developer agents, not family assistants.

6. **Cron as agent tasks** — Fortress's APScheduler + `run_daily_schedule()` is simpler and sufficient.

### Redesign

1. **Consolidate intent detection** — Merge `intent_detector.py`, the relevant parts of `command_parser.py`, and `tool_router.py` into a single classification module. Kill `intent_detector.py`.

2. **Unify LLM dispatch** — One function that handles provider selection, fallback, and error handling. Kill `ChatSkill._dispatch_llm()` and make `llm_dispatch.py` the single entry point for all non-agent-loop LLM calls.

3. **Flatten the tool → skill indirection** — The current flow is: LLM calls tool → `tool_executor` looks up skill+action → builds Command → `executor.execute()` → skill.execute(). This is one layer too many. Tools should be able to register their handlers directly while still going through the verify/audit pipeline.

### Leave Alone

1. **Dual-path execution** (agent + regex fallback) — This is a genuine architectural advantage.
2. **Document pipeline** — Domain-specific, well-structured.
3. **Model selector** — Sophisticated and cost-aware.
4. **SOUL.md personality** — Works well.
5. **WhatsApp integration** — Simple and sufficient.
6. **Permission system** — Appropriate for the domain.

---

## C. Execution Plan

### Phase 1: Quick Wins (1-2 days each, low risk)

**1.1 Kill `intent_detector.py`**
- It's nearly dead code. `tool_router.py` does the same job better.
- Remove the file, remove the import from `message_handler.py`.
- Risk: zero. The only caller is `should_fallback_to_chat()` which can move to `tool_router.py`.

**1.2 Unify LLM dispatch**
- Make `llm_dispatch.llm_generate()` the single non-agent-loop LLM entry point.
- Delete `ChatSkill._dispatch_llm()` and have `ChatSkill.respond()` call `llm_dispatch.llm_generate()`.
- Risk: low. Both implementations do the same thing (Bedrock → Ollama fallback).

**1.3 Centralize async bridging**
- Create `src/utils/async_bridge.py` with a `run_sync(coro)` function.
- Replace all `ThreadPoolExecutor` + `asyncio.run()` patterns in `dev_skill.py` and `document_skill.py`.
- Risk: low. Behavioral change is minimal.

### Phase 2: Medium-Risk Improvements (3-5 days each)

**2.1 Self-registering tool pattern**
- Create a `@tool` decorator or `register_tool()` function that combines schema + handler + skill mapping + availability check.
- Each skill file registers its own tools at import time (like Hermes).
- `tool_registry.py` becomes a thin registry that collects registrations.
- `tool_executor.py` dispatches directly to registered handlers, but still runs through the verify/audit pipeline.
- Risk: medium. Touches the core dispatch path. Needs thorough testing.

**2.2 Context compression**
- When conversation history exceeds N tokens, summarize older turns using a cheap model (economy tier).
- Store compressed summaries in conversation state.
- Risk: medium. Affects response quality. Needs tuning.

**2.3 Tool availability gating**
- Add `check_fn` to tool registrations.
- Dev tools check `member.is_admin`.
- Document tools check storage availability.
- `get_tool_schemas()` filters based on `check_fn` results.
- Risk: low-medium. Could accidentally hide tools if check_fn is wrong.

### Phase 3: Deeper Architectural Changes (1-2 weeks)

**3.1 Bounded memory with agent curation**
- Add capacity limits to memory (e.g., 2000 chars for agent memory, 1000 for user profile).
- Add `memory_consolidate` and `memory_replace` tool actions.
- Add simple session search (FTS on conversations table).
- Risk: medium-high. Changes memory behavior that users rely on.

**3.2 Flatten tool → skill indirection**
- Allow tools to register handlers directly instead of going through the Command → skill.execute() → action dispatch chain.
- Keep the verify/audit pipeline as middleware.
- Existing skills can gradually migrate to direct registration.
- Risk: high. Core architectural change. Do this last.

---

### Priority Order (impact / risk ratio)

| Priority | Item | Impact | Risk | Time |
|----------|------|--------|------|------|
| 1 | Kill intent_detector.py | Low | Zero | 1 hour |
| 2 | Unify LLM dispatch | Medium | Low | 1 day |
| 3 | Centralize async bridging | Medium | Low | 1 day |
| 4 | Self-registering tools | High | Medium | 3-5 days |
| 5 | Tool availability gating | Medium | Low-Med | 2 days |
| 6 | Context compression | High | Medium | 3-5 days |
| 7 | Bounded memory | High | Med-High | 1 week |
| 8 | Flatten tool indirection | Medium | High | 1-2 weeks |

### What NOT to do

- Don't try to make Fortress provider-agnostic. Bedrock + Ollama is fine.
- Don't add a plugin system. You have one deployment.
- Don't replace code-based skills with prompt-based skills. Your domain needs determinism.
- Don't add multi-platform gateway support unless you actually need it.
- Don't adopt Hermes's 9,200-line `run_agent.py` monolith pattern. Fortress's separation into `agent_loop.py` + `message_handler.py` + `executor.py` is cleaner.
