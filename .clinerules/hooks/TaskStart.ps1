$root = git rev-parse --show-toplevel
python "$root/tools/agent/cline_guardrails.py"
exit $LASTEXITCODE