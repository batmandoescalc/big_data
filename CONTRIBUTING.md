# Contributing

This repository records an independent study, so a contribution should be
both technically correct and explainable by the student who submits it.

## Workflow

1. Start from the current `dev` branch and create a descriptively named branch.
2. Keep one topic per commit where practical.
3. Run `bash scripts/run-tests.sh` before pushing. GitHub runs the same
   checks on every pull request; do not merge while they fail.
4. Document inputs, outputs, limitations, and observed results.
5. Open a pull request into `dev` for weekly work. Periodic reviewed
   checkpoints merge `dev` into `main`.
6. Request review and leave the final checkpoint unmerged until reviewers have
   examined it.

## Reproducibility expectations

- Record data provenance and checksums where available.
- Keep preparation time separate from query/runtime measurements.
- Preserve failed experimental evidence when it explains a design change.
- Compare distributed output with an independent implementation when possible.
- Avoid performance claims that extend beyond the measured machines and data.

## Safety and privacy

Never commit passwords, authentication prompts, SSH private keys, personal
identifiers, internal hostnames or IP addresses, large datasets, generated
databases, or private logs. The existing Hadoop cluster is already provisioned;
do not rerun the fresh-node installer or reformat storage.
