"""Dashboard de análise de corrida, executado com `streamlit run`."""

import html
import os
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import duckdb
import polars as pl
import streamlit as st
from dotenv import load_dotenv

from f1.config.settings import settings_from_env
from f1.extract import warehouse
from f1.transform.normalize import select_finished_sessions
from f1.transform.race_views import (
    COMPOUND_COLORS,
    build_roster,
    format_duration,
    lap_pace,
    larger_photo,
    positions_by_lap,
    spread_labels,
    tyre_stints,
)

MAX_HIGHLIGHTED_DRIVERS = 4
CONTEXT_LINE_COLOR = "#4A4F5C"
RACE_SESSION_TYPE = "Race"
TABLE_ROW_HEIGHT = 64
TABLE_HEADER_HEIGHT = 38
LABEL_COLOR = "#FAFAFA"
# O Streamlit desconta a legenda e os eixos da altura pedida para o gráfico.
CHART_CHROME_HEIGHT = 155
POSITION_ROW_HEIGHT = 32
PACE_CHART_HEIGHT = 300 + CHART_CHROME_HEIGHT
# Distância mínima entre os rótulos das linhas, como fração da escala de tempos.
LABEL_GAP_SHARE = 0.06


@st.cache_data(ttl=600, show_spinner=False)
def _load(db_path: str, table: str, **filters: int) -> pl.DataFrame:
    return warehouse.read_table(Path(db_path), table, **filters)


def _default_index(options: list[int], preferred: int | None) -> int:
    return options.index(preferred) if preferred in options else len(options) - 1


def _select_session(
    columns: list, sessions: pl.DataFrame, meetings: pl.DataFrame
) -> dict | None:
    """Mostra os seletores e retorna a sessão escolhida."""
    finished_keys = select_finished_sessions(sessions, datetime.now(UTC))
    finished = sessions.filter(pl.col("session_key").is_in(finished_keys)).sort(
        "date_start"
    )
    if finished.is_empty():
        return None

    years = sorted(finished["year"].unique().to_list(), reverse=True)
    year = columns[0].selectbox("Temporada", years)
    in_year = finished.filter(pl.col("year") == year)

    meeting_names = dict(meetings.select("meeting_key", "meeting_name").iter_rows())
    meeting_keys = in_year["meeting_key"].unique(maintain_order=True).to_list()
    last_race = in_year.filter(pl.col("session_name") == "Race")
    preferred_meeting = last_race["meeting_key"][-1] if last_race.height else None
    meeting_key = columns[1].selectbox(
        "Grande Prêmio",
        meeting_keys,
        index=_default_index(meeting_keys, preferred_meeting),
        format_func=lambda key: meeting_names.get(key, f"Evento {key}"),
    )

    in_meeting = in_year.filter(pl.col("meeting_key") == meeting_key)
    session_keys = in_meeting["session_key"].to_list()
    names = dict(in_meeting.select("session_key", "session_name").iter_rows())
    race = in_meeting.filter(pl.col("session_name") == "Race")
    session_key = columns[2].selectbox(
        "Sessão",
        session_keys,
        index=_default_index(
            session_keys, race["session_key"][0] if race.height else None
        ),
        format_func=lambda key: names[key],
    )
    session = in_meeting.filter(pl.col("session_key") == session_key).row(0, named=True)
    return session | {"meeting_name": meeting_names.get(meeting_key, "")}


def _driver_card_html(driver: dict, position_label: str) -> str:
    photo = html.escape(larger_photo(driver["photo"]), quote=True)
    color = html.escape(driver["color"], quote=True)
    name = html.escape(driver["full_name"])
    team = html.escape(driver["team_name"])
    result = html.escape(driver["result"])
    return (
        '<div style="display:flex;gap:16px;align-items:center;padding:12px 0">'
        f'<img src="{photo}" alt="Foto de {name}" width="112" height="112" '
        f'style="border-radius:50%;border:3px solid {color};flex:none;'
        'background:#1F2430;object-fit:cover">'
        '<div style="min-width:0">'
        f'<div style="font-size:14px;opacity:.7">{html.escape(position_label)}</div>'
        f'<div style="font-size:20px;font-weight:600;line-height:1.25">{name}</div>'
        f'<div style="font-size:14px;opacity:.7">{team}</div>'
        f'<div style="font-size:15px;margin-top:4px">{result}</div>'
        "</div></div>"
    )


