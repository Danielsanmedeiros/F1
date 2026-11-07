# Plano de criação do projeto F1

## Contexto

O projeto F1 vai coletar dados históricos da [API OpenF1](doc_api.md) e disponibilizá-los para análise de corrida em arquivos locais. A construção segue a skill [python-data-engineering-standards](.claude/skills/python-data-engineering-standards/SKILL.md).

**Resultado esperado:** um comando que carrega uma ou mais temporadas em Parquet, pode ser repetido sem duplicar dados e deixa tudo consultável em DuckDB.

### Decisões

| Tema | Decisão |
| --- | --- |
| Dados | Só histórico (2023 em diante), via REST, sem autenticação |
| Endpoints | `meetings`, `sessions`, `drivers`, `laps`, `stints`, `pit`, `position`, `session_result`, `starting_grid`, `weather`, `race_control` |
| Destino | Parquet local particionado, consultado com views no DuckDB |
| Fora do escopo | Tempo real (MQTT, WebSocket, OAuth2), `car_data`, `location`, `intervals`, `overtakes`, `team_radio` e os endpoints de campeonato (beta), agendamento e deploy |

### Estado atual do repositório

- Já existem `pyproject.toml` (pacote `f1`, Python `>=3.13,<4.0`), `.python-version` (3.13.13), `.venv`, `src/f1/__init__.py` e `tests/__init__.py`. Por isso, o `poetry new` da skill não será usado.
- Faltam dependências, `.gitignore`, `docs/`, `mkdocs.yml` e as configurações de Ruff e pytest.
- O `README.md` aparece como binário no `git diff`. Verificar a codificação e regravá-lo em UTF-8.
- Esta sessão tem `VIRTUAL_ENV` apontando para o Python 3.15.0b1 global. Sem limpar a variável, o Poetry instala os pacotes lá, e não no `.venv`.

## Arquitetura

Stack de runtime: `httpx` (HTTP), `polars` (DataFrames e Parquet), `duckdb` (consulta) e `python-dotenv` (`.env`).

```text
src/f1/
├── config/settings.py      # Configurações lidas do ambiente
├── extract/client.py       # Cliente REST da OpenF1
├── transform/schemas.py    # Colunas, tipos e chaves de cada endpoint
├── transform/normalize.py  # Registros da API para DataFrame tipado
├── transform/quality.py    # Validações de saída
├── load/parquet.py         # Escrita atômica por partição
├── load/duckdb.py          # Views sobre os arquivos Parquet
└── pipelines/ingest.py     # Orquestração e CLI (f1-ingest)
```

`extract/`, `transform/` e `load/` não importam uns aos outros; quem os combina é `pipelines/`. O pacote `utils/` só será criado se surgir código realmente genérico.

Fluxo:

1. Buscar `meetings` e `sessions` por `year`.
2. Selecionar as sessões encerradas (`date_end` no passado) e não canceladas (`is_cancelled`).
3. Para cada sessão, buscar os demais endpoints por `session_key`.
4. Normalizar, validar e gravar cada partição.
5. Recriar as views no DuckDB.

Partições, ignoradas no Git:

```text
data/meetings/year=2024/data.parquet
data/sessions/year=2024/data.parquet
data/laps/year=2024/session_key=9165/data.parquet
data/f1.duckdb
```

### Regras do pipeline

- **Idempotência:** cada partição é gravada em um arquivo temporário e substituída com `os.replace`. Repetir a carga troca o arquivo, sem duplicar linhas.
- **Carga incremental:** partições existentes são ignoradas, e `--force` as recarrega. Resultado vazio grava um Parquet vazio com o schema, para não repetir a requisição.
- **Reprodutibilidade:** nunca usar `session_key=latest` ou `meeting_key=latest`, pois o resultado muda com o tempo.
- **Falhas:** repetir com espera em caso de 429, 5xx e erro de rede, respeitando `Retry-After`. Se persistir, registrar a partição, seguir com as demais e encerrar com código 1, listando as falhas. Repetir o comando retoma de onde parou.
- **Limites de requisição:** o `doc_api.md` não informa os valores, então o intervalo entre chamadas fica configurável. Estimativa: cerca de 1.100 requisições por temporada, a confirmar na primeira carga.
- **Schema:** coluna obrigatória ausente ou tipo inválido falha a partição. Coluna desconhecida gera aviso e é descartada.
- **Qualidade:** antes de gravar, validar que as chaves não têm nulos nem duplicatas.
- **Campos depreciados:** `country_code` (`drivers`) e `pit_duration` (`pit`) serão removidos após 2026, então entram como opcionais. `stop_duration` só existe a partir do GP dos EUA de 2024 e também é opcional.

### Chaves por endpoint

Hipóteses a confirmar na fase 2:

| Endpoint | Chave |
| --- | --- |
| `meetings` | `meeting_key` |
| `sessions` | `session_key` |
| `drivers`, `session_result`, `starting_grid` | `session_key`, `driver_number` |
| `laps` | `session_key`, `driver_number`, `lap_number` |
| `stints` | `session_key`, `driver_number`, `stint_number` |
| `pit`, `position` | `session_key`, `driver_number`, `date` |
| `weather` | `session_key`, `date` |
| `race_control` | Sem chave natural: remover apenas linhas idênticas |

## Fases

