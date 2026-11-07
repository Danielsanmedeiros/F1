import polars as pl
import pytest

from f1.transform.quality import DataQualityError, enforce_quality
from f1.transform.schemas import Column, EndpointSchema

KEYED = EndpointSchema(
    name="keyed",
    columns=(Column("a", pl.Int64), Column("b", pl.Int64), Column("v", pl.String)),
    key=("a", "b"),
)
UNKEYED = EndpointSchema(
    name="unkeyed",
    columns=(Column("a", pl.Int64), Column("v", pl.String)),
    key=(),
)


def test_quality_mantem_dados_validos() -> None:
    df = pl.DataFrame({"a": [1, 1], "b": [1, 2], "v": ["x", "x"]})

    assert enforce_quality(df, KEYED).equals(df)


def test_quality_falha_com_chave_nula() -> None:
    df = pl.DataFrame({"a": [1, 1], "b": [1, None], "v": ["x", "y"]})

    with pytest.raises(DataQualityError, match="1 linhas com nulo"):
        enforce_quality(df, KEYED)


def test_quality_falha_com_chave_duplicada() -> None:
    df = pl.DataFrame({"a": [1, 1, 2], "b": [1, 1, 2], "v": ["x", "y", "z"]})

    with pytest.raises(DataQualityError, match="1 linhas duplicadas"):
        enforce_quality(df, KEYED)


def test_quality_sem_chave_remove_apenas_linhas_identicas() -> None:
    df = pl.DataFrame({"a": [2, 2, 2, 1], "v": ["x", "x", "y", "x"]})

    result = enforce_quality(df, UNKEYED)

    assert result.to_dicts() == [
        {"a": 2, "v": "x"},
        {"a": 2, "v": "y"},
        {"a": 1, "v": "x"},
    ]


def test_quality_aceita_df_vazio() -> None:
    df = pl.DataFrame(schema={"a": pl.Int64, "b": pl.Int64, "v": pl.String})

    assert enforce_quality(df, KEYED).is_empty()
    assert enforce_quality(df, UNKEYED).is_empty()