def _render_podium(roster: pl.DataFrame) -> None:
    podium = roster.filter(pl.col("position").is_not_null()).head(3)
    if podium.is_empty():
        return
    for column, driver in zip(
        st.columns(3), podium.iter_rows(named=True), strict=False
    ):
        with column:
            st.html(_driver_card_html(driver, f"{driver['position']}º lugar"))


def _render_results(roster: pl.DataFrame) -> None:
    st.subheader("Classificação")
    table = roster.with_columns(
        pl.col("position").cast(pl.String).fill_null("–")
    ).select(
        "position",
        "photo",
        "acronym",
        "full_name",
        "team_name",
        "result",
        "number_of_laps",
        "points",
    )
    # Treinos não têm pontos, por exemplo: uma coluna toda nula só atrapalharia.
    table = table.select(
        column.name for column in table if column.null_count() < table.height
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        row_height=TABLE_ROW_HEIGHT,
        height=table.height * TABLE_ROW_HEIGHT + TABLE_HEADER_HEIGHT,
        column_config={
            "position": st.column_config.TextColumn("Pos.", width="small"),
            "photo": st.column_config.ImageColumn("Foto", width="small"),
            "acronym": st.column_config.TextColumn("Sigla", width="small"),
            "full_name": "Piloto",
            "team_name": "Equipe",
            "result": "Resultado",
            "number_of_laps": st.column_config.NumberColumn("Voltas", width="small"),
            "points": st.column_config.NumberColumn("Pontos", width="small"),
        },
    )


def _render_highlighted(highlighted: pl.DataFrame) -> None:
    chips = []
    for driver in highlighted.iter_rows(named=True):
        photo = html.escape(driver["photo"], quote=True)
        color = html.escape(driver["color"], quote=True)
        name = html.escape(driver["full_name"])
        chips.append(
            '<div style="display:flex;gap:8px;align-items:center">'
            f'<img src="{photo}" alt="Foto de {name}" width="48" height="48" '
            f'style="border-radius:50%;border:2px solid {color};background:#1F2430">'
            f'<span style="font-size:14px">{name}</span></div>'
        )
    st.html(
        '<div style="display:flex;flex-wrap:wrap;gap:12px 24px;margin:4px 0 8px">'
        f"{''.join(chips)}</div>"
    )


def _driver_scales(highlighted: pl.DataFrame) -> tuple[alt.Color, alt.StrokeDash]:
    domain = highlighted["acronym"].to_list()
    color = alt.Color(
        "acronym:N",
        scale=alt.Scale(domain=domain, range=highlighted["color"].to_list()),
        legend=alt.Legend(title="Piloto", orient="top"),
    )
    dash = alt.StrokeDash(
        "acronym:N",
        scale=alt.Scale(domain=domain, range=highlighted["line_dash"].to_list()),
        legend=None,
    )
    return color, dash


def _pace_chart(pace: pl.DataFrame, highlighted: pl.DataFrame) -> alt.LayerChart:
    color, dash = _driver_scales(highlighted)
    hover = alt.selection_point(
        fields=["lap_number"], nearest=True, on="pointerover", empty=False
    )
    tooltip = [
        alt.Tooltip("full_name:N", title="Piloto"),
        alt.Tooltip("lap_number:Q", title="Volta"),
        alt.Tooltip("lap_text:N", title="Tempo"),
    ]
    base = alt.Chart(pace).encode(
        x=alt.X("lap_number:Q", title="Volta", axis=alt.Axis(tickMinStep=1)),
        y=alt.Y(
            "lap_duration:Q",
            title="Tempo de volta (s)",
            scale=alt.Scale(zero=False, nice=True),
        ),
        color=color,
    )
    lines = base.mark_line(strokeWidth=2).encode(strokeDash=dash)
    targets = (
        base.mark_point(size=500, opacity=0).encode(tooltip=tooltip).add_params(hover)
    )
    points = base.mark_point(size=70, filled=True, opacity=1).transform_filter(hover)
    rule = (
        alt.Chart(pace)
        .mark_rule(strokeWidth=1, color=CONTEXT_LINE_COLOR)
        .encode(x="lap_number:Q")
        .transform_filter(hover)
    )
    ends = (
        pace.sort("lap_number")
        .group_by("acronym", maintain_order=True)
        .last()
        .sort("lap_duration")
    )
    time_range = pace["lap_duration"].max() - pace["lap_duration"].min()
    labels = (
        alt.Chart(
            ends.with_columns(
                pl.Series(
                    "label_y",
                    spread_labels(
                        ends["lap_duration"].to_list(),
                        time_range * LABEL_GAP_SHARE,
                    ),
                )
            )
        )
        .mark_text(align="left", dx=8, fontSize=12, color=LABEL_COLOR)
        .encode(x="lap_number:Q", y="label_y:Q", text="acronym:N")
    )
    return alt.layer(lines, rule, targets, points, labels).properties(
        height=PACE_CHART_HEIGHT, padding={"right": 44}
    )


