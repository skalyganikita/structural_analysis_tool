"""The packaged example models and result tables remain portable."""

import json
from io import StringIO
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fea.examples import examples
from fea.solver import solve, validate
from fea.reporting import node_table, section_table, end_force_table


@pytest.mark.parametrize("name", list(examples()))
def test_json_round_trip_and_csv(name):
    model = examples()[name]
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / (name.lower().replace(" ", "_") + ".json")
    )
    loaded = json.loads(path.read_text())
    validate(loaded)
    result = solve(loaded, "Service")
    original = solve(model, "Service")
    np.testing.assert_allclose(result.d, original.d, rtol=1e-12, atol=1e-14)
    for table in [node_table(result), section_table(result), end_force_table(result)]:
        restored = pd.read_csv(StringIO(table.to_csv(index=False)))
        assert list(restored.columns) == list(table.columns)
        assert len(restored) == len(table)
        assert np.isfinite(restored.select_dtypes("number")).all().all()
    assert len(section_table(result)) >= 201 * len(model["elements"])
