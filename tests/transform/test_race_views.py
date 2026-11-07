import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import polars as pl
import pytest

from f1.transform.race_views import (
    FALLBACK_COLOR,
    UNKNOWN_COMPOUND,
    build_roster,
    driver_photo,
    format_duration,
    lap_pace,
    larger_photo,
    positions_by_lap,
    result_text,
    spread_labels,
    team_color,
    tyre_stints,
)

PHOTO = "https://media.formula1.com/x/maxver01.png.transform/1col/image.png"
START = datetime(2024, 3, 2, 15, 0, tzinfo=UTC)


def drivers_frame(*rows: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(
        list(rows),
        schema={
            "driver_number": pl.Int64,
            "name_acronym": pl.String,
            "full_name": pl.String,
            "team_name": pl.String,
            "team_colour": pl.String,
            "headshot_url": pl.String,
        },
    )


def results_frame(*rows: dict[str, Any]) -> pl.DataFrame:
    schema = {
        "driver_number": pl.Int64,
        "position": pl.Int64,
        "number_of_laps": pl.Int64,
        "points": pl.Float64,
        "dnf": pl.Boolean,
        "dns": pl.Boolean,
        "dsq": pl.Boolean,
        "duration": pl.Float64,
        "duration_q1": pl.Float64,
        "duration_q2": pl.Float64,
        "duration_q3": pl.Float64,
        "gap_to_leader": pl.Float64,
        "laps_behind": pl.Int64,
    }
    return pl.DataFrame(
        [{name: row.get(name) for name in schema} for row in rows], schema=schema
    )


def driver(number: int, acronym: str, team: str = "Equipe") -> dict[str, Any]:
    return {
        "driver_number": number,
        "name_acronym": acronym,
        "full_name": f"Piloto {acronym}",
        "team_name": team,
        "team_colour": "3671c6",
        "headshot_url": PHOTO,
    }


def roster_for(*numbers: int) -> pl.DataFrame:
    return build_roster(
        drivers_frame(*(driver(number, f"P{number}") for number in numbers)),
        results_frame(),
    )


@pytest.mark.parametrize(
    ("colour", "expected"),
    [
        ("3671c6", "#3671C6"),
        ("FF8000", "#FF8000"),
        (None, FALLBACK_COLOR),
        ("", FALLBACK_COLOR),
        ("vermelho", FALLBACK_COLOR),
    ],
)
def test_team_color_normaliza_e_usa_cor_neutra(
    colour: str | None, expected: str
) -> None:
    assert team_color(colour) == expected


def test_driver_photo_mantem_endereco_https() -> None:
    assert driver_photo(PHOTO, "VER", "#3671C6") == PHOTO


@pytest.mark.parametrize("url", [None, "", "http://site/foto.png", "javascript:x"])
def test_driver_photo_gera_substituto_com_sigla(url: str | None) -> None:
    photo = driver_photo(url, "COL", "#64C4FF")

    prefix = "data:image/svg+xml;base64,"
    assert photo.startswith(prefix)
    svg = base64.b64decode(photo.removeprefix(prefix)).decode("utf-8")
    assert ">COL</text>" in svg
    assert 'fill="#64C4FF"' in svg


def test_driver_photo_escapa_sigla_no_substituto() -> None:
    photo = driver_photo(None, "<b>", "#3671C6").removeprefix(
        "data:image/svg+xml;base64,"
    )

    assert "&lt;b&gt;" in base64.b64decode(photo).decode("utf-8")


def test_driver_photo_ajusta_cor_do_texto_ao_fundo() -> None:
    def svg_for(color: str) -> str:
        data = driver_photo(None, "AAA", color).split(",", 1)[1]
        return base64.b64decode(data).decode("utf-8")

    assert 'fill="#111111"' in svg_for("#FFFFFF")
    assert 'fill="#FFFFFF"' in svg_for("#000000")


def test_larger_photo_troca_tamanho_e_preserva_substituto() -> None:
    assert larger_photo(PHOTO).endswith(".transform/2col/image.png")
    substitute = driver_photo(None, "COL", "#64C4FF")
    assert larger_photo(substitute) == substitute


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (92.608, "1:32.608"),
        (5504.742, "1:31:44.742"),
        (59.9996, "1:00.000"),
        (0.5, "0:00.500"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"duration": 5504.742, "gap_to_leader": 0.0}, "1:31:44.742"),
        ({"duration": 5527.199, "gap_to_leader": 22.457}, "+22.457 s"),
        ({"laps_behind": 1}, "+1 volta"),
        ({"laps_behind": 2}, "+2 voltas"),
        ({"dnf": True, "laps_behind": 1}, "Abandono"),
        ({"dns": True}, "Não largou"),
        ({"dsq": True, "duration": 5500.0}, "Desclassificado"),
        ({"duration_q1": 90.1, "duration_q2": 89.5}, "1:29.500"),
        ({"duration_q1": 90.1, "duration_q2": None}, "1:30.100"),
        ({}, ""),
    ],
)
def test_result_text(result: dict[str, Any], expected: str) -> None:
    assert result_text(result) == expected


