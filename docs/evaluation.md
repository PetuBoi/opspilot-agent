# Evaluation protocol

Hypothesis: word TF-IDF linear classifiers provide a useful CPU baseline for support category
prediction. Compare Logistic Regression with LinearSVC; do not infer severity or resolutions.

The authentic CC BY 4.0 dataset is attributed to the
[original record](https://zenodo.org/records/7648117) and
[Hugging Face mirror](https://huggingface.co/datasets/tasksource/it-support-tickets).
Both original splits and labels are cached unchanged. Acquisition records revision, UTC download
time and SHA-256 checksums. Labels are decoded from Arrow's Hugging Face ClassLabel metadata.
Raw records remain excluded from Git. EDA includes redacted examples and original split balance.

Training quarantines 119 training rows whose NFKC/lowercase/whitespace-normalized text occurs
in the published test split. This uses identity only, not test labels or outcomes. The EDA raw
exact-text count is a different statistic (33 distinct shared strings). GroupShuffleSplit creates
a validation set inside the remaining training records with duplicate text grouped together.
Only validation macro-F1 selects C in {0.5, 2.0} and the model. Refit on cleaned training records,
then evaluate the full, unchanged 657-row test. Both baselines have their own test reports.
Do not tune subsequent changes on those reported test metrics. Near-duplicate and multilingual
generalization risks remain. Batch inference time per ticket is not single-request server latency.

All 45 original EOL training records overlap the test text identities, so cleaned training contains
no EOL examples. The six-class learned predictor cannot predict that seventh category. All 58 EOL
test records remain in the original test, contribute zero EOL recall/F1, and appear in the full
seven-category confusion matrices and machine-readable counts. Metadata explicitly lists training
labels and categories lost during quarantine. Validation metrics cover the remaining represented
classes. No performance or coverage claim is made for the unlearnable class under this split policy.

`reports/real/` contains EDA, confusion matrices, per-class precision/recall/F1 JSON, comparison
CSV and Markdown. No RAG resolution claim is derived from the classification dataset.

`reports/synthetic/` measures the original Northstar fixtures. Twenty-four manually labeled
runbook-title queries measure document Recall@5 and MRR. These intentionally simple in-domain
queries are smoke benchmarks, not realistic retrieval generalization. Agent evaluation uses an
isolated temporary DB, alternates approval/rejection, repeats each decision and verifies zero
mutations before approval, valid citations and exactly one/zero final action. Unit tests add
malicious text, missing evidence, restart and concurrent approval cases.

Synthetic classifier templates reuse topic vocabulary and are a wiring demonstration only.
Live provider tests use mocks; no paid call is needed. The test suite and CLI compute all results.
