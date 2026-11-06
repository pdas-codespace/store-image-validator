# Evaluation

* `datasets/*.jsonl` – one row per case: images, pinned rule pack, human label (decision + per-rule
  statuses), partition. **All current rows are synthetic drawings** (`fixtures/images/syn-*.jpg`). They
  test the harness; they are not evidence of model quality on real photos.
* `replay/` – recorded agent outputs for those images (used by `--provider replay`).
* `evaluators/` – stdlib-only `grade(sample, item)` functions, shared by local gates and Foundry.
* `release_gates.yaml` – thresholds; `run_local_eval.py` exits 1 on any miss.

Adding real cases: put the photo under `fixtures/images/`, add a row with the human adjudication to the
right partition file, then run with `--provider foundry-model`. The first real golden case should be the
reference Contoso storefront photo mentioned in spec §13. Production traces enter via
`insights/annotate.py export` → `production_regression.jsonl` (adjudicated only).
