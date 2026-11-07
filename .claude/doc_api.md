# API OpenF1: resumo

Resumo dos principais tópicos da [documentação da OpenF1](https://openf1.org/docs/#api-endpoints), consultada em 2026-11-06.

## Visão geral

- API open source com dados de telemetria, cronometragem e sessões da Fórmula 1.
- Projeto não oficial, sem vínculo com as empresas da Fórmula 1.
- Base URL: `https://api.openf1.org/v1/{endpoint}`

## Acesso e autenticação

| Tipo de dado | Requisito |
| --- | --- |
| Histórico (2023 em diante) | Grátis, sem autenticação |
| Tempo real | Assinatura paga e token OAuth2 |

As páginas consultadas não informam os preços nem os valores dos limites de requisição. Elas dizem apenas que a autenticação aumenta esses limites.

### Como obter o token

Envie um `POST` para `https://api.openf1.org/token` com `username` e `password` em `application/x-www-form-urlencoded`. A resposta é um JSON com `access_token`, `expires_in` e `token_type`.

```
Authorization: Bearer SEU_ACCESS_TOKEN
```

- O token expira em 1 hora. Depois disso, é preciso solicitar um novo.
- A troca de credenciais deve ficar no backend, nunca em aplicações client-side.

## Tempo real (MQTT e WebSocket)

A documentação recomenda estes canais para dados ao vivo, pois enviam os dados assim que ficam disponíveis.

| Protocolo | Endereço |
| --- | --- |
| MQTT com TLS | `mqtt.openf1.org`, porta `8883` |
| MQTT sobre WebSocket | `wss://mqtt.openf1.org:8084/mqtt` |

- **Credenciais:** o token é a senha. O usuário pode ser qualquer texto não vazio, ou o e-mail cadastrado se a biblioteca cliente exigir.
- **Tópicos:** seguem os caminhos REST, como `v1/laps` e `v1/location`. O wildcard `#` assina todos, se a biblioteca cliente suportar.
- **Campos extras nas mensagens:** `_id` (identificador crescente, para ordenação) e `_key` (identifica atualizações de um mesmo objeto).

## Formatos e filtros

- **Formato:** JSON por padrão. Para CSV, adicione `csv=true` à URL.
- **Filtros:** qualquer atributo pode ser filtrado, exceto arrays.
- **Operadores:** `=`, `>=`, `<=`, `>`, `<`. Exemplo: `speed>=315`.
- **Vários valores:** repita o parâmetro. Exemplo: `driver_number=4&driver_number=81`.
- **Datas:** use `date`, `date_start` ou `date_end` com operadores. Aceita formatos compatíveis com `dateutil.parser.parse` do Python, como `2021-09-10` e `2021-09-10T14:30:20+00:00`.
- **Mais recente:** `meeting_key=latest` e `session_key=latest` apontam para o evento ou a sessão mais recente ou em andamento.

## Endpoints

Todos os endpoints retornam `meeting_key`, e todos, exceto `meetings`, retornam `session_key`. Por isso, esses dois campos não aparecem na tabela.

| Endpoint | Descrição | Frequência ou restrição | Atributos |
| --- | --- | --- | --- |
| `car_data` | Telemetria de cada carro | Cerca de 3,7 Hz | `brake`, `date`, `driver_number`, `drs`, `n_gear`, `rpm`, `speed`, `throttle` |
| `championship_drivers` (beta) | Classificação do campeonato de pilotos | Só corridas | `driver_number`, `points_current`, `points_start`, `position_current`, `position_start` |
| `championship_teams` (beta) | Classificação do campeonato de equipes | Só corridas | `points_current`, `points_start`, `position_current`, `position_start`, `team_name` |
| `drivers` | Dados dos pilotos em uma sessão | | `broadcast_name`, `country_code`, `driver_number`, `first_name`, `full_name`, `headshot_url`, `last_name`, `name_acronym`, `team_colour`, `team_name` |
| `intervals` | Distância entre pilotos e para o líder | Só corridas, cerca de 4 s | `date`, `driver_number`, `gap_to_leader`, `interval` |
| `laps` | Dados de cada volta | | `date_start`, `driver_number`, `duration_sector_1`, `duration_sector_2`, `duration_sector_3`, `i1_speed`, `i2_speed`, `is_pit_out_lap`, `lap_duration`, `lap_number`, `segments_sector_1`, `segments_sector_2`, `segments_sector_3`, `st_speed` |
| `location` | Posição 3D aproximada do carro | Cerca de 3,7 Hz | `date`, `driver_number`, `x`, `y`, `z` |
| `meetings` | Fins de semana de GP ou de testes | Diária, à meia-noite UTC | `circuit_key`, `circuit_image`, `circuit_info_url`, `circuit_short_name`, `circuit_type`, `country_code`, `country_flag`, `country_key`, `country_name`, `date_end`, `date_start`, `gmt_offset`, `is_cancelled`, `location`, `meeting_name`, `meeting_official_name`, `year` |
| `overtakes` | Trocas de posição entre pilotos | Só corridas | `date`, `overtaken_driver_number`, `overtaking_driver_number`, `position` |
| `pit` | Passagens pelo pit lane | | `date`, `driver_number`, `lane_duration`, `lap_number`, `pit_duration`, `stop_duration` |
| `position` | Posição dos pilotos durante a sessão | | `date`, `driver_number`, `position` |
| `race_control` | Status da sessão, incidentes, bandeiras e safety car | | `category`, `date`, `driver_number`, `flag`, `lap_number`, `message`, `qualifying_phase`, `scope`, `sector` |
| `sessions` | Treinos, classificação, sprint, corrida etc. | Diária, à meia-noite UTC | `circuit_key`, `circuit_short_name`, `country_code`, `country_key`, `country_name`, `date_end`, `date_start`, `gmt_offset`, `is_cancelled`, `location`, `session_name`, `session_type`, `year` |
| `session_result` | Classificação ao final da sessão | Minutos após a publicação oficial | `dnf`, `dns`, `dsq`, `driver_number`, `duration`, `gap_to_leader`, `number_of_laps`, `position` |
| `starting_grid` | Grid de largada | Minutos após a publicação oficial | `driver_number`, `lap_duration`, `position` |
| `stints` | Períodos de pilotagem contínua | | `compound`, `driver_number`, `lap_end`, `lap_start`, `stint_number`, `tyre_age_at_start` |
| `team_radio` | Seleção de rádios entre piloto e equipe | Registro parcial | `date`, `driver_number`, `recording_url` |
| `weather` | Clima na pista | A cada minuto | `air_temperature`, `date`, `humidity`, `pressure`, `rainfall`, `track_temperature`, `wind_direction`, `wind_speed` |

## Exemplos de requisição

```
# Sessões de 2023 em CSV
https://api.openf1.org/v1/sessions?year=2023&csv=true

# Telemetria de um piloto acima de 315 km/h
https://api.openf1.org/v1/car_data?driver_number=55&session_key=9159&speed>=315

# Uma volta específica de um piloto
https://api.openf1.org/v1/laps?session_key=9161&driver_number=63&lap_number=8

# Stints com pneus usados por pelo menos 3 voltas
https://api.openf1.org/v1/stints?session_key=9165&tyre_age_at_start>=3
```

## Tabelas de referência

### Valores de `drs`

| Valor | Significado |
| --- | --- |
| 0, 1 | DRS desligado |
| 8 | Detectado, elegível ao entrar na zona de ativação |
| 10, 12, 14 | DRS ligado |
| 2, 3, 9 | Desconhecido |

### Valores de segmentos em `laps`

| Valor | Significado |
| --- | --- |
| 2048 | Setor amarelo |
| 2049 | Setor verde |
| 2051 | Setor roxo |
| 2064 | Pit lane |
| 0, 2050, 2052, 2068 | Desconhecido ou indisponível |

## Limitações

- **Campos depreciados:** `country_code` em `drivers` e `pit_duration` em `pit` serão removidos após a temporada de 2026.
- **`stop_duration`:** disponível a partir do GP dos EUA de 2024.
- **`laps`:** os valores de segmentos não ficam disponíveis durante corridas, e `date_start` é aproximado.
- **`location`:** mostra o progresso ao longo da pista, mas não a posição lateral.
- **`overtakes`:** os dados podem estar incompletos. Incluem mudanças de posição por pit stop e por punições pós-corrida.
- **`team_radio`:** não é liberado em todas as sessões, e a cobertura caiu bastante a partir de 2026.

## Fontes

- [Documentação da API](https://openf1.org/docs/#api-endpoints)
- [Autenticação e dados ao vivo](https://openf1.org/auth.html)
