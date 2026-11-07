# Dados

Cada tabela é uma view no DuckDB (`data/f1.duckdb`) sobre arquivos Parquet. As colunas da pasta de partição, como `year`, ficam disponíveis na view.

## Tabelas

| Tabela | Conteúdo | Partição | Chave |
| --- | --- | --- | --- |
| `meetings` | Fins de semana de GP ou de testes | `year` | `meeting_key` |
| `sessions` | Treinos, classificação, sprint e corrida | `year` | `session_key` |
| `drivers` | Pilotos em cada sessão | `year`, `session_key` | `session_key`, `driver_number` |
| `laps` | Voltas | `year`, `session_key` | `session_key`, `driver_number`, `lap_number` |
| `stints` | Períodos de pilotagem contínua | `year`, `session_key` | `session_key`, `driver_number`, `stint_number` |
| `pit` | Passagens pelo pit lane | `year`, `session_key` | `session_key`, `driver_number`, `date` |
| `position` | Posição durante a sessão | `year`, `session_key` | `session_key`, `driver_number`, `date` |
| `session_result` | Classificação ao final da sessão | `year`, `session_key` | `session_key`, `driver_number` |
| `starting_grid` | Grid de largada | `year`, `session_key` | `session_key`, `driver_number` |
| `weather` | Clima na pista | `year`, `session_key` | `session_key`, `date` |
| `race_control` | Bandeiras, incidentes e safety car | `year`, `session_key` | Sem chave natural: apenas linhas idênticas são removidas |

Exemplo de partição: `data/laps/year=2024/session_key=9165/data.parquet`.

## Colunas de `session_result`

Na API, `duration` e `gap_to_leader` mudam de formato conforme a sessão. Para manter o schema estável, o pipeline os separa em colunas numéricas.

| Valor na API | Colunas |
| --- | --- |
| Número | `duration` ou `gap_to_leader` |
| Texto como `+1 LAP` | `laps_behind`, com `gap_to_leader` nulo |
| Lista com Q1, Q2 e Q3 | `duration_q1` a `duration_q3` ou `gap_to_leader_q1` a `gap_to_leader_q3` |

## Limitações herdadas da API

- **Campos depreciados:** `country_code` (`drivers`) e `pit_duration` (`pit`) serão removidos após a temporada de 2026. Por isso, são opcionais.
- **`stop_duration` (`pit`):** disponível a partir do GP dos EUA de 2024.
- **`laps`:** os valores de segmentos não ficam disponíveis durante corridas, e `date_start` é aproximado.
- **Calendário:** `meetings` e `sessions` são atualizadas à meia-noite UTC, então sessões recentes podem aparecer apenas no dia seguinte.
- **Resultados:** `session_result` e `starting_grid` são publicados minutos após o resultado oficial. Uma carga logo após a sessão grava partições vazias, que precisam de `--force` para serem recarregadas.
- **Correções:** dados corrigidos depois da carga também exigem `--force`.

## Divergências em relação ao `doc_api.md`

Confirmadas em 2026-11-06, em amostras de corrida, classificação e treino do GP do Bahrein de 2024.

- **Bloqueio durante sessões ao vivo:** o resumo informa que o histórico é gratuito e sem autenticação, mas, enquanto acontece uma sessão, a API responde HTTP 401 a qualquer acesso sem autenticação, inclusive ao histórico.
- **Consulta sem resultados:** a API responde HTTP 404 com `{"detail":"No results found."}`, e não uma lista vazia.
- **`starting_grid`:** o grid fica na sessão de classificação. Em 2024, todas as 30 sessões `Qualifying` e `Sprint Qualifying` têm grid, e nenhuma sessão `Race` ou `Sprint` tem.
- **`points` (`session_result`):** campo não documentado, presente nas corridas e ausente na amostra de classificação.
- **`humidity` (`weather`):** a documentação mostra um inteiro, mas a API retorna número decimal.
- **`team_colour` (`drivers`):** pode vir em letras minúsculas, como `3671c6`.

## Nulos observados

Os campos abaixo têm nulos nos dados de 2024. Os nulos são preservados, e consultas devem considerá-los.

| Tabela | Campos |
| --- | --- |
| `laps` | `date_start`, `lap_duration`, `duration_sector_1`, `duration_sector_3`, `i1_speed`, `st_speed` |
| `pit` | `lane_duration`, `pit_duration`, `stop_duration` |
| `race_control` | `driver_number`, `flag`, `lap_number`, `qualifying_phase`, `scope`, `sector` |
| `session_result` | `duration` e `gap_to_leader`, em pilotos com volta de atraso, abandono (`dnf`), sem largada (`dns`) ou desclassificados (`dsq`). `position`, em parte dos abandonos e das não largadas, nas desclassificações e em 4 registros de classificação sem nenhuma dessas marcas |

## Exemplos de consulta

Melhor volta de cada piloto em uma corrida:

```sql
SELECT d.name_acronym, d.team_name, min(l.lap_duration) AS best_lap
FROM laps AS l
JOIN drivers AS d USING (session_key, driver_number)
JOIN sessions AS s USING (session_key)
WHERE s.year = 2024 AND s.location = 'Sakhir' AND s.session_name = 'Race'
GROUP BY ALL
ORDER BY best_lap;
```

Stints de cada piloto na corrida do GP do Bahrein de 2024, com o composto usado:

```sql
SELECT d.name_acronym, st.stint_number, st.compound, st.lap_start, st.lap_end
FROM stints AS st
JOIN drivers AS d USING (session_key, driver_number)
WHERE st.session_key = 9472
ORDER BY d.name_acronym, st.stint_number;
```
