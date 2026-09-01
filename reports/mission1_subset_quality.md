# Mission-1 Prepared Subset Quality Report

Generated: `2026-09-01T10:14:20Z`

This report describes measured properties of the prepared Phase 1.2 subset. It does not report model results or reinterpret ESA taxonomy.

## Telemetry

Selected channels: 6
Total samples: 92,287,014
Processed Parquet storage: 708,766,239 bytes (675.93 MiB)

### `channel_41`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 0.9821103811264038
- Value quartiles (Q1/median/Q3): 0.8055142760276794 / 0.8094388246536255 / 0.8141486048698425
- Distinct finite values: 828
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

### `channel_42`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 0.9662727117538452
- Value quartiles (Q1/median/Q3): 0.7783113718032837 / 0.7839346528053284 / 0.7895565629005432
- Distinct finite values: 850
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

### `channel_43`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 0.9507275819778442
- Value quartiles (Q1/median/Q3): 0.7663609981536865 / 0.7703173160552979 / 0.7742736339569092
- Distinct finite values: 835
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

### `channel_44`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 0.9755059480667114
- Value quartiles (Q1/median/Q3): 0.7913063168525696 / 0.7960298657417297 / 0.8007520437240601
- Distinct finite values: 856
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

### `channel_45`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 1.0
- Value quartiles (Q1/median/Q3): 0.8075276017189026 / 0.8117668032646179 / 0.8168546557426453
- Distinct finite values: 838
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

### `channel_46`

- Samples: 15,381,169
- Timestamp range: `2000-01-01T00:00:16.353000` to `2013-12-31T23:59:39.657000`
- Timestamps strictly increasing: True
- Duplicate timestamps: 0
- Missing timestamps: 0
- Missing values: 0
- Non-finite values: 0
- Value range: 0.0 to 0.9595302939414978
- Value quartiles (Q1/median/Q3): 0.7619175910949707 / 0.766984760761261 / 0.7728950381278992
- Distinct finite values: 852
- Sampling intervals: 281 distinct; minimum `P0DT0H0M0.003S`, mode `P0DT0H0M30S` (13,861,387), maximum `P0DT5H54M30S`
- Uniform sampling: False

## Events

- Retained event IDs: 118
- Retained label rows: 3,310
- Selected-channel references: 1,255
- Context-channel references: 2,055
- IDs touching at least two selected channels: 117
- IDs by literal Category: `{"Anomaly": 51, "Communication Gap": 4, "Rare Event": 63}`
- Rows by literal Category: `{"Anomaly": 939, "Communication Gap": 208, "Rare Event": 2163}`
- Label-row duration (minimum/median/maximum): 0 / 11,340,000,000,000 / 3,481,151,994,000,000 ns
- Zero-duration label rows: 182
- Missing taxonomy fields: `{"category": 0, "class": 0, "dimensionality": 208, "length": 208, "locality": 208, "subclass": 0}`

`is_multichannel` means an ID has references to at least two selected channels. It is structural context, not a causal or scientific inference.

## Telecommands

- Definitions: 698
- Execution records: 1,594,722
- Empty execution streams: 17
- Timestamp range: `2000-01-01T00:00:00` to `2013-12-31T16:40:26.250000`
- Counts by literal Priority: `{"0": 1496996, "1": 97075, "2": 179, "3": 472}`
- Execution-value counts: `{"1": 1594722}`

The execution-value meaning and any relationship between telecommands and events remain unresolved. No causal decision was made.

## Resource observations

- Largest loaded channel frame: 184,574,028 bytes
- Observed process peak working set: 501198848
- Preparation loaded one channel or telecommand stream at a time.

## Quality issues

- All selected channels have varying observed timestamp intervals; no resampling was applied.
- Some retained event taxonomy fields are null in the source and remain null.
- 182 retained label rows have zero duration.
- 17 telecommand streams are empty in the source.
- Authoritative source provenance is unresolved.
- Dataset license is unresolved.
- Telecommand execution-value semantics are unresolved.

## Transformations deliberately not performed

- No resampling
- No interpolation
- No normalization
- No forward filling
- No model training or anomaly detection
