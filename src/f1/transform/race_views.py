"""Regras que preparam os dados de uma sessão para visualização."""

import base64
import html
import re
from collections.abc import Sequence
from typing import Any

import polars as pl

FALLBACK_COLOR = "#8A8F98"
UNKNOWN_COMPOUND = "Desconhecido (?)"
COMPOUND_LABELS = {
    "SOFT": "Macio (S)",
    "MEDIUM": "Médio (M)",
    "HARD": "Duro (H)",
    "INTERMEDIATE": "Intermediário (I)",
    "WET": "Chuva (W)",
}
COMPOUND_COLORS = {
    "Macio (S)": "#E03C31",
    "Médio (M)": "#F2C12E",
    "Duro (H)": "#E8E8E8",
    "Intermediário (I)": "#2BA84A",
    "Chuva (W)": "#2F6FDE",
    UNKNOWN_COMPOUND: "#6B7280",
}
SOLID_LINE = (1, 0)
DASHED_LINE = (6, 3)

_HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
_RESULT_COLUMNS = (
    "driver_number",
    "position",
    "number_of_laps",
    "points",
    "dnf",
    "dns",
    "dsq",
    "duration",
    "duration_q1",
    "duration_q2",
    "duration_q3",
    "gap_to_leader",
    "laps_behind",
)
_DRIVER_COLUMNS = (
    "driver_number",
    "name_acronym",
    "full_name",
    "team_name",
    "team_colour",
    "headshot_url",
)
_ROSTER_LOOKUP = ("driver_number", "acronym", "full_name", "team_name", "color")


def team_color(colour: str | None) -> str:
    """Normaliza a cor de uma equipe.

    Args:
        colour: Cor no formato `RRGGBB` informado pela API.

    Returns:
        Cor no formato `#RRGGBB`, ou uma cor neutra se o valor for inválido.
    """
    if colour and _HEX_COLOR.match(colour):
        return f"#{colour.upper()}"
    return FALLBACK_COLOR


def driver_photo(url: str | None, acronym: str, color: str) -> str:
    """Escolhe a imagem de um piloto.

    Args:
        url: Endereço da foto informado pela API.
        acronym: Sigla do piloto, usada na imagem substituta.
        color: Cor da equipe no formato `#RRGGBB`.

    Returns:
        O endereço da foto, se for HTTPS. Caso contrário, uma imagem SVG embutida com
        a sigla do piloto sobre a cor da equipe.
    """
    if url and url.startswith("https://"):
        return url
    ink = "#111111" if _luminance(color) > 0.3 else "#FFFFFF"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<circle cx="50" cy="50" r="50" fill="{html.escape(color)}"/>'
        f'<text x="50" y="50" dy="0.35em" text-anchor="middle" fill="{ink}" '
        'font-family="sans-serif" font-size="32" font-weight="700">'
        f"{html.escape(acronym)}</text></svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def larger_photo(photo: str) -> str:
    """Troca a foto da API pela versão maior, de 206 pixels.

    Args:
        photo: Endereço retornado por `driver_photo`.

    Returns:
        Endereço da versão maior. Imagens substitutas são mantidas.
    """
    return photo.replace(".transform/1col/", ".transform/2col/")


def format_duration(seconds: float) -> str:
    """Formata uma duração como `1:31:44.742` ou `1:32.608`.

    Args:
        seconds: Duração em segundos.

    Returns:
        Duração no formato usado na cronometragem.
    """
    total_ms = round(seconds * 1000)
    minutes, ms = divmod(total_ms, 60_000)
    hours, minutes = divmod(minutes, 60)
    second_text = f"{ms // 1000:02d}.{ms % 1000:03d}"
    if hours:
        return f"{hours}:{minutes:02d}:{second_text}"
    return f"{minutes}:{second_text}"


def result_text(result: dict[str, Any]) -> str:
    """Descreve o resultado de um piloto em uma sessão.

    Args:
        result: Linha de `session_result`.

    Returns:
        Situação, tempo ou diferença para o líder. Vazio se não houver resultado.
    """
    for flag, text in (
        ("dsq", "Desclassificado"),
        ("dns", "Não largou"),
        ("dnf", "Abandono"),
    ):
        if result.get(flag):
            return text

    phases = [result.get(f"duration_q{phase}") for phase in (3, 2, 1)]
    best_phase = next((value for value in phases if value is not None), None)
    if best_phase is not None:
        return format_duration(best_phase)

    laps_behind = result.get("laps_behind")
    if laps_behind:
        return f"+{laps_behind} volta" + ("s" if laps_behind > 1 else "")

    gap = result.get("gap_to_leader")
    if gap:
        return f"+{gap:.3f} s"

    duration = result.get("duration")
    return format_duration(duration) if duration is not None else ""


