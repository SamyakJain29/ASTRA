# ESA Mission 1 dataset

This document separates source-backed ESA semantics, verified local observations,
and the prepared Phase 1.2 research assets used by Phase 1.3. Phase 1.1 inspected the local archive at
`data/raw/esa_adb/ESA-Mission1.zip` without deserializing its pickle members. Phase 1.2
verified and converted a bounded subset into Parquet. Phase 1.3 adds a predeclared
baseline protocol; dataset facts in this document are not model results.

Machine-readable evidence is stored in `artifacts/data/mission1_profile.json`,
`artifacts/data/mission1_provenance.json`, and
`artifacts/data/mission1_subset_manifest.json`. Human-readable evidence is in
`reports/mission1_data_profile.md` and `reports/mission1_subset_quality.md`.

## Verified dataset facts

### Source identity and ESA semantics

The authoritative references used here are the [Zenodo v1 dataset
record](https://zenodo.org/records/12528696), the [ESA-ADB
paper](https://openreview.net/forum?id=bbpRMoatVO), its [supplementary dataset
documentation](https://openreview.net/attachment?id=FYEGPuUrpo&name=supplementary_material),
and the [official ESA-ADB code](https://github.com/kplabs-pl/ESA-ADB). The
following interpretations come from those sources; the anonymized CSV literals remain
unchanged in the prepared Parquet data.

- The CSV literal `Anomaly` represents an unexpected or unwanted abnormal telemetry
  change that should be brought to an operator's attention.
- The CSV literal `Rare Event` is the paper's rare nominal event concept: an unusual
  event that is nevertheless expected or planned. It is not a spacecraft anomaly from
  the operator's point of view.
- `Communication Gap` is a separate category. ASTRA does not reinterpret it as a
  spacecraft anomaly.
- ESA anonymized mission time through temporal scaling and shifting. The anonymized
  Mission-1 timeline starts on `2000-01-01`; these timestamps are not the original
  mission clock.
- Public telemetry values were normalized during ESA's anonymization at the channel-group
  level. The Phase 1.2 pipeline applied no additional normalization.
- Label `StartTime` and `EndTime` values define closed intervals: both endpoints belong
  to the annotation.
- The supplementary documentation uses telecommand `Priority` to describe potential
  usefulness as anomaly-detection context. ASTRA preserves its numeric value and does
  not describe it as spacecraft operational severity or command urgency.
- A stored telecommand execution value of 1 marks an on-board execution at that exact
  timestamp. The anonymized command's operational purpose remains unavailable.

The local `ESA-Mission1.zip` MD5 is
`80750189d171f5f398fb3d96c49df12b`, an exact match for the Mission-1 file on the
Zenodo v1 record. Its existing SHA-256 remains the stronger local content identifier.

### Archive and extracted structure

- The archive is named `ESA-Mission1.zip` and is 3,776,246,054 bytes.
- Its MD5 is `80750189d171f5f398fb3d96c49df12b`, matching the Zenodo v1 file
  record.
- Its pinned SHA-256 is
  `8c81edb1e81af9084f38a3cc06fa06dbea73b504c99ce1b0fb92bda996b801a7`.
- Its ZIP directory contains 780 members: 4 CSV files, 774 nested ZIP files, and 2
  explicit directory entries.
- The sum of outer-member uncompressed sizes is 3,776,362,882 bytes.
- All members are under the top-level directory `ESA-Mission1/`.
- The immediate contents are `anomaly_types.csv`, `channels.csv`, `labels.csv`,
  `telecommands.csv`, `channels/`, and `telecommands/`.
- Safe extraction produced 778 files under `data/interim/esa_adb/mission1/` with a
  total extracted size of 3,776,362,882 bytes. A repeat inspection verified and
  skipped identical extracted files.

### Metadata tables

| File | Rows | Observed columns | Observed nulls |
| --- | ---: | --- | --- |
| `channels.csv` | 76 | `Channel`, `Subsystem`, `Physical Unit`, `Group`, `Target` | none |
| `telecommands.csv` | 698 | `Telecommand`, `Priority` | none |
| `anomaly_types.csv` | 200 | `ID`, `Class`, `Subclass`, `Category`, `Dimensionality`, `Locality`, `Length` | 4 each in `Dimensionality`, `Locality`, and `Length`; none in the other fields |
| `labels.csv` | 3,589 | `ID`, `Channel`, `StartTime`, `EndTime` | none |

Additional literal observations:

- `channels.csv` contains 58 `YES` and 18 `NO` values in `Target`.
- `telecommands.csv` contains `Priority` values 0, 1, 2, and 3 with respective row
  counts 345, 323, 19, and 11.
- `anomaly_types.csv` contains 118 `Anomaly`, 78 `Rare Event`, and 4
  `Communication Gap` values in `Category`.
- `labels.csv` references 200 distinct `ID` values and 58 distinct channel values.
  Every referenced ID occurs in `anomaly_types.csv`, and every referenced channel
  occurs in `channels.csv`.
- `StartTime` and `EndTime` contain ISO-8601-like UTC strings ending in `Z`.

### Telemetry/channel storage

- `channels/` contains 76 ZIP files named for `channel_1` through `channel_76`; these
  identifiers match the 76 definitions in `channels.csv`.
- Each channel ZIP contains one extensionless member.
- The channel ZIP files total 3,767,883,838 bytes. Their inner members total
  8,938,358,731 uncompressed bytes.
- Opcode-only inspection identifies every inner member as Python pickle protocol 5.
  The opcodes reference `pandas.core.frame.DataFrame` and NumPy symbols; no pickle
  was deserialized or executed.
- Recognized value buffers are NumPy `float32`; recognized timestamp buffers are
  NumPy `datetime64[ns]`.
- Embedded array lengths give 744,856,895 samples across the 76 files. Every channel
  payload has matching recognized timestamp and numeric-buffer lengths, and all 76
  payloads were counted.
  Per-file estimates range from 487,448 to 19,286,353 samples.
- In a bounded inspection of the first 10,000 timestamps per channel, 39 channels
  had uniform positive timestamp spacing and 37 had varying spacing. Uniform
  intervals observed in that bounded window were 30 and 90 seconds, so sampling is
  not uniform across all inspected channels.
- No NumPy NaN values were found in the recognized float buffers, and no NumPy NaT
  values were found in the recognized timestamp buffers. Undocumented numeric
  sentinel values were not interpreted.

The main ESA-ADB paper table reports 774,856,895 Mission-1 data points, 30,000,000
more than the archive inspection. However, the supplementary benchmark table reports
Phase-5 counts of 305,515,601 training, 10,741,556 validation, and 428,599,738 test
points, which sum exactly to 744,856,895. Together with the matched Zenodo v1 MD5 and
the internally consistent buffers, this identifies a source-reporting inconsistency,
likely a typographical error in the main table, rather than samples missed by the
ASTRA inspector. No archive corruption was found, so the discrepancy does not block
the verified channels 41–46 baseline study.

### Telecommand storage

- `telecommands/` contains 698 ZIP files named for `telecommand_1` through
  `telecommand_698`; these identifiers match the 698 definitions in
  `telecommands.csv`.
- Each telecommand ZIP contains one extensionless member.
- The telecommand ZIP files total 8,203,463 bytes. Their inner members total
  15,029,218 uncompressed bytes.
- Opcode-only inspection identifies every inner member as Python pickle protocol 5.
  The opcodes reference `pandas.core.frame.DataFrame` and NumPy symbols; no pickle
  was deserialized or executed.
- Recognized execution-value buffers are NumPy `uint8`; recognized timestamp buffers
  are NumPy `datetime64[ns]`.
- Embedded array lengths give an estimated 1,594,722 execution records across the
  698 files.
- `Priority` is the only definition-table field whose name contains a priority or
  impact token. No separate impact-named field was observed. It is retained as
  anomaly-detection context relevance, not operational severity or urgency.

### Event-label storage

- `anomaly_types.csv` associates each observed `ID` with literal `Class`, `Subclass`,
  and `Category` fields, plus `Dimensionality`, `Locality`, and `Length` where those
  cells are populated.
- `labels.csv` stores an `ID`, a `Channel`, and `StartTime`/`EndTime` for each of its
  3,589 rows.
- The literal category representation is `Anomaly`, `Rare Event`, or
  `Communication Gap`. Those values are preserved literally in processed data.
- `StartTime` and `EndTime` are interpreted as a closed annotation interval, including
  equal-endpoint, zero-duration rows.

## Prepared Phase 1.2 research assets

These are reproducible data-preparation outputs, not experimental results. The final
run recorded that the raw archive's filename, size, member count, uncompressed size,
MD5, and pinned SHA-256 matched the configured, Zenodo v1, and Phase 1.1 facts. The
archive's size and modification time were unchanged during preparation.

### Selected telemetry

Numeric identifiers 41 through 46 resolved through `channels.csv` to the following
literal metadata:

| Channel | Subsystem | Physical Unit | Group | Target | Samples |
| --- | --- | --- | ---: | --- | ---: |
| `channel_41` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |
| `channel_42` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |
| `channel_43` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |
| `channel_44` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |
| `channel_45` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |
| `channel_46` | `subsystem_5` | `physical_unit_4` | 8 | `YES` | 15,381,169 |

The six files contain 92,287,014 rows in total. Each has the timestamp range
`2000-01-01T00:00:16.353000` through `2013-12-31T23:59:39.657000`. All six timestamp
indexes are strictly increasing, with no duplicate or missing timestamps. No NaN or
infinite values were measured. Each channel has 281 distinct observed intervals; the
minimum is 3 milliseconds, the mode is 30 seconds, and the maximum is 5 hours,
54 minutes, 30 seconds. Sampling is therefore varying rather than uniform.

One Zstandard-compressed Parquet file is written per channel under
`data/processed/mission1/channels/`. Its schema is:

| Field | Parquet type |
| --- | --- |
| `channel` | dictionary-encoded string with `int8` indices |
| `timestamp` | `timestamp[ns]` |
| `value` | `float32` |

### Events and retained channel context

`data/processed/mission1/events.parquet` contains 3,310 label rows for 118 distinct
event IDs. An ID is relevant when at least one source label row references a selected
channel. After identifying those IDs, preparation retains every source label row for
them, including rows for other channels. This produces 1,255 selected-channel
references and 2,055 context-channel references.

The `is_multichannel` field means that an ID references at least two selected
channels. It is a structural marker, not a claim about causality or operational
meaning. Of the retained IDs, 117 meet that structural condition.

| Literal Category | Distinct event IDs | Label rows |
| --- | ---: | ---: |
| `Anomaly` | 51 | 939 |
| `Rare Event` | 63 | 2,163 |
| `Communication Gap` | 4 | 208 |

The retained event timestamp extent is `2000-02-10T01:31:16.347000+00:00` through
`2013-11-19T15:08:22.041000+00:00`. Literal category and taxonomy values remain
separate; they were not collapsed into a binary label. The Parquet schema uses:

- `large_string` for `event_id`, `channel`, `category`, `class`, `subclass`,
  `dimensionality`, `locality`, `length`, `source_start_time`, and `source_end_time`;
- `timestamp[us, tz=UTC]` for parsed `start_timestamp` and `end_timestamp`;
- `int64` for `duration_ns`;
- `int32` for `selected_channel_count` and `all_channel_count`; and
- Boolean values for `is_selected_channel` and `is_multichannel`.

There are 208 null rows in each of `dimensionality`, `locality`, and `length`; these
source nulls remain null. There are also 182 zero-duration label rows; their equal
start and end timestamps are preserved rather than reinterpreted.

### Telecommand context

Preparation processed all 698 telecommand definitions.
`data/processed/mission1/telecommands.parquet` contains 1,594,722 execution records
joined to their definition's literal Priority. Seventeen source execution streams
are empty. The timestamp range is `2000-01-01T00:00:00` through
`2013-12-31T16:40:26.250000`.

| Literal Priority | Execution records |
| ---: | ---: |
| 0 | 1,496,996 |
| 1 | 97,075 |
| 2 | 179 |
| 3 | 472 |

The schema is dictionary-encoded string `telecommand`, `timestamp[ns]`, `uint8`
`execution_value`, and `int16` `priority`. Every retained execution value is the
literal value 1. Per the ESA supplementary documentation, this marks an on-board
telecommand execution at its exact timestamp. No causal relationship between a
telecommand and an event was inferred.

### Storage and reproducibility

The eight processed Parquet files occupy 708,766,239 bytes (675.93 MiB): six channel
files, `events.parquet`, and `telecommands.parquet`. The manifest records file sizes,
row counts, schemas, output SHA-256 values, configuration and code hashes, dependency
versions, and the generation timestamp. The measured peak process working set for
the final run was 501,198,848 bytes. Preparation loaded one channel or telecommand
stream at a time.

### Trusted pickle boundary

Python pickle is executable data. Phase 1.2 deserialized only Mission-1 payloads that
were admitted through a narrow trust boundary: the raw archive had to match the
pinned identity, and each extracted nested archive had to match its member size and
CRC in that verified archive. Nested archives were required to contain one expected
payload, and loaded objects were validated against the observed Mission-1 DataFrame
structure before conversion. The preparation module does not expose a general
arbitrary-pickle loading API.

The SHA-256 establishes continuity with the inspected local bytes, and the matching
MD5 establishes identity with the Zenodo v1 Mission-1 file. These checks do not by
themselves establish licensing terms.

### Transformations deliberately not performed

- No resampling
- No interpolation
- No additional normalization of the already anonymized public values
- No forward filling
- No telemetry timestamp alteration or telemetry reordering
- No model training or anomaly detection

## Unresolved semantic questions

- What licensing terms govern the dataset artifact on the pinned Zenodo v1 record?
- What are the full authoritative meanings of `Target`, `Class`, `Subclass`,
  `Dimensionality`, `Locality`, and `Length` beyond the definitions needed in this
  phase?
- What original time standard and mission clock semantics preceded the published
  temporal anonymization?
- What operational actions do the anonymized telecommand identifiers denote?
- Are there documented missing-value sentinels beyond NumPy NaN and NaT?
- Do gaps and varying timestamp spacings represent acquisition gaps, operational
  behavior, variable-rate sampling, or another mechanism?
- How should rows with the same event ID across several channels be interpreted beyond
  their documented shared event identity?

## Future preprocessing decisions

The trusted conversion to Parquet is complete for channels 41 through 46. Phase 1.3
uses the source-backed temporal split and category mappings documented in
`docs/EXPERIMENTS.md`. Later preprocessing work must still decide:

- whether a later model requires additional normalization or timestamp alignment;
- whether and how to resample channels with different or varying timestamp spacing;
- how to handle NaN, NaT, documented sentinels, acquisition gaps, and duplicates;
- how `Target` affects channel inclusion, after its meaning is confirmed;
- whether any later detector needs a transformation beyond the unchanged irregular
  timestamp representation used by the Phase 1.3 baselines; and
- how later context or memory studies will use telecommands and recurring classes
  without inferring causality.

Raw files remain immutable. Future transformations must write reproducible outputs to
`data/interim/` or `data/processed/`; raw, interim, and generated real-data profiles
remain ignored by Git while placeholder files stay tracked.
