"""Use tasks and runner helpers from the sibling PhysLiteBench checkout."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent / "PhysLiteBench"
sys.path.insert(0, str(ROOT / "scripts"))

from run_candidate_matrix import shortcut_model
from run_science import harbor_command, restrict_network
