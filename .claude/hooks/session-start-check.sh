#!/bin/bash
# Hook: Remind Claude to call memory_session_start at conversation beginning
echo "MEMORY MCP: You MUST call memory_session_start() before doing anything else. This loads mandatory rules, forbidden rules, last session context, active sprint goals, and recent decisions. Do NOT skip this step."
