-- Suggested indexes for the agentic chat rollout schema.

CREATE INDEX IF NOT EXISTS idx_chat_agents_mode_enabled_priority
ON chat_agents(mode, enabled, priority);

CREATE INDEX IF NOT EXISTS idx_chat_agents_role_key
ON chat_agents(role_key);

CREATE INDEX IF NOT EXISTS idx_chat_agent_prompts_agent_kind
ON chat_agent_prompts(agent_id, prompt_kind, version DESC);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_mode_cap
ON chat_sessions(mode, cap_id);

CREATE INDEX IF NOT EXISTS idx_chat_tool_runs_session_created
ON chat_tool_runs(session_id, created_at DESC);
