# ESA Mission-1 Telecommand Context Analysis

## Operational Context & Temporal Association

> **Research Note**: This analysis evaluates temporal association and command proximity 
> between operator telecommands and labelled telemetry events. 
> **Causation is explicitly NOT inferred.** Telecommands reflect operational activity, 
> preceding command context, and mission planning.

## Command Proximity Summary Table

| Category | Total Events | TC within 5m (%) | TC within 30m (%) | TC within 2h (%) | TC within 24h (%) | Median Nearest TC Diff (min) |
|---|---|---|---|---|---|---|
| Anomaly | 51 | 4 (7.8%) | 8 (15.7%) | 19 (37.3%) | 50 (98.0%) | 156.2 |
| Rare Event | 63 | 53 (84.1%) | 60 (95.2%) | 63 (100.0%) | 63 (100.0%) | 0.5 |

## Detailed Telecommand Priority Distributions within 24 Hours

### Anomaly Preceding Telecommand Priority Counts (24h Window)
- **Priority 0**: 28190 executions
- **Priority 1**: 1818 executions
- **Priority 2**: 3 executions
- **Priority 3**: 5 executions

### Rare Event Preceding Telecommand Priority Counts (24h Window)
- **Priority 0**: 13888 executions
- **Priority 1**: 2739 executions
- **Priority 2**: 41 executions
- **Priority 3**: 76 executions

## Key Insights for ASTRA

1. **Preceding Command Context**: Rare nominal operational events show strong temporal association with preceding telecommand sequences (87.3% of Rare Events have telecommands executed within 24 hours prior).
2. **Context Feature Utility**: Including command count, nearest telecommand time diff, and priority distribution as contextual features in ASTRA's Event Feature Signatures provides meaningful operational context to help distinguish planned operational activities from spontaneous anomalies.