# ESA Mission 1 Data Profile

This report records observed file and table facts. It does not assign scientific meaning to ambiguous fields.

## Archive

- Filename: `ESA-Mission1.zip`
- Archive size: 3,776,246,054 bytes
- Member count: 780
- Member extensions: {'.csv': 4, '.zip': 774}
- Uncompressed size estimate: 3,776,362,882 bytes
- Top-level structure: ['ESA-Mission1']

## Extracted structure

- Root: `data\interim\esa_adb\mission1`
- Files: 778
- Extracted size: 3,776,362,882 bytes
- Top-level structure: ['ESA-Mission1']

## Metadata tables

### `ESA-Mission1/channels.csv`

- Rows: 76
- Size: 3.46 KiB
- Columns: `Channel`, `Subsystem`, `Physical Unit`, `Group`, `Target`

| Column | Inferred type | Null count |
|---|---:|---:|
| Channel | string | 0 |
| Subsystem | string | 0 |
| Physical Unit | string | 0 |
| Group | integer | 0 |
| Target | string | 0 |

Example rows (maximum 5):

```json
[
  {
    "Channel": "channel_1",
    "Subsystem": "subsystem_1",
    "Physical Unit": "physical_unit_1",
    "Group": "1",
    "Target": "NO"
  },
  {
    "Channel": "channel_2",
    "Subsystem": "subsystem_1",
    "Physical Unit": "physical_unit_1",
    "Group": "1",
    "Target": "NO"
  },
  {
    "Channel": "channel_3",
    "Subsystem": "subsystem_1",
    "Physical Unit": "physical_unit_1",
    "Group": "1",
    "Target": "NO"
  },
  {
    "Channel": "channel_4",
    "Subsystem": "subsystem_1",
    "Physical Unit": "physical_unit_2",
    "Group": "2",
    "Target": "NO"
  },
  {
    "Channel": "channel_5",
    "Subsystem": "subsystem_1",
    "Physical Unit": "physical_unit_2",
    "Group": "2",
    "Target": "NO"
  }
]
```

## Telemetry/channel storage

- Channel archives: 76
- Channel identifiers: ['channel_1', 'channel_10', 'channel_11', 'channel_12', 'channel_13', 'channel_14', 'channel_15', 'channel_16', 'channel_17', 'channel_18', 'channel_19', 'channel_2', 'channel_20', 'channel_21', 'channel_22', 'channel_23', 'channel_24', 'channel_25', 'channel_26', 'channel_27', 'channel_28', 'channel_29', 'channel_3', 'channel_30', 'channel_31', 'channel_32', 'channel_33', 'channel_34', 'channel_35', 'channel_36', 'channel_37', 'channel_38', 'channel_39', 'channel_4', 'channel_40', 'channel_41', 'channel_42', 'channel_43', 'channel_44', 'channel_45', 'channel_46', 'channel_47', 'channel_48', 'channel_49', 'channel_5', 'channel_50', 'channel_51', 'channel_52', 'channel_53', 'channel_54', 'channel_55', 'channel_56', 'channel_57', 'channel_58', 'channel_59', 'channel_6', 'channel_60', 'channel_61', 'channel_62', 'channel_63', 'channel_64', 'channel_65', 'channel_66', 'channel_67', 'channel_68', 'channel_69', 'channel_7', 'channel_70', 'channel_71', 'channel_72', 'channel_73', 'channel_74', 'channel_75', 'channel_76', 'channel_8', 'channel_9']
- Inner member extensions: {'[no extension]': 76}
- Serialization formats observed: {'Python pickle protocol 5': 76}
- Object-type symbols observed without deserialization: ['pandas.core.frame.DataFrame']
- Compressed size: 3,767,883,838 bytes
- Uncompressed size: 8,938,358,731 bytes
- Approximate sample-count summary: {'files_with_estimates': 76, 'approximate_total': 744856895, 'approximate_minimum_per_file': 487448, 'approximate_maximum_per_file': 19286353, 'basis': 'recognized embedded array lengths; values are estimates'}
- Timestamp representations observed: ['NumPy datetime64[ns]']
- Value representations observed: ['NumPy float32']
- Sampling interval assessments: {'uniform': 39, 'varying': 37}
- Cross-channel sampling comparison: {'assessment': 'varying within at least one inspected channel sample', 'distinct_observed_intervals': [{'interval': 30.0, 'unit': 'seconds'}, {'interval': 90.0, 'unit': 'seconds'}], 'basis': 'bounded leading timestamp observations from each recognized channel file'}
- Missing-value observations: {'False': 76}
- Missing-value evidence scope: NaT in recognized datetime arrays and NaN in recognized floating-point arrays; undocumented numeric sentinels are not interpreted