def build_roster(drivers: pl.DataFrame, results: pl.DataFrame) -> pl.DataFrame:
    """Reúne os pilotos de uma sessão, na ordem do resultado.

    Pilotos sem posição ficam ao final, primeiro os que completaram mais voltas.

    Args:
        drivers: Tabela `drivers` da sessão.
        results: Tabela `session_result` da sessão.

    Returns:
        Uma linha por piloto, com sigla, equipe, cor, foto, estilo de linha, texto do
        resultado e `order`, que começa em 0. O segundo piloto de uma equipe recebe
        linha tracejada, para não depender só da cor.
    """
    merged = (
        drivers.select(_DRIVER_COLUMNS)
        .join(
            results.select(_RESULT_COLUMNS),
            on="driver_number",
            how="full",
            coalesce=True,
        )
        .sort(
            ["position", "number_of_laps", "driver_number"],
            descending=[False, True, False],
            nulls_last=True,
        )
    )

    rows: list[dict[str, Any]] = []
    teams_seen: set[str] = set()
    for order, row in enumerate(merged.iter_rows(named=True)):
        number = row["driver_number"]
        acronym = row["name_acronym"] or f"#{number}"
        team = row["team_name"] or "Equipe desconhecida"
        color = team_color(row["team_colour"])
        rows.append(
            {
                "order": order,
                "driver_number": number,
                "acronym": acronym,
                "full_name": row["full_name"] or acronym,
                "team_name": team,
                "color": color,
                "photo": driver_photo(row["headshot_url"], acronym, color),
                "line_dash": list(DASHED_LINE if team in teams_seen else SOLID_LINE),
                "position": row["position"],
                "number_of_laps": row["number_of_laps"],
                "points": row["points"],
                "result": result_text(row),
            }
        )
        teams_seen.add(team)
    return pl.DataFrame(
        rows,
        schema={
            "order": pl.Int64,
            "driver_number": pl.Int64,
            "acronym": pl.String,
            "full_name": pl.String,
            "team_name": pl.String,
            "color": pl.String,
            "photo": pl.String,
            "line_dash": pl.List(pl.Int64),
            "position": pl.Int64,
            "number_of_laps": pl.Int64,
            "points": pl.Float64,
            "result": pl.String,
        },
    )


def lap_pace(
    laps: pl.DataFrame,
    roster: pl.DataFrame,
    driver_numbers: Sequence[int],
    limit: float = 1.07,
) -> pl.DataFrame:
    """Seleciona as voltas representativas do ritmo dos pilotos.

    Descarta voltas sem tempo, voltas de saída dos boxes e voltas acima de `limit`
    vezes a melhor volta da sessão, como as de entrada nos boxes e de safety car.

    Args:
        laps: Tabela `laps` da sessão.
        roster: Resultado de `build_roster`.
        driver_numbers: Pilotos a manter.
        limit: Múltiplo máximo da melhor volta da sessão.

    Returns:
        Voltas dos pilotos, com `lap_text` e os dados de `roster`.
    """
    timed = laps.filter(pl.col("lap_duration").is_not_null())
    threshold = 0.0 if timed.is_empty() else timed["lap_duration"].min() * limit
    pace = (
        timed.filter(
            pl.col("driver_number").is_in(driver_numbers),
            pl.col("lap_duration") <= threshold,
            ~pl.col("is_pit_out_lap").fill_null(False),
        )
        .select("driver_number", "lap_number", "lap_duration")
        .join(roster.select(_ROSTER_LOOKUP), on="driver_number")
        .sort("driver_number", "lap_number")
    )
    return pace.with_columns(
        pl.Series(
            "lap_text",
            [format_duration(value) for value in pace["lap_duration"]],
            dtype=pl.String,
        )
    )


