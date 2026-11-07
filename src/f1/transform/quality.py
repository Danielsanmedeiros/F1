"""Validações de qualidade aplicadas antes da gravação."""

import polars as pl

from f1.transform.schemas import EndpointSchema


class DataQualityError(ValueError):
    """Os dados violam uma regra de qualidade."""


def enforce_quality(df: pl.DataFrame, schema: EndpointSchema) -> pl.DataFrame:
    """Aplica as regras de qualidade de um endpoint.

    Endpoints com chave não podem ter nulos nem duplicatas nela. Endpoints sem chave
    natural têm apenas as linhas idênticas removidas.

    Args:
        df: DataFrame normalizado.
        schema: Contrato do endpoint.

    Returns:
        DataFrame pronto para gravação.

    Raises:
        DataQualityError: Se a chave tiver nulos ou duplicatas.
    """
    if not schema.key:
        return df.unique(maintain_order=True)

    key = list(schema.key)
    null_rows = df.filter(pl.any_horizontal(pl.col(key).is_null())).height
    if null_rows:
        raise DataQualityError(
            f"{schema.name}: {null_rows} linhas com nulo na chave {key}"
        )

    duplicated_rows = df.height - df.select(key).unique().height
    if duplicated_rows:
        raise DataQualityError(
            f"{schema.name}: {duplicated_rows} linhas duplicadas na chave {key}"
        )
    return df
