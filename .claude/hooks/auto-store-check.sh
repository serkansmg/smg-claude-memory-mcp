#!/bin/bash
# Hook: PostToolUse - After significant operations, remind to store decisions
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

# Skip memory tools
if [[ "$TOOL_NAME" == memory_* ]] || [[ "$TOOL_NAME" == mcp__memory__* ]]; then
    exit 0
fi

# After Edit/Write/Bash operations, remind to store if a decision was made
if [[ "$TOOL_NAME" == "Edit" ]] || [[ "$TOOL_NAME" == "Write" ]] || [[ "$TOOL_NAME" == "Bash" ]]; then
    echo "MEMORY MCP: If a decision, architecture choice, rule, or important context was discussed in this interaction, store it with memory_store(). Categories: decision, architecture, devops, mandatory_rules, forbidden_rules, feedback, developer_docs."
fi

exit 0
