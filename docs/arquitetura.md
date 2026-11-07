# Arquitetura

## Módulos

| Módulo | Responsabilidade |
| --- | --- |
| `config/settings.py` | Configurações lidas do ambiente |
| `extract/client.py` | Cliente REST da OpenF1, com intervalo entre chamadas e novas tentativas |
| `transform/schemas.py` | Colunas, tipos e chaves de cada endpoint |
| `transform/normalize.py` | Conversão dos registros da API em DataFrames tipados e seleção de sessões |
| `transform/quality.py` | Validações antes da gravação |
| `load/parquet.py` | Escrita atômica por partição |
| `load/duckdb.py` | Views sobre os arquivos Parquet |
| `pipelines/ingest.py` | Orquestração e linha de comando `f1-ingest` |
| `extract/warehouse.py` | Leitura das views do DuckDB em conexões somente leitura |
| `transform/race_views.py` | Regras que preparam uma sessão para visualização, como fotos, resultados e posições por volta |
| `dashboard.py` | Página do Streamlit, com seletores e gráficos |

`extract/`, `transform/` e `load/` não importam uns aos outros. Quem os combina são `pipelines/` e `dashboard.py`.

## Fluxo

1. Buscar `meetings` e `sessions` por `year`. Essas tabelas são sempre atualizadas, pois definem o calendário e mudam durante a temporada.
2. Selecionar as sessões encerradas (`date_end` no passado) e não canceladas (`is_cancelled`).
3. Para cada sessão, buscar os demais endpoints por `session_key`, ignorando as partições existentes.
4. Normalizar, validar e gravar cada partição.
5. Recriar as views no DuckDB.

## Regras do pipeline

- **Idempotência:** cada partição é gravada em um arquivo temporário e substituída com `os.replace`. Repetir a carga troca o arquivo, sem duplicar linhas. Se a gravação falhar, a versão anterior é preservada.
- **Carga incremental:** partições de sessão existentes são ignoradas, e `--force` as recarrega. Resultado vazio grava um Parquet vazio com o schema, para não repetir a requisição.
- **Reprodutibilidade:** o pipeline nunca usa `session_key=latest` nem `meeting_key=latest`.

### Tratamento de falhas

| Situação | Comportamento |
| --- | --- |
| HTTP 429, 5xx ou erro de rede | Novas tentativas com espera crescente, respeitando `Retry-After` |
| Falha persistente, schema inválido ou chave com nulos ou duplicatas | Registra a falha, segue com as demais partições e encerra com código 1 |
| HTTP 401 ou 403, como no bloqueio por sessão ao vivo | Interrompe a carga e encerra com código 1, pois as demais chamadas também falhariam |

Em todos os casos, repetir o comando retoma de onde parou.
