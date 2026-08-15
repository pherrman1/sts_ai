# S3 live AI_RNG 32-seed causal-gate audit

This tracked summary preserves the audit conclusions for the raw artifacts
stored under the ignored `build/` directory.

- Seeds: `910000–910031`
- OFF: 17/32 wins, mean floor `47.781`
- PLACEBO: 12/32 wins, mean floor `45.406`
- AI_RNG: 15/32 wins, mean floor `46.656`
- AI_RNG − PLACEBO: `+3/32` wins, mean floor `+1.25`
- Floor delta positive/negative/zero: `6/5/21`
- Exact win discordance: AI wins/placebo loses `6`; AI loses/placebo wins `3`
- Exact two-sided McNemar p-value: `0.5078125`
- Classification: **MIXED/INCONCLUSIVE**

The result did not establish H1 and did not authorize a 64-seed extension.
The complete raw-data audit and copied raw files remain at
`build/s3live32_causal_gate_910000_910031/s3live32_causal_gate_audit.md`
when the ignored build artifacts are available.