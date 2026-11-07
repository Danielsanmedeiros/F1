# F1

Coleta dados históricos da [API OpenF1](https://openf1.org/docs/) (2023 em diante) e os disponibiliza para análise de corrida em arquivos Parquet locais, consultáveis no DuckDB.

## Como rodar

```bash
poetry install
poetry run f1-ingest --year 2024
```

Para carregar mais de uma temporada ou recarregar o que já existe:

```bash
poetry run f1-ingest --year 2023 --year 2024 --force
```

| Opção | Descrição |
| --- | --- |
| `--year` | Temporada a carregar, a partir de 2023. Obrigatória e repetível. |
| `--force` | Recarrega as partições existentes. |

O comando encerra com código 0 em caso de sucesso, 1 se alguma partição falhar ou se a carga for interrompida, e 2 se os argumentos forem inválidos. Repetir o comando retoma de onde parou, sem duplicar dados.

**Bloqueio durante sessões ao vivo:** enquanto acontece uma sessão de Fórmula 1, a OpenF1 recusa todo acesso sem autenticação, inclusive ao histórico (HTTP 401). A carga é interrompida com código 1 e deve ser repetida depois que a sessão terminar.

**Duração:** a carga da temporada de 2024 fez 1.109 requisições em 37 minutos, sem erro de limite, e ocupa cerca de 10 MB. Repetir o comando leva segundos, pois só o calendário é baixado de novo.

## Configuração

As variáveis são lidas do ambiente ou de um arquivo `.env` (veja `.env.example`).

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `OPENF1_BASE_URL` | `https://api.openf1.org/v1` | URL base da API |
| `OPENF1_REQUEST_INTERVAL_SECONDS` | `2.0` | Intervalo mínimo entre chamadas, em segundos |
| `F1_DATA_DIR` | `data` | Pasta dos arquivos Parquet e do banco DuckDB |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `F1_DATA_SNAPSHOT_URL` | sem valor | Endereço do snapshot que o dashboard baixa quando o banco não existe |

## Dashboard

```bash
poetry run task dashboard
```

Rode a partir da raiz do projeto, depois de carregar ao menos uma temporada. O dashboard abre no navegador, em `http://localhost:8501`, e mostra para a sessão escolhida:

- pódio e classificação, com a foto de cada piloto;
- ritmo por volta e evolução das posições dos pilotos em destaque (até 4);
- estratégia de pneus de todos os pilotos.

**Fotos:** vêm do campo `headshot_url` e são carregadas do site da Fórmula 1 pelo navegador, sem ficar salvas nos dados. Por isso:

- É preciso ter internet para vê-las.
- O endereço é fixo, mas a imagem é a atual do site. Um piloto pode aparecer com o uniforme de outra equipe em temporadas passadas.
- Pilotos sem foto na API aparecem com a sigla sobre a cor da equipe. Em 2024, isso vale para 16 dos 35 números de piloto, como Colapinto e Lawson.

**Cores:** as cores das equipes são as informadas pela API e só têm contraste suficiente no fundo escuro, então o tema escuro é o padrão (`.streamlit/config.toml`). Algumas são parecidas, como as de RB e Williams. Por isso, os gráficos também identificam os pilotos com rótulo ou foto, tracejado para o segundo piloto da equipe e tabela de dados.

**Dados online:** os dados não ficam no repositório. Em um ambiente sem dados, defina `F1_DATA_SNAPSHOT_URL` com o endereço de um snapshot, gerado com `poetry run f1-snapshot` em `dist/f1-data.zip`. Na primeira execução, o dashboard baixa o arquivo e cria as views. Para atualizar os dados publicados, gere e publique o snapshot de novo e reinicie o app.

## Como consultar

As views ficam em `data/f1.duckdb`, e a seção [Dados](dados.md) traz exemplos de consulta.

```bash
poetry run python -c "import duckdb; print(duckdb.connect('data/f1.duckdb', read_only=True).sql('SELECT year, count(*) FROM sessions GROUP BY year'))"
```

## Desenvolvimento

| Comando | O que faz |
| --- | --- |
| `poetry run task test` | Roda os testes com cobertura (`pytest`) |
| `poetry run task lint` | Valida lint e formatação, sem alterar arquivos (`ruff check .` e `ruff format --check .`) |
| `poetry run task format` | Corrige o lint, ordena os imports e formata (`ruff check . --fix --exit-zero` e `ruff format .`). Erros sem correção automática são exibidos, mas não impedem a formatação |
| `poetry run task docs` | Gera a documentação e falha em caso de aviso (`mkdocs build --strict`) |
| `poetry run task dashboard` | Abre o dashboard (`streamlit run src/f1/dashboard.py`) |

Antes de uma entrega, rode `task lint`, `task test` e `task docs`.
