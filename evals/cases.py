import json
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from app.ledger.categories import Category
from app.ledger.schemas import Direction


class EvalCase(BaseModel):
    id: str
    direction: Direction
    amount: Decimal
    counterparty: str
    expected: Category


def load_cases(path: Path | str) -> list[EvalCase]:
    """Load evaluation cases from a JSON lines file, ignoring blank lines."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    cases: list[EvalCase] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(EvalCase.model_validate(json.loads(line)))
    return cases
