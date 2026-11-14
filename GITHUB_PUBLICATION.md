# Publishing this repository publicly

This package is prepared for a **public** GitHub repository named `MushroomGuard-AI`.
It has not yet been pushed to GitHub. The GitHub account connection/authentication must be completed by the repository owner.

## Before publishing

1. Review `README.md`, `DATASET_AUDIT_2026-11-04.md`, and `ml/datasets/methi_disease/README.md`.
2. Confirm that you have rights to publish every project file and each uploaded image. The Methi growth-stage candidate images in `ml/datasets/methi/incoming_review/` were supplied in this conversation and extracted from your uploaded collage/PDF. They are not third-party images.
3. Do not add `.env`, API keys, database files, private farm records, video recordings, or any local uploads. `.gitignore` excludes these.
4. This repository deliberately has no `LICENSE` file. Public visibility alone does not grant a general licence to copy, modify, or redistribute the code. Choose a project licence only after confirming the rights to all included code.
5. The user-supplied YOLO checkpoint was removed from this public-ready package. Obtain model weights from their official source and check their licence before redistribution.
6. Disease reference images have **not** been downloaded or included. See the disease dataset source register; only add an image after checking its individual licence and attribution requirements.

## Git LFS

The candidate Methi PNG images are tracked through Git LFS using `.gitattributes`. Install Git LFS before the first `git add`/commit so the binary PNGs are stored as LFS objects rather than ordinary Git blobs.

Windows (Git Bash or PowerShell with Git LFS installed):

```powershell
git lfs install
git init -b main
git add .gitattributes
git add .
git status --short
git lfs ls-files
git commit -m "Prepare MushroomGuard AI source and Methi dataset"
```

Then authenticate with GitHub CLI and create/push the public repository:

```powershell
gh auth login
gh repo create MushroomGuard-AI --public --source . --remote origin --push --description "Offline-first mushroom and microgreens cultivation monitoring with Arduino, Flask and Methi dataset tooling"
```

If you create the empty repository in the browser instead, add its HTTPS or SSH URL as `origin` and run:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/MushroomGuard-AI.git
git push -u origin main
```

Do not initialize the remote with a README/license/gitignore if you are pushing this local history; use an empty repository to avoid unrelated-history conflicts.

## Dataset size and limits

GitHub blocks ordinary Git files larger than 100 MiB and recommends Git LFS for binary assets. Review current GitHub LFS quota/billing for your account before pushing a dataset; clones/downloads of LFS content consume bandwidth. References: <https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github> and <https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage>.

## Current status

- Source code and documentation: included.
- Methi stage candidate files: included (95 PNG candidates, 3 source groups).
- Methi stage 3: missing.
- Methi disease image binaries: not included; source register only.
- Trained Methi classifier: not included; no model was trained or validated.
- GitHub public repository: not created/pushed yet.