def test_build_roster_ordena_com_sem_posicao_ao_final() -> None:
    roster = build_roster(
        drivers_frame(driver(1, "AAA"), driver(2, "BBB"), driver(3, "CCC")),
        results_frame(
            {"driver_number": 3, "position": None, "number_of_laps": 10, "dnf": True},
            {"driver_number": 1, "position": None, "number_of_laps": 30, "dnf": True},
            {"driver_number": 2, "position": 1, "number_of_laps": 57},
        ),
    )

    assert roster["acronym"].to_list() == ["BBB", "AAA", "CCC"]
    assert roster["order"].to_list() == [0, 1, 2]
    assert roster["result"].to_list()[1] == "Abandono"


def test_build_roster_marca_segundo_piloto_da_equipe_com_tracejado() -> None:
    roster = build_roster(
        drivers_frame(driver(1, "AAA", "X"), driver(2, "BBB", "X"), driver(3, "CCC")),
        results_frame(),
    )

    assert roster["line_dash"].to_list() == [[1, 0], [6, 3], [1, 0]]


def test_build_roster_preenche_piloto_ausente_de_drivers() -> None:
    roster = build_roster(
        drivers_frame(), results_frame({"driver_number": 7, "position": 1})
    )

    row = roster.row(0, named=True)
    assert row["acronym"] == "#7"
    assert row["team_name"] == "Equipe desconhecida"
    assert row["color"] == FALLBACK_COLOR
    assert row["photo"].startswith("data:image/svg+xml")


def test_build_roster_vazio_mantem_colunas() -> None:
    roster = build_roster(drivers_frame(), results_frame())

    assert roster.is_empty()
    assert "photo" in roster.columns


def laps_frame(*rows: tuple[int, int, float | None, bool]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "driver_number": number,
                "lap_number": lap,
                "lap_duration": duration,
                "is_pit_out_lap": pit_out,
                "date_start": START + timedelta(minutes=lap),
            }
            for number, lap, duration, pit_out in rows
        ],
        schema={
            "driver_number": pl.Int64,
            "lap_number": pl.Int64,
            "lap_duration": pl.Float64,
            "is_pit_out_lap": pl.Boolean,
            "date_start": pl.Datetime("us", "UTC"),
        },
    )


def test_lap_pace_filtra_voltas_nao_representativas() -> None:
    laps = laps_frame(
        (1, 1, 90.0, False),
        (1, 2, None, False),
        (1, 3, 95.0, True),
        (1, 4, 120.0, False),
        (1, 5, 96.0, False),
        (2, 1, 92.0, False),
    )

    pace = lap_pace(laps, roster_for(1, 2), [1])

    assert pace["lap_number"].to_list() == [1, 5]
    assert pace["lap_text"].to_list() == ["1:30.000", "1:36.000"]
    assert pace["acronym"].unique().to_list() == ["P1"]


def test_lap_pace_usa_melhor_volta_da_sessao_como_referencia() -> None:
    laps = laps_frame((1, 1, 100.0, False), (2, 1, 90.0, False))

    assert lap_pace(laps, roster_for(1, 2), [1]).is_empty()


def test_lap_pace_sem_tempos_retorna_vazio() -> None:
    laps = laps_frame((1, 1, None, False))

    assert lap_pace(laps, roster_for(1), [1]).is_empty()


def positions_frame(*rows: tuple[int, float, int]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "driver_number": number,
                "date": START + timedelta(minutes=minutes),
                "position": position,
            }
            for number, minutes, position in rows
        ],
        schema={
            "driver_number": pl.Int64,
            "date": pl.Datetime("us", "UTC"),
            "position": pl.Int64,
        },
    )


