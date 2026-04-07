#!/bin/bash
# Hook: PreToolUse - Check if rules have been loaded before significant operations
# Receives tool call JSON on stdin
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)

# Skip check for memory tools themselves (avoid infinite loop)
if [[ "$TOOL_NAME" == memory_* ]] || [[ "$TOOL_NAME" == mcp__memory__* ]]; then
    exit 0
fi

echo "MEMORY MCP RULES CHECK: Before proceeding with '$TOOL_NAME', ensure you have called memory_get_rules() this session and are following all mandatory rules and avoiding all forbidden patterns."
exit 0
