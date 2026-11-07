from pathlib import Path

root_evals = str(Path(__file__).resolve().parents[2] / "evals")
if root_evals not in __path__:
    __path__.append(root_evals)
