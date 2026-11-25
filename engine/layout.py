"""Where FyzxsFlow lives in a project. The single place the folder names are set in the engine.

  <repo>/.fyzxsflow/            HOME: the project's own files, never overwritten by an install
      config.json  profile.md  gates.json  feature-flags.md  docs/  feedback/  runs/  baselines/
      learned/<agent>.md       each agent's Learned entries (the Curator's lessons for this project)
      compacted/<package path> the Compactor's smaller package files, applied by install.py (compact.py)
  <repo>/.fyzxsflow/package/    PACKAGE: installer-owned, replaced on every install, never edited by hand
      engine/  agents/  context/  templates/  skills/  instructions/  prompts/  INSTALLED.json

Agent and context files spell these paths out literally (`.fyzxsflow/package/engine/run.py`); a rename changes
this file and those paths together.
"""

NAME = "FyzxsFlow"
HOME = ".fyzxsflow"
PACKAGE = "package"
# An agent file loads in full as a system prompt, and a host's file viewer truncates long files (Copilot's at 20 KB):
# every package agent file stays within this; longer guidance lives in <agent>/<part>.md beside it.
AGENT_BUDGET_KB = 12
LEARNED = "learned"
COMPACTED = "compacted"
LEGACY_HOMES = (".agentflow",)  # earlier names, migrated by install.py


def common_dir(root):
    """The git common directory (shared by every worktree of the repo), or None outside git."""
    import pathlib
    import subprocess
    out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True)
    if out.returncode or not out.stdout.strip():
        return None
    p = pathlib.Path(out.stdout.strip())
    return (p if p.is_absolute() else pathlib.Path(root) / p).resolve()


def resolve_run(value, root=None):
    """A --run value: a run folder, or a bare run id looked up under runs/active/ (then completed/, abandoned/).
    Exits with a message when neither exists, so nothing writes to a folder made up from the id."""
    import pathlib
    path = pathlib.Path(value)
    if path.is_dir() or len(path.parts) > 1:
        return path
    if path.parts:
        base = pathlib.Path(root) if root else pathlib.Path.cwd()
        for top in [base, *base.resolve().parents]:
            for state in ("active", "completed", "abandoned"):
                cand = top / HOME / "runs" / state / value
                if cand.is_dir():
                    return cand
            if (top / HOME).is_dir():
                break
    raise SystemExit(f"--run {value}: not a run folder and not a run id under {HOME}/runs/ (see run.py list)")
