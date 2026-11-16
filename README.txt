Prior-factory data transfer (issue #1053), orphan branch, not for merging. Delete this branch after fetching.
Restore: cat factory-data.tar.part-* > factory-data.tar && tar -xf factory-data.tar && sha256sum -c SOURCES.sha256
Contents: batch1-packed.tar (1,021 batch-1 unit packs, *.tar.npz.xz, with batch1-packed.SHA256SUMS) and batch2/bundle-*.tar
(2,553 batch-2 unit packs as bundles with SHA256SUMS inside). Merge with tools/rollout_prior/pack_factory.py merge
(branch claude/project-thread-6o0swp >= ae08707f): merge DIR_WITH_BATCH1_PACKS OUT.npz --more batch2 [--rooms playout] [--compress].
