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
LEARNED = "learned"
COMPACTED = "compacted"
LEGACY_HOMES = (".agentflow",)  # earlier names, migrated by install.py
