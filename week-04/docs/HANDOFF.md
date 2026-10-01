# Week 4 handoff: minhash and LSH

Updated October 1, 2026. The local pipeline and the Hadoop LSH step are
complete and verified. See [STATUS.md](STATUS.md) for evidence.

## Start here

1. Read this file, [STATUS.md](STATUS.md), the [Week 4 README](../README.md),
   and the earlier [Week 2 handoff](../../week-02/docs/HANDOFF.md) for
   cluster boundaries. Those boundaries still apply: never rerun the
   installer, format disks or the NameNode, or change the firewall.
2. Check `git status --short --branch`. Work is on `max/week-04-minhash-lsh`,
   based on `origin/dev`. PRs now target `dev`, not `main`.
3. **Next session: teach the student this week's work at a lower level.** They
   want to understand what happens under the hood well enough to explain it
   back and walk through the work (see the learning item in
   [STATUS.md](STATUS.md)). Start from [the walkthrough](minhash-lsh-walkthrough.md),
   then step through `shingle.py`, `minhash.py`, `lsh.py`, and the Hadoop
   scripts. Check understanding by asking them to explain each step. Keep
   explanations short. Do not rerun the cluster job just to restore context.

## How to run

- Local: `python3 week-04/scripts/find_similar.py --output-dir data/week-04/NEW`
  (about 20 s). It refuses an existing output directory.
- Chart: `plot_scurve.py` needs matplotlib, which the system Python lacks; it
  prints a table instead. The committed PNG came from a throwaway venv.
- Cluster: the ignored helper `.local/run-week04-lsh.py LOCAL_RUN_DIR 25 4`
  ships `lsh.py`, the Hadoop scripts, and `signatures.tsv` over the pinned SSH
  route, runs the health check and `run-hadoop.sh`, and saves the private log
  and pairs to `data/week-04/cluster-<stamp>/`. Each run uses a new
  `/results/apollo11/week04-minhash-lsh-<stamp>` path.
- The cluster is reachable only on the UConn VPN. Without it, SSH times out.

## Lessons to keep

- Hadoop Streaming `-files` links each script from its own cache directory;
  Python resolves the link, so sibling modules need `-cmdenv PYTHONPATH=.`.
- With `stream.num.map.output.key.fields=2`, reducers receive
  `key1<TAB>key2<TAB>` plus an empty value.
- Reducers must not depend on value order within a key (Week 3).
- Never use Python's `hash()` for anything shared across processes.

## Boundaries

Keep hostnames, IP addresses, NetIDs, keys, and private logs out of Git. The
sanitized [example run log](example-run-log.txt) is the public record.
The PR and wiki are published; further outward-facing changes need the
student's go-ahead.