def positions_by_lap(
    positions: pl.DataFrame, laps: pl.DataFrame, roster: pl.DataFrame
) -> pl.DataFrame:
    """Calcula a posição de cada piloto ao final de cada volta.

    A API só registra as mudanças de posição. Cada mudança é atribuída à volta em
    andamento, e a posição é mantida até a última volta do piloto. A volta 0 é a
    posição antes da primeira volta registrada.

    Args:
        positions: Tabela `position` da sessão.
        laps: Tabela `laps` da sessão.
        roster: Resultado de `build_roster`.

    Returns:
        Uma linha por piloto e volta, com os dados de `roster`.
    """
    lookup = roster.select(_ROSTER_LOOKUP)
    if positions.is_empty():
        return pl.DataFrame(
            schema={"lap_number": pl.Int64, "position": pl.Int64, **lookup.schema}
        )

    lap_starts = (
        laps.filter(pl.col("date_start").is_not_null())
        .select("driver_number", "date_start", "lap_number")
        .sort("date_start")
    )
    events = (
        positions.select("driver_number", "date", "position")
        .sort("date")
        .join_asof(
            lap_starts,
            left_on="date",
            right_on="date_start",
            by="driver_number",
            strategy="backward",
            check_sortedness=False,
        )
        .with_columns(pl.col("lap_number").fill_null(0))
        .group_by("driver_number", "lap_number", maintain_order=True)
        .agg(pl.col("position").last())
    )
    last_laps = (
        pl.concat(
            [
                events.select("driver_number", "lap_number"),
                laps.select("driver_number", "lap_number"),
            ]
        )
        .group_by("driver_number")
        .agg(pl.col("lap_number").max().alias("last_lap"))
    )
    all_laps = last_laps.with_columns(
        pl.int_ranges(0, pl.col("last_lap") + 1, dtype=pl.Int64).alias("lap_number")
    ).explode("lap_number")
    return (
        all_laps.select("driver_number", "lap_number")
        .join(events, on=["driver_number", "lap_number"], how="left")
        .sort("driver_number", "lap_number")
        .with_columns(pl.col("position").forward_fill().over("driver_number"))
        .filter(pl.col("position").is_not_null())
        .join(lookup, on="driver_number")
    )


def tyre_stints(stints: pl.DataFrame, roster: pl.DataFrame) -> pl.DataFrame:
    """Prepara os stints para o gráfico de estratégia de pneus.

    Args:
        stints: Tabela `stints` da sessão.
        roster: Resultado de `build_roster`.

    Returns:
        Stints válidos, com o composto traduzido, a letra do composto, a quantidade
        de voltas e os dados de `roster`.
    """
    known = stints.filter(
        pl.col("lap_start").is_not_null(),
        pl.col("lap_end").is_not_null(),
        pl.col("lap_end") >= pl.col("lap_start"),
    )
    labelled = known.with_columns(
        pl.col("compound")
        .replace_strict(
            COMPOUND_LABELS, default=UNKNOWN_COMPOUND, return_dtype=pl.String
        )
        .fill_null(UNKNOWN_COMPOUND)
        .alias("compound_label"),
        (pl.col("lap_end") - pl.col("lap_start") + 1).alias("laps"),
    )
    return (
        labelled.with_columns(
            pl.col("compound_label").str.extract(r"\((.)\)$").alias("compound_letter")
        )
        .select(
            "driver_number",
            "stint_number",
            "lap_start",
            "lap_end",
            "laps",
            "tyre_age_at_start",
            "compound_label",
            "compound_letter",
        )
        .join(roster.select("driver_number", "acronym", "order"), on="driver_number")
        .sort("order", "stint_number")
    )


def spread_labels(values: Sequence[float], min_gap: float) -> list[float]:
    """Afasta os rótulos de um eixo até que não se sobreponham.

    Rótulos próximos formam um grupo, centrado na média dos seus valores.

    Args:
        values: Posições originais, em ordem crescente.
        min_gap: Distância mínima entre rótulos, na unidade do eixo.

    Returns:
        Posições ajustadas, na mesma ordem.
    """
    groups: list[list[float]] = []
    for value in values:
        groups.append([value])
        while len(groups) > 1 and _groups_overlap(groups[-2], groups[-1], min_gap):
            last = groups.pop()
            groups[-1].extend(last)

    spread: list[float] = []
    for group in groups:
        center = sum(group) / len(group)
        spread.extend(
            center + (index - (len(group) - 1) / 2) * min_gap
            for index in range(len(group))
        )
    return spread


def _groups_overlap(lower: list[float], upper: list[float], min_gap: float) -> bool:
    lower_top = sum(lower) / len(lower) + (len(lower) - 1) / 2 * min_gap
    upper_bottom = sum(upper) / len(upper) - (len(upper) - 1) / 2 * min_gap
    return upper_bottom - lower_top < min_gap


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
