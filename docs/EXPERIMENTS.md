# Experiments

## Phase 1.3 protocol

Phase 1.3 asks whether a reproducible unusual-event detector can be established on
ESA Mission-1 channels 41–46 for later use beneath ASTRA's rare-nominal suppression
layer. This phase measures detector behavior only. It does not suppress rare nominal
events, use operational context as a model input, implement Event Memory, or test the
full ASTRA hypothesis.

The protocol is based on the [ESA-ADB
paper](https://openreview.net/forum?id=bbpRMoatVO), the [supplementary dataset
documentation](https://openreview.net/attachment?id=FYEGPuUrpo&name=supplementary_material),
the [official Mission-1 preparation
script](https://github.com/kplabs-pl/ESA-ADB/blob/main/notebooks/data-prep/Mission1_semisupervised_prep_from_raw.py),
and the [official metric
implementation](https://github.com/kplabs-pl/ESA-ADB/blob/main/timeeval/metrics/ESA_ADB_metrics.py).
Configuration in `configs/baseline.yaml` and `configs/experiment.yaml` predeclares
the choices below. Measured results belong in generated experiment artifacts and
`reports/mission1_baseline_results.md`; this protocol document does not invent or
anticipate them.

## Prepared inputs

The Phase 1.2 asset contains six channels with unchanged, irregular timestamps:
`channel_41` through `channel_46`. Each channel has 15,381,169 samples spanning
`2000-01-01T00:00:16.353000` through `2013-12-31T23:59:39.657000`. The event table
retains 118 IDs whose labels touch a selected channel, together with all source label
rows for those IDs. The telecommand table contains all 1,594,722 execution records.

No resampling, interpolation, forward filling, or additional value normalization is
introduced for these baselines. This differs from the official benchmark
preprocessing and is important when interpreting the results.

## Temporal split and leakage controls

Mission-1 follows the ESA benchmark's calendar split: the first 84 months are the
training side and the second 84 months are test; the final three months of the
training side are validation. Exact sample assignment is:

| Partition | Timestamp rule |
| --- | --- |
| Train | dataset start through `2006-10-01T00:00:00Z`, inclusive |
| Validation | after `2006-10-01T00:00:00Z` through `2007-01-01T00:00:00Z`, inclusive |
| Test | after `2007-01-01T00:00:00Z` through dataset end, inclusive |

Assignment uses timestamps rather than row indices because sampling is irregular.
Samples are never shuffled. Each event ID is assigned by its earliest
selected-channel `StartTime`; the split manifest also records any event interval that
crosses a partition boundary. Exact boundaries, counts by literal Category, and Class
distributions are written to `artifacts/data/mission1_split_manifest.json`.

Detector location and scale statistics are fitted independently for each channel from
the train partition only. Labels are not used during fitting. Validation remains
separate from fitting, and neither validation nor test data is used to choose the
fixed thresholds in this baseline suite.

## Event recurrence and command-context audits

`reports/mission1_event_recurrence.md` describes literal Category/Class recurrence
across train, validation, and test. It is a prerequisite audit for later Event Memory
work, not an Event Memory implementation or a claim that two occurrences are
operationally identical.

`reports/mission1_command_context.md` measures whether telecommand executions precede
Anomaly and Rare Event IDs within fixed windows and summarizes nearest preceding
deltas. Priority is retained only as the documented anomaly-detection context ranking.
Temporal proximity is association, not causation, and anonymized telecommand names are
not interpreted.

## Baseline suite

Only small, deterministic CPU baselines are in scope:

| Run ID | Detector | Fit and threshold rule |
| --- | --- | --- |
| `no_alarm` | Constant sanity check | Always false; emits no alarms |
| `std3` | Per-channel global STD | Training mean ± 3 population standard deviations |
| `std5` | Per-channel global STD | Training mean ± 5 population standard deviations |
| `mad5` | Per-channel robust MAD | Training median ± 5 × 1.4826 × median absolute deviation |

A timestamp is a system-level positive when any selected channel is positive. The
configured `state_change` grouping keeps adjacent positive timestamps in the same
prediction interval only while the positive state continues and their separation is
at most 90 seconds; a larger timestamp gap ends the interval. This explicit rule does
not assert uniform sampling.

Isolation Forest is deliberately omitted: the requested statistical baselines are
sufficient for this phase, while an additional model would add resource use and
interpretive complexity. Neural and forecasting models remain out of scope.

## Evaluation modes

The same detector outputs are evaluated under two explicit mappings:

| Mode | Alarm-positive events | Separately measured or masked |
| --- | --- | --- |
| ESA unusual-event | `Anomaly`, `Rare Event` | `Communication Gap` masked and reported separately |
| ASTRA operational | `Anomaly` | `Rare Event` is special nominal alarm burden; `Communication Gap` masked and reported separately |

ESA unusual-event mode follows the current official benchmark convention that treats
rare nominal events as detection targets. ASTRA operational mode reports genuine
Anomaly event precision and recall, detected Rare Event count/rate, and predictions
during Communication Gaps separately. It does not suppress or relabel detector
outputs. Rare Event alarms establish the burden a future context or memory layer may
attempt to reduce.

## Corrected event-wise F0.5

For a selected positive-event set, let `TPe` be distinct event IDs overlapped by at
least one prediction interval, `FNe` be selected event IDs with no overlap, and `FPe`
be unmatched prediction intervals. Repeated prediction intervals inside one closed
event do not create extra true positives. Endpoint contact counts as overlap because
ESA annotations are closed intervals.

The corrected precision uses the official time-aware penalty:

`corrected precision = TPe / (TPe + FPe) × (1 - FPt / Nt)`

Here `FPt` is predicted-positive duration in nominal time and `Nt` is total nominal
duration. Event-wise recall is `TPe / (TPe + FNe)`, and the reported score is
`F_beta` with `beta = 0.5`. Communication Gap intervals are excluded from target and
nominal scoring and are reported separately. In ASTRA operational mode, Rare Event
overlaps are also reported separately instead of being silently folded into anomaly
performance.

The implementation reproduces the core ESA event-counting, closed-overlap, and
time-penalty definitions, but Phase 1.3 results are labelled **ASTRA-local** rather
than official ESA-ADB benchmark results. ASTRA preserves irregular source timestamps
and constructs prediction intervals with the configured continuity rule, whereas the
official preparation script resamples at 30 seconds with zero-order hold and performs
other transformations. The official repository also notes that anomaly types must be
regenerated for lightweight channel subsets. ASTRA preserves source Category/Class
literals and does not claim direct leaderboard comparability.

## Reproducible experiment records

Each run writes to a new, uniquely named directory under ignored `experiments/` and
must not silently overwrite an earlier result. A result record includes:

- detector name, fixed parameters, fitted per-channel statistics, and alarm count;
- dataset-manifest and split-manifest hashes;
- resolved configuration and random seed;
- source revision when Git metadata is available;
- Python and dependency versions;
- elapsed runtime and observed peak memory where measurable;
- ESA unusual-event metrics; and
- ASTRA operational metrics, including Rare Event and Communication Gap burden.

The no-alarm run is a required evaluator sanity check. No threshold is optimized on
the test set. Reported baseline values must come from the recorded artifacts, and
published ESA benchmark values must not be presented as directly comparable under
this ASTRA-local preprocessing.

## Decisions deferred beyond Phase 1.3

The allowed degradation represented by “without materially reducing genuine anomaly
detection” must be selected before a confirmatory context/memory comparison. Later
work must also predeclare how operator validation enters memory, prevent an evaluation
event from becoming available before prediction time, and define uncertainty or
variability reporting. None of those choices is inferred from the baseline results.
