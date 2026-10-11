# Shared-folder archive, 2026-10-11 (data only, never merge)

Backup of finished experiment folders from the project's shared folder
(`/mnt/project-files/`), made because the share hit its 50,000-file limit.

Each `library-20261011/<folder>/` holds:

- `ARCHIVE-<folder>.tar.gz` (or `.tar.gz.partNN` split pieces; join with `cat`):
  every **subdirectory** of `/mnt/project-files/<folder>/`, paths relative to
  `/mnt/project-files/`. Loose top-level files of the folder (PLAN/BRIEF/RESULT
  docs, scripts, report.json) stayed on the share.
- `ARCHIVE-<folder>.tar.gz.sha256`: hash of the whole (joined) tar.gz.
- `ARCHIVE-<folder>.members.sha256`: sha256 of every member, taken from the
  share before packing; the tar was extracted and re-hashed against it.

Restore:

    cat ARCHIVE-X.tar.gz.part* > ARCHIVE-X.tar.gz   # only for split archives
    sha256sum -c ARCHIVE-X.tar.gz.sha256
    tar xzf ARCHIVE-X.tar.gz -C /mnt/project-files/   # or any directory
    (cd /mnt/project-files && sha256sum -c .../ARCHIVE-X.members.sha256)