Raw telemetry example rows are intentionally omitted.

## Telecommands

- Definitions: 698
- Execution archives: 698
- Execution member extensions: {'[no extension]': 698}
- Serialization formats observed: {'Python pickle protocol 5': 698}
- Object-type symbols observed without deserialization: ['pandas.core.frame.DataFrame']
- Value representations observed: ['NumPy uint8']
- Priority/impact-like fields observed: ['Priority']
- Approximate execution records: 1594722 (estimated from embedded array lengths)
- Timestamp representation: {'representations_observed': ['NumPy datetime64[ns]'], 'files_with_candidates': 698, 'basis': 'observed execution-record values; units and operational semantics unresolved'}

### `ESA-Mission1/telecommands.csv`

- Rows: 698
- Size: 12.87 KiB
- Columns: `Telecommand`, `Priority`

| Column | Inferred type | Null count |
|---|---:|---:|
| Telecommand | string | 0 |
| Priority | integer | 0 |

Example rows (maximum 5):

```json
[
  {
    "Telecommand": "telecommand_1",
    "Priority": "1"
  },
  {
    "Telecommand": "telecommand_2",
    "Priority": "1"
  },
  {
    "Telecommand": "telecommand_3",
    "Priority": "1"
  },
  {
    "Telecommand": "telecommand_4",
    "Priority": "1"
  },
  {
    "Telecommand": "telecommand_5",
    "Priority": "1"
  }
]
```

## Event labels

### `ESA-Mission1/anomaly_types.csv`

- Rows: 200
- Size: 12.99 KiB
- Columns: `ID`, `Class`, `Subclass`, `Category`, `Dimensionality`, `Locality`, `Length`

| Column | Inferred type | Null count |
|---|---:|---:|
| ID | string | 0 |
| Class | string | 0 |
| Subclass | string | 0 |
| Category | string | 0 |
| Dimensionality | string | 4 |
| Locality | string | 4 |
| Length | string | 4 |

Example rows (maximum 5):

```json
[
  {
    "ID": "id_1",
    "Class": "class_6",
    "Subclass": "subclass_1",
    "Category": "Rare Event",
    "Dimensionality": "Multivariate",
    "Locality": "Global",
    "Length": "Subsequence"
  },
  {
    "ID": "id_2",
    "Class": "class_7",
    "Subclass": "subclass_1",
    "Category": "Anomaly",
    "Dimensionality": "Multivariate",
    "Locality": "Local",
    "Length": "Subsequence"
  },
  {
    "ID": "id_3",
    "Class": "class_7",
    "Subclass": "subclass_1",
    "Category": "Anomaly",
    "Dimensionality": "Multivariate",
    "Locality": "Global",
    "Length": "Subsequence"
  },
  {
    "ID": "id_4",
    "Class": "class_7",
    "Subclass": "subclass_1",
    "Category": "Anomaly",
    "Dimensionality": "Multivariate",
    "Locality": "Local",
    "Length": "Subsequence"
  },
  {
    "ID": "id_5",
    "Class": "class_7",
    "Subclass": "subclass_1",
    "Category": "Anomaly",
    "Dimensionality": "Multivariate",
    "Locality": "Local",
    "Length": "Subsequence"
  }
]
```