def _positions_chart(
    positions: pl.DataFrame, highlighted: pl.DataFrame
) -> alt.LayerChart:
    numbers = highlighted["driver_number"].to_list()
    selected = positions.filter(pl.col("driver_number").is_in(numbers))
    others = positions.filter(~pl.col("driver_number").is_in(numbers))
    largest = positions["position"].max()

    x = alt.X("lap_number:Q", title="Volta", axis=alt.Axis(tickMinStep=1, grid=False))
    y = alt.Y(
        "position:Q",
        title="Posição",
        scale=alt.Scale(domain=[largest, 1], nice=False),
        axis=alt.Axis(values=list(range(1, largest + 1)), grid=False),
    )
    color, dash = _driver_scales(highlighted)
    tooltip = [
        alt.Tooltip("full_name:N", title="Piloto"),
        alt.Tooltip("lap_number:Q", title="Volta"),
        alt.Tooltip("position:Q", title="Posição"),
    ]
    context = (
        alt.Chart(others)
        .mark_line(strokeWidth=1, interpolate="step-after", color=CONTEXT_LINE_COLOR)
        .encode(x=x, y=y, detail="acronym:N", tooltip=tooltip)
    )
    lines = (
        alt.Chart(selected)
        .mark_line(strokeWidth=2, interpolate="step-after")
        .encode(x=x, y=y, color=color, strokeDash=dash)
    )
    targets = (
        alt.Chart(selected)
        .mark_point(size=400, opacity=0)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    ends = (
        selected.sort("lap_number")
        .group_by("driver_number", maintain_order=True)
        .last()
        .join(highlighted.select("driver_number", "photo"), on="driver_number")
    )
    faces = (
        alt.Chart(ends)
        .mark_image(width=28, height=28, xOffset=18)
        .encode(x=x, y=y, url="photo:N", tooltip=tooltip)
    )
    return alt.layer(context, lines, targets, faces).properties(
        height=largest * POSITION_ROW_HEIGHT + CHART_CHROME_HEIGHT,
        padding={"right": 44},
    )


def _tyre_chart(stints: pl.DataFrame) -> alt.LayerChart:
    order = stints.sort("order")["acronym"].unique(maintain_order=True).to_list()
    y = alt.Y("acronym:N", title=None, sort=order)
    tooltip = [
        alt.Tooltip("acronym:N", title="Piloto"),
        alt.Tooltip("compound_label:N", title="Composto"),
        alt.Tooltip("lap_start:Q", title="Da volta"),
        alt.Tooltip("lap_end:Q", title="Até a volta"),
        alt.Tooltip("laps:Q", title="Voltas"),
        alt.Tooltip("tyre_age_at_start:Q", title="Idade inicial"),
    ]
    bars = (
        alt.Chart(stints)
        .transform_calculate(start="datum.lap_start - 1", end="datum.lap_end - 0.15")
        .mark_bar(height=16, cornerRadius=4)
        .encode(
            x=alt.X("start:Q", title="Volta", axis=alt.Axis(tickMinStep=1)),
            x2="end:Q",
            y=y,
            color=alt.Color(
                "compound_label:N",
                scale=alt.Scale(
                    domain=list(COMPOUND_COLORS), range=list(COMPOUND_COLORS.values())
                ),
                legend=alt.Legend(title="Composto", orient="top"),
            ),
            tooltip=tooltip,
        )
    )
    letters = (
        alt.Chart(stints.filter(pl.col("laps") >= 3))
        .transform_calculate(middle="(datum.lap_start - 1 + datum.lap_end) / 2")
        .mark_text(fontSize=11, fontWeight=600, color="#111111")
        .encode(x="middle:Q", y=y, text="compound_letter:N", tooltip=tooltip)
    )
    return alt.layer(bars, letters).properties(
        height=len(order) * 26 + CHART_CHROME_HEIGHT
    )


def _show_with_table(chart: alt.LayerChart, table: pl.DataFrame) -> None:
    st.altair_chart(chart, width="stretch")
    with st.expander("Ver dados em tabela"):
        st.dataframe(table, hide_index=True, width="stretch")


def _render_session(
    db_path: str, session: dict, highlight_column: st.delta_generator.DeltaGenerator
) -> None:
    session_key = session["session_key"]
    filters = {"session_key": session_key}
    drivers = _load(db_path, "drivers", **filters)
    results = _load(db_path, "session_result", **filters)
    roster = build_roster(drivers, results)

    st.title(f"{session['meeting_name']}: {session['session_name']}")
    date_start = session["date_start"]
    st.caption(f"{session['location']}, {date_start:%d/%m/%Y}")

    if roster.is_empty():
        st.info("Esta sessão não tem pilotos registrados.")
        return

    names = dict(roster.select("driver_number", "full_name").iter_rows())
    numbers = roster["driver_number"].to_list()
    selected = highlight_column.multiselect(
        f"Pilotos em destaque (até {MAX_HIGHLIGHTED_DRIVERS})",
        numbers,
        default=numbers[:3],
        max_selections=MAX_HIGHLIGHTED_DRIVERS,
        format_func=lambda number: names[number],
        key=f"highlighted-{session_key}",
    )
    highlighted = roster.filter(pl.col("driver_number").is_in(selected))

    _render_podium(roster)
    _render_results(roster)

    laps = _load(db_path, "laps", **filters)

    st.subheader("Ritmo por volta")
    best_lap = laps["lap_duration"].min()
    pace = lap_pace(laps, roster, selected)
    if highlighted.is_empty():
        st.info("Escolha ao menos um piloto em destaque.")
    elif pace.is_empty():
        st.info("Não há tempos de volta para os pilotos escolhidos.")
    else:
        _render_highlighted(highlighted)
        _show_with_table(
            _pace_chart(pace, highlighted),
            pace.select("full_name", "lap_number", "lap_text"),
        )
        st.caption(
            f"Melhor volta da sessão: {format_duration(best_lap)}. Voltas de saída "
            "dos boxes e acima de 107% da melhor volta ficam de fora, como as de "
            "entrada nos boxes e de safety car."
        )

    if session["session_type"] == RACE_SESSION_TYPE:
        st.subheader("Evolução das posições")
        position_events = _load(db_path, "position", **filters)
        positions = positions_by_lap(position_events, laps, roster)
        if positions.is_empty():
            st.info("Não há dados de posição nesta sessão.")
        elif highlighted.is_empty():
            st.info("Escolha ao menos um piloto em destaque.")
        else:
            _show_with_table(
                _positions_chart(positions, highlighted),
                positions.filter(pl.col("driver_number").is_in(selected)).select(
                    "full_name", "lap_number", "position"
                ),
            )

    st.subheader("Estratégia de pneus")
    stints = tyre_stints(_load(db_path, "stints", **filters), roster)
    if stints.is_empty():
        st.info("Não há dados de pneus nesta sessão.")
    else:
        _show_with_table(
            _tyre_chart(stints),
            stints.select(
                "acronym", "stint_number", "compound_label", "lap_start", "lap_end"
            ),
        )


def main() -> None:
    """Monta a página do dashboard."""
    st.set_page_config(page_title="F1", page_icon="🏁", layout="wide")
    load_dotenv()
    db_path = settings_from_env(os.environ).db_path
    if not db_path.exists():
        st.error("O banco de dados ainda não existe. Carregue os dados com:")
        st.code("poetry run f1-ingest --year 2024", language="bash")
        return

    filters = st.columns([1, 2, 1, 3])
    try:
        sessions = _load(str(db_path), "sessions")
        meetings = _load(str(db_path), "meetings")
        session = _select_session(filters, sessions, meetings)
        if session is None:
            st.info("Ainda não há sessões encerradas nos dados carregados.")
            return
        _render_session(str(db_path), session, filters[3])
    except duckdb.Error as exc:
        st.error(f"Não foi possível ler os dados: {exc}")


if __name__ == "__main__":
    main()