Cada fase termina com o checklist da skill passando, a partir do momento em que as ferramentas existirem. Nenhum commit será feito sem pedido explícito.

### Fase 0: Ambiente

```powershell
Remove-Item Env:VIRTUAL_ENV
poetry env info --path
```

**Pronto quando:** o caminho impresso for `...\F1\.venv`. Sem isso, não instalar nada.

### Fase 1: Base do projeto

```bash
poetry add httpx polars duckdb python-dotenv
poetry add --group dev ruff pytest pytest-cov pre-commit
poetry add --group docs mkdocs-material "mkdocstrings[python]"
poetry run pre-commit install
```

- Completar o `pyproject.toml` conforme a skill, trocando `projeto` por `f1` (`known-first-party`, `--cov=src/f1`, `target-version = "py313"`).
- Adicionar `f1-ingest = "f1.pipelines.ingest:main"` em `[tool.poetry.scripts]`. O aviso de depreciação do `poetry check` é esperado.
- Criar `.gitignore` (lista da skill mais `data/`), `.env.example`, `.pre-commit-config.yaml` e `config/settings.py`.
- Variáveis: `OPENF1_BASE_URL`, `OPENF1_REQUEST_INTERVAL_SECONDS`, `F1_DATA_DIR` e `LOG_LEVEL`.

**Pronto quando:** `poetry run ruff check .` passar e `poetry.lock` listar as dependências.

### Fase 2: Contrato da API

O `doc_api.md` traz os nomes dos atributos, mas não os tipos. Antes de fechar os schemas, consultar a API real em uma sessão de corrida e uma de classificação para confirmar:

- tipos e nulos de cada atributo;
- campos com formato variável, como `duration` e `gap_to_leader` em `session_result`;
- resposta de consulta sem resultados (lista vazia ou erro 404);
- chaves da tabela acima.

**Pronto quando:** `transform/schemas.py` refletir os 11 endpoints e as divergências em relação ao `doc_api.md` estiverem anotadas em `docs/dados.md`.

### Fase 3: Extração

`OpenF1Client.get(endpoint, **params)` com timeout, intervalo entre chamadas e novas tentativas.

**Testes** (`httpx.MockTransport`): sucesso, 429 seguido de sucesso, 5xx persistente e consulta vazia.

### Fase 4: Transformação

Funções puras em `normalize.py` e `quality.py`. É a principal prioridade de testes.

**Testes:** conversão de tipos, datas, campos opcionais ausentes, coluna obrigatória ausente, coluna desconhecida, duplicatas, chave nula e lista vazia.

### Fase 5: Carga

`load/parquet.py` faz a escrita atômica. `load/duckdb.py` gera o SQL das views em uma função pura e o executa, com `read_parquet(..., union_by_name=true)`.

**Testes:** escrita, substituição e arquivo antigo preservado em caso de falha, com `tmp_path`. SQL gerado e execução com `duckdb.connect` mockado, pois a skill não permite banco em testes unitários. O DuckDB real é coberto na verificação final.

### Fase 6: Pipeline e CLI

```bash
poetry run f1-ingest --year 2024
poetry run f1-ingest --year 2023 --year 2024 --force
```

- `--year` é obrigatório, repetível e rejeita valores abaixo de 2023.
- Logs com `logging`, sem `print`.

**Testes** (cliente falso): sessão futura e cancelada ignoradas, partição existente ignorada, `--force`, falha parcial com código de saída 1 e validação de `--year`.

### Fase 7: Documentação

- `docs/index.md`: visão geral e como rodar.
- `docs/arquitetura.md`: módulos e fluxo.
- `docs/dados.md`: catálogo de tabelas, chaves, limitações herdadas da API e exemplos de consulta.
- `docs/api.md`: referência gerada pelo mkdocstrings.
- `README.md`: resumo em UTF-8 com link para a documentação.

## Verificação final

1. Checklist da skill:

   ```bash
   poetry run ruff check .
   poetry run ruff format --check .
   poetry run pytest
   poetry run mkdocs build --strict
   ```

2. Carga real da temporada de 2024 com `poetry run f1-ingest --year 2024`.
3. Idempotência: rodar de novo e confirmar que as contagens por tabela não mudam e que nenhuma partição é baixada novamente. Depois, rodar com `--force` e comparar as contagens.
4. Consulta no DuckDB, juntando `laps`, `drivers` e `sessions`: a melhor volta de cada piloto em uma corrida deve bater com uma fonte conhecida.

## Riscos

| Risco | Tratamento |
| --- | --- |
| Limites de requisição desconhecidos | Intervalo configurável, novas tentativas e retomada pela carga incremental |
| Formatos de campo diferentes do documentado | Amostra real na fase 2 e falha explícita por partição |
| Dados corrigidos depois da carga | Recarga com `--force` |
| Calendário atualizado só à meia-noite UTC | Sessões recentes podem aparecer apenas no dia seguinte |
| `overtakes` e `team_radio` com dados incompletos | Fora do escopo desta entrega |

## Pendências fora deste plano

- Limpeza dos pacotes instalados por engano no Python 3.15.0b1 global, com o comando já informado.
- Sobreposição entre as skills `python-project-setup` e `python-data-engineering-standards`. Este plano usa apenas a segunda.
- Fim de vida do MkDocs Material, previsto para 5 de maio de 2027.
