# Working together

## First-time GitHub setup (repository owner)

1. Create a new repository on GitHub, for example `ml-capstone-team`.
2. Choose visibility appropriate for the project. A private repository can be shared with teammates and the mentor by invitation.
3. Leave the README, .gitignore, and license initialization options unchecked: the local repository already has its starter files.
4. In a terminal inside this folder, replace YOUR-USERNAME with the GitHub owner and run:

```sh
git remote add origin https://github.com/YOUR-USERNAME/ml-capstone-team.git
git push -u origin main
```

Authenticate with GitHub when prompted using your configured credential manager, token, or SSH setup. A GitHub account password is not a Git HTTPS credential.

5. Invite teammates and the mentor through the repository's Settings → Collaborators (or the access settings for your organization).

## Joining the project

After accepting the invitation, clone the repository once:

```sh
git clone https://github.com/YOUR-USERNAME/ml-capstone-team.git
cd ml-capstone-team
```

Rename your placeholder folder under `people/`, update its README, and update the team table in the root README. Coordinate those initial root README edits.

## Everyday workflow

For personal exploration, the team can start by committing directly to `main`.

Start with a clean working tree and get the latest work:

```sh
git pull --ff-only
```

Work in your personal folder. Before a meeting, copy `weekly/update-template.md` to `weekly/YYYY-MM-DD/your-name.md` and fill it out. The meeting owner creates the dated folder and meeting notes using `weekly/meeting-template.md`.

Review and commit only your intended files (replace these example paths):

```sh
git status
git add people/person_a weekly/2026-09-19/person_a.md
git commit -m "Explore initial approach and record findings"
git pull --rebase
git push
```

Make sure there are no unrelated uncommitted changes before rebasing. If someone pushes while you are working, the rebase brings their commits in before yours. If a push is rejected because new commits arrived, repeat `git pull --rebase`, then `git push`.

Separate folders reduce conflicts, but don't eliminate them. Overlapping edits to the same file can still conflict, especially notebooks. Avoid editing someone else's notebook simultaneously. Coordinate changes to shared dependencies, the root README, and meeting notes.

If a rebase reports conflicts, resolve them before continuing; ask for help if needed. `git rebase --abort` returns you to the state before the rebase. Do not force-push shared `main`.

For substantial changes to shared code, use a branch and a pull request so another teammate can review it.

## Dependencies and data

Record dependencies needed by shared work in the root `requirements.txt`. Individual experiments may keep their own requirements file and setup instructions. Do not replace the shared file with a dump of your entire environment.

Store datasets locally in `data/raw/` or `data/processed/`; these folders are ignored by Git. Document sources and access steps in `data/README.md`. Large outputs and model artifacts belong in local `outputs/` or `artifacts/` folders, also ignored. Keep small, shareable figures and summaries in your personal folder when they help explain findings.

Never commit credentials or restricted source documents. Inspect notebook outputs before committing them.
