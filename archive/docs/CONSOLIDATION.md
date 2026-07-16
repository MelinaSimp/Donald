# Consolidated branch

This branch gathers **every file from all of the project's scattered branches into one place**,
so you can browse the whole project without clicking between branches on GitHub.

## How it was built
- All 20 `claude/*` working branches were branched off an empty `main`, each holding a
  different slice of the same "Donald" project.
- Their files were merged into this single branch (269 unique files total).
- For the ~13 files that existed in multiple branches with different contents, the version
  from the **most complete branch** was kept.
- Compiled junk (`__pycache__`, `.pyc`) was removed and is now git-ignored.

If you want a specific older version of a file restored, just ask.