### `ESA-Mission1/labels.csv`

- Rows: 3589
- Size: 239.81 KiB
- Columns: `ID`, `Channel`, `StartTime`, `EndTime`

| Column | Inferred type | Null count |
|---|---:|---:|
| ID | string | 0 |
| Channel | string | 0 |
| StartTime | string | 0 |
| EndTime | string | 0 |

Example rows (maximum 5):

```json
[
  {
    "ID": "id_1",
    "Channel": "channel_12",
    "StartTime": "2004-12-01T20:42:15.429Z",
    "EndTime": "2004-12-08T22:55:45.429Z"
  },
  {
    "ID": "id_1",
    "Channel": "channel_13",
    "StartTime": "2004-12-01T20:42:15.429Z",
    "EndTime": "2004-12-08T22:55:45.429Z"
  },
  {
    "ID": "id_1",
    "Channel": "channel_14",
    "StartTime": "2004-12-01T20:43:45.429Z",
    "EndTime": "2004-12-02T02:57:15.429Z"
  },
  {
    "ID": "id_1",
    "Channel": "channel_15",
    "StartTime": "2004-12-01T20:45:00.429Z",
    "EndTime": "2004-12-02T02:58:45.429Z"
  },
  {
    "ID": "id_1",
    "Channel": "channel_16",
    "StartTime": "2004-12-01T20:43:45.429Z",
    "EndTime": "2004-12-16T16:52:30.429Z"
  }
]
```

- Candidate fields: {'ESA-Mission1/anomaly_types.csv': {'event_identifiers': ['ID'], 'start_timestamps': [], 'end_timestamps': [], 'channel_references': [], 'category_or_type_fields': ['Class', 'Subclass', 'Category'], 'timestamp_candidates': []}, 'ESA-Mission1/labels.csv': {'event_identifiers': ['ID'], 'start_timestamps': ['StartTime'], 'end_timestamps': ['EndTime'], 'channel_references': ['Channel'], 'category_or_type_fields': [], 'timestamp_candidates': [{'column': 'StartTime', 'representation': 'ISO-8601-like string', 'evidence': ['observed ISO-8601-like values']}, {'column': 'EndTime', 'representation': 'ISO-8601-like string', 'evidence': ['observed ISO-8601-like values']}]}}
- Observed category/type values: {'ESA-Mission1/anomaly_types.csv:Class': ['class_1', 'class_10', 'class_11', 'class_12', 'class_13', 'class_14', 'class_15', 'class_16', 'class_17', 'class_18', 'class_19', 'class_2', 'class_20', 'class_21', 'class_22', 'class_3', 'class_4', 'class_5', 'class_6', 'class_7', 'class_8', 'class_9'], 'ESA-Mission1/anomaly_types.csv:Subclass': ['subclass_1', 'subclass_2', 'subclass_3', 'subclass_4', 'subclass_5', 'subclass_6', 'unknown'], 'ESA-Mission1/anomaly_types.csv:Category': ['Anomaly', 'Communication Gap', 'Rare Event']}
- Interpretation boundary: Literal fields and values are reported; scientific semantics remain unresolved unless supplied by authoritative documentation.

## Unresolved semantic questions

- The meaning of observed telecommand execution values and Priority requires authoritative documentation.
- The mission time standard and timezone semantics of observed datetime64 indexes require authoritative documentation.
- Missing-value sentinels other than NumPy NaN and NaT remain unresolved.
- The cause of varying timestamp spacing is unresolved.
- The semantic meaning of the channels.csv Target field remains unresolved.
- Whether the literal Rare Event category is identical to the project's rare-nominal concept remains unresolved.
- Event interval endpoint semantics and multi-channel row interpretation remain unresolved.
- The authoritative dataset release, source, license, and checksum are not established by structural inspection alone.