def test_positions_by_lap_mantem_posicao_ate_a_ultima_volta() -> None:
    laps = laps_frame(
        (1, 1, 90.0, False),
        (1, 2, 90.0, False),
        (1, 3, 90.0, False),
        (1, 4, 90.0, False),
    )
    # Volta 1 começa em START + 1 min. Os eventos ocorrem antes dela e na volta 3.
    positions = positions_frame((1, 0, 5), (1, 3.5, 2))

    result = positions_by_lap(positions, laps, roster_for(1))

    assert result["lap_number"].to_list() == [0, 1, 2, 3, 4]
    assert result["position"].to_list() == [5, 5, 5, 2, 2]
    assert result["acronym"].unique().to_list() == ["P1"]


def test_positions_by_lap_usa_ultimo_evento_da_volta() -> None:
    laps = laps_frame((1, 1, 90.0, False))
    positions = positions_frame((1, 1.2, 3), (1, 1.4, 4))

    result = positions_by_lap(positions, laps, roster_for(1))

    assert result.filter(pl.col("lap_number") == 1)["position"].to_list() == [4]


def test_positions_by_lap_inclui_piloto_sem_voltas() -> None:
    laps = laps_frame((1, 1, 90.0, False))
    positions = positions_frame((2, 0, 20))

    result = positions_by_lap(positions, laps, roster_for(1, 2))

    assert result.to_dicts()[0]["acronym"] == "P2"
    assert result["position"].to_list() == [20]


def test_positions_by_lap_nao_mistura_pilotos_no_preenchimento() -> None:
    laps = laps_frame((1, 1, 90.0, False), (2, 1, 90.0, False), (2, 2, 90.0, False))
    positions = positions_frame((1, 0, 1), (2, 2.5, 2))

    result = positions_by_lap(positions, laps, roster_for(1, 2))

    driver_two = result.filter(pl.col("driver_number") == 2)
    assert driver_two["lap_number"].to_list() == [2]
    assert driver_two["position"].to_list() == [2]


def test_positions_by_lap_sem_eventos_retorna_vazio_com_colunas() -> None:
    laps = laps_frame((1, 1, 90.0, False))

    result = positions_by_lap(positions_frame(), laps, roster_for(1))

    assert result.is_empty()
    assert {"lap_number", "position", "acronym"} <= set(result.columns)


def stints_frame(*rows: tuple[Any, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "driver_number": number,
                "stint_number": stint,
                "compound": compound,
                "lap_start": start,
                "lap_end": end,
                "tyre_age_at_start": 0,
            }
            for number, stint, compound, start, end in rows
        ],
        schema={
            "driver_number": pl.Int64,
            "stint_number": pl.Int64,
            "compound": pl.String,
            "lap_start": pl.Int64,
            "lap_end": pl.Int64,
            "tyre_age_at_start": pl.Int64,
        },
    )


def test_tyre_stints_traduz_compostos_e_calcula_voltas() -> None:
    stints = stints_frame((1, 1, "SOFT", 1, 20), (1, 2, "HARD", 21, 57))

    result = tyre_stints(stints, roster_for(1))

    assert result["compound_label"].to_list() == ["Macio (S)", "Duro (H)"]
    assert result["compound_letter"].to_list() == ["S", "H"]
    assert result["laps"].to_list() == [20, 37]


@pytest.mark.parametrize("compound", ["TEST_UNKNOWN", "UNKNOWN", None])
def test_tyre_stints_trata_composto_desconhecido(compound: str | None) -> None:
    result = tyre_stints(stints_frame((1, 1, compound, 1, 5)), roster_for(1))

    assert result["compound_label"].to_list() == [UNKNOWN_COMPOUND]
    assert result["compound_letter"].to_list() == ["?"]


def test_tyre_stints_descarta_stint_invalido_e_ordena_pelo_resultado() -> None:
    stints = stints_frame(
        (2, 1, "SOFT", 1, 5),
        (1, 1, "SOFT", 1, 5),
        (1, 2, "SOFT", None, 8),
        (1, 3, "SOFT", 9, 8),
    )

    result = tyre_stints(stints, roster_for(1, 2))

    assert result["driver_number"].to_list() == [1, 2]


def test_spread_labels_afasta_valores_proximos() -> None:
    assert spread_labels([10.0, 10.1, 10.2], 1.0) == pytest.approx([9.1, 10.1, 11.1])


def test_spread_labels_mantem_valores_distantes() -> None:
    assert spread_labels([10.0, 20.0], 1.0) == [10.0, 20.0]


def test_spread_labels_lista_vazia() -> None:
    assert spread_labels([], 1.0) == []
