---
name: python-data-engineering-standards
description: Use ao criar, revisar, manter ou padronizar projetos Python de engenharia de dados do time, cobrindo Poetry, layout src, arquitetura modular, Ruff, pytest com cobertura mínima e MkDocs Material.
---

# Padrões de projetos Python de engenharia de dados

Nos exemplos, substitua:

- `projeto` pelo nome real do pacote.
- `3.13`, `>=3.13,<4.0` e `py313` pela versão de Python do projeto, mantendo os três coerentes.

## Como aplicar

- **Criar projeto:** siga [Setup de um projeto novo](#setup-de-um-projeto-novo).
- **Revisar ou manter:** compare o projeto com as [Regras](#regras) e [Nunca faça](#nunca-faça) e rode o [Checklist final](#checklist-final).
- **Padronizar projeto existente:**
  1. Migre as dependências de `requirements.txt` ou de outro gerenciador com `poetry add`.
  2. Mova o código para `src/projeto/` e os testes para `tests/`, ajustando os imports.
  3. Copie as configurações de [pyproject.toml](#pyprojecttoml-de-exemplo) e [mkdocs.yml](#mkdocsyml-de-exemplo).
  4. Remova flake8, black, isort e suas configurações.
  5. Rode o [Checklist final](#checklist-final) e corrija cada falha.

## Regras

### 1. Poetry para ambiente e pacotes

O Poetry é a única ferramenta para criar a venv e gerenciar pacotes. `pip install`, `pip freeze` e `requirements.txt` como fonte da verdade são proibidos.

Venv dentro do projeto, na pasta `.venv`:

```bash
poetry config virtualenvs.in-project true
```

Dependências de runtime e ferramentas em grupos separados:

```bash
poetry add <pacote>
poetry add --group dev ruff pytest pytest-cov pre-commit
poetry add --group docs mkdocs-material "mkdocstrings[python]"
```

- Versione sempre o `poetry.lock` no Git.
- Execute todos os comandos com `poetry run <comando>`.

### 2. Arquitetura src

- Código em `src/projeto/`, testes em `tests/` e documentação em `docs/`.
- `mkdocs.yml` e `pyproject.toml` na raiz.
- Pacote declarado no `pyproject.toml`:

```toml
[tool.poetry]
packages = [{ include = "projeto", from = "src" }]
```

Árvore de referência:

```text
projeto/
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── mkdocs.yml
├── poetry.lock
├── pyproject.toml
├── docs/
│   ├── api.md
│   ├── arquitetura.md
│   └── index.md
├── src/
│   └── projeto/
│       ├── __init__.py
│       ├── config/
│       ├── extract/
│       ├── load/
│       ├── pipelines/
│       ├── transform/
│       └── utils/
└── tests/
    ├── __init__.py
    ├── pipelines/
    └── transform/
```

### 3. Projeto modular

Separe as responsabilidades em subpacotes:

| Subpacote | Responsabilidade |
| --- | --- |
| `extract/` | Leitura de fontes |
| `transform/` | Regras de negócio |
| `load/` | Escrita em destinos |
| `config/` | Configurações e variáveis de ambiente |
| `utils/` | Funções genéricas reutilizáveis |
| `pipelines/` ou `jobs/` | Orquestração que combina os módulos |

- Escreva funções pequenas, com uma responsabilidade cada e sem efeitos colaterais quando possível. Transformações devem ser puras.
- Não coloque lógica de negócio em scripts soltos ou notebooks. Notebooks servem apenas para exploração e importam o pacote.
- Defina pontos de entrada em `[tool.poetry.scripts]` ou em `src/projeto/__main__.py` (executado com `poetry run python -m projeto`).
- Evite imports circulares e dependências desnecessárias entre módulos do mesmo nível. `extract/`, `transform/` e `load/` não importam uns aos outros; quem os combina é `pipelines/`.

### 4. Lint e formatação com Ruff

O Ruff é a única ferramenta de lint, formatação e ordenação de imports. Ele substitui flake8, black e isort. A configuração está no [pyproject.toml](#pyprojecttoml-de-exemplo).

O `ruff format` **não** ordena imports. A ordenação é feita pelo `ruff check --fix` com a regra `I`. Use esta sequência:

```bash
poetry run ruff check . --fix
poetry run ruff format .
```

Para validar sem alterar arquivos (CI):

```bash
poetry run ruff check .
poetry run ruff format --check .
```

### 5. Testes com pytest e cobertura mínima de 50%

- Use pytest e pytest-cov, com `tests/` espelhando `src/projeto/`: `src/projeto/transform/vendas.py` é testado em `tests/transform/test_vendas.py`.
- Mantenha um `__init__.py` em cada subpasta de `tests/`, para permitir arquivos de teste com o mesmo nome.
- A cobertura é medida sobre `src/projeto` e o pytest falha abaixo de 50% (`addopts` no [pyproject.toml](#pyprojecttoml-de-exemplo)).
- Testes unitários não acessam banco, rede, cloud ou arquivos reais. Use fixtures, `tmp_path`, mocks (`unittest.mock` ou `pytest-mock`) e DataFrames pequenos criados no teste.
- Priorize as funções de transformação, que concentram a regra de negócio.

```bash
poetry run pytest
```

### 6. Documentação com MkDocs Material

- Configure `theme: name: material` e o plugin `mkdocstrings` no [mkdocs.yml](#mkdocsyml-de-exemplo), que gera a referência da API a partir das docstrings.
- Páginas mínimas: `docs/index.md` (visão geral e como rodar), `docs/arquitetura.md` (arquitetura e módulos) e `docs/api.md` (referência da API).
- Escreva docstrings em todas as funções e classes públicas, em um único estilo (Google ou NumPy), igual ao `docstring_style` do `mkdocs.yml`.
- Anote os tipos dos parâmetros documentados. Sem a anotação, o mkdocstrings emite um aviso e o `--strict` falha.

```bash
poetry run mkdocs serve
poetry run mkdocs build --strict
```

### 7. Boas práticas de Python e de engenharia de dados

- Use type hints em todas as funções públicas e nomes conforme a PEP 8.
- Use `logging`, nunca `print`, com níveis adequados.
- Leia configurações e segredos de variáveis de ambiente ou de um `.env` não versionado. Nunca coloque credenciais no código. Mantenha um `.env.example` sem valores reais.
- Faça pipelines idempotentes: rodar de novo não pode duplicar nem corromper dados.
- Valide schema e qualidade dos dados nas fronteiras, na entrada e na saída.
- Trate exceções de forma explícita, sem `except:` genérico silencioso.
- Mantenha no `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `site/` e `.env`.
- Use `pre-commit`, instalado via Poetry, para rodar o Ruff antes de cada commit (etapa 8 do setup).

## Setup de um projeto novo

Execute nesta ordem. Os comandos funcionam em bash e em PowerShell.

### 1. Criar o projeto

```bash
poetry config virtualenvs.in-project true
poetry new --src projeto
cd projeto
```

No Poetry 2.x, `--src` já é o padrão e gera um aviso de depreciação. Quando a opção for removida, use `poetry new projeto`.

### 2. Criar o ambiente

Ajuste `requires-python` no `pyproject.toml`, pois o `poetry new` copia a versão do Python ativo:

```toml
requires-python = ">=3.13,<4.0"
```

```bash
poetry env use 3.13
poetry env info --path
poetry run python --version
```

`poetry env info --path` deve imprimir o caminho de `.venv` dentro do projeto. Se imprimir outro caminho, **não instale nada**: o Poetry instalaria os pacotes nesse outro ambiente. Resolva antes em [`.venv` criada fora do projeto](#venv-criada-fora-do-projeto).

### 3. Instalar as dependências

```bash
poetry add --group dev ruff pytest pytest-cov pre-commit
poetry add --group docs mkdocs-material "mkdocstrings[python]"
```

### 4. Criar a estrutura

```bash
poetry run python -c "from pathlib import Path; [(p := Path(d)).mkdir(parents=True, exist_ok=True) or (p / '__init__.py').touch() for d in ('src/projeto/extract', 'src/projeto/transform', 'src/projeto/load', 'src/projeto/config', 'src/projeto/utils', 'src/projeto/pipelines', 'tests/transform', 'tests/pipelines')]"
mkdir docs
```

### 5. Configurar

Complete o `pyproject.toml` conforme o [exemplo](#pyprojecttoml-de-exemplo), mantendo as versões que o `poetry add` gravou.

`.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.coverage
site/
.env
```

`.env.example`:

```dotenv
LOG_LEVEL=INFO
```

### 6. Escrever o primeiro código e os testes

`src/projeto/transform/vendas.py`:

```python
"""Regras de negócio de vendas."""


def calcular_total(quantidade: int, preco_unitario: float) -> float:
    """Calcula o valor total de um item.

    Args:
        quantidade: Quantidade vendida.
        preco_unitario: Preço de uma unidade.

    Returns:
        Valor total do item.

    Raises:
        ValueError: Se a quantidade for negativa.
    """
    if quantidade < 0:
        raise ValueError("quantidade não pode ser negativa")
    return quantidade * preco_unitario
```

`src/projeto/pipelines/vendas.py`:

```python
"""Pipeline de vendas."""

import logging
import os

from projeto.transform.vendas import calcular_total

logger = logging.getLogger(__name__)


def main() -> None:
    """Executa o pipeline de vendas."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    total = calcular_total(quantidade=2, preco_unitario=10.5)
    logger.info("Total calculado: %s", total)
```

`tests/transform/test_vendas.py`:

```python
import pytest

from projeto.transform.vendas import calcular_total


def test_calcular_total() -> None:
    assert calcular_total(quantidade=2, preco_unitario=10.5) == 21.0


def test_calcular_total_rejeita_quantidade_negativa() -> None:
    with pytest.raises(ValueError, match="negativa"):
        calcular_total(quantidade=-1, preco_unitario=10.5)
```

`tests/pipelines/test_vendas.py`:

```python
import logging

import pytest

from projeto.pipelines.vendas import main


def test_main_registra_total(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        main()

    assert "Total calculado: 21.0" in caplog.text
```

Instale o pacote na venv e rode os testes e o pipeline:

```bash
poetry install
poetry run pytest
poetry run projeto-vendas
```

### 7. Gerar a documentação

Crie o `mkdocs.yml` conforme o [exemplo](#mkdocsyml-de-exemplo).

`docs/index.md`:

````markdown
# Projeto

Descreva o objetivo do projeto, as fontes e os destinos de dados.

## Como rodar

```bash
poetry install
poetry run projeto-vendas
```
````

`docs/arquitetura.md`:

```markdown
# Arquitetura

- `extract/`: leitura de fontes.
- `transform/`: regras de negócio.
- `load/`: escrita em destinos.
- `config/`: configurações e variáveis de ambiente.
- `utils/`: funções genéricas reutilizáveis.
- `pipelines/`: orquestração que combina os módulos.
```

`docs/api.md`:

```markdown
# Referência da API

::: projeto.transform.vendas

::: projeto.pipelines.vendas
```

```bash
poetry run mkdocs build --strict
```

### 8. Ativar o pre-commit

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: poetry run ruff check --fix --force-exclude
        language: system
        types: [python]
      - id: ruff-format
        name: ruff format
        entry: poetry run ruff format --force-exclude
        language: system
        types: [python]
```

Os hooks locais usam a versão do Ruff fixada no `poetry.lock`.

```bash
git init
poetry run pre-commit install
```

Se um hook alterar arquivos, o commit é interrompido. Rode `git add` nos arquivos alterados e faça o commit de novo.

Por fim, rode o [Checklist final](#checklist-final).

## pyproject.toml de exemplo

```toml
[project]
name = "projeto"
version = "0.1.0"
description = "Pipelines de dados do projeto."
authors = [
    {name = "Time de Engenharia de Dados", email = "dados@example.com"}
]
readme = "README.md"
requires-python = ">=3.13,<4.0"
dependencies = []

[dependency-groups]
dev = [
    "ruff (>=0.17.4,<0.18.0)",
    "pytest (>=9.2.0,<10.0.0)",
    "pytest-cov (>=7.1.0,<8.0.0)",
    "pre-commit (>=4.7.0,<5.0.0)"
]
docs = [
    "mkdocs-material (>=9.8.0,<10.0.0)",
    "mkdocstrings[python] (>=1.0.8,<2.0.0)"
]

[tool.poetry]
packages = [{ include = "projeto", from = "src" }]

[tool.poetry.scripts]
projeto-vendas = "projeto.pipelines.vendas:main"

[tool.ruff]
target-version = "py313"
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "SIM"]

[tool.ruff.lint.isort]
known-first-party = ["projeto"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/projeto --cov-report=term-missing --cov-fail-under=50"

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"
```

No Poetry 2.x, `poetry check` emite um aviso de depreciação para `[tool.poetry.scripts]`. O aviso não impede a instalação nem a execução.

## mkdocs.yml de exemplo

```yaml
site_name: Projeto
theme:
  name: material
nav:
  - Início: index.md
  - Arquitetura: arquitetura.md
  - Referência da API: api.md
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
          options:
            docstring_style: google
```

## Checklist final

Todos os itens devem passar antes de qualquer entrega ou PR:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest
poetry run mkdocs build --strict
```

1. `poetry run ruff check .` sem erros.
2. `poetry run ruff format --check .` sem pendências.
3. `poetry run pytest` passando com cobertura ≥ 50% em `src/projeto`.
4. `poetry run mkdocs build --strict` sem erros.

## Nunca faça

- Usar pip: `pip install`, `pip freeze`, `python -m pip` ou `poetry run pip`.
- Usar `requirements.txt` como fonte da verdade.
- Instalar pacotes fora da venv do projeto.
- Commitar segredos, `.env` ou credenciais no código.
- Colocar lógica de negócio em notebooks ou scripts soltos.
- Ignorar a cobertura mínima: não reduza `--cov-fail-under`, não use `--no-cov`, não amplie exclusões de cobertura e não remova testes para passar.
- Usar outras ferramentas de lint ou formatação: flake8, black, isort, pylint ou autopep8.

## Solução de problemas

### Poetry usa a versão errada do Python

```bash
poetry env list
poetry env remove --all
poetry env use 3.13
poetry install
poetry run python --version
```

Se o Poetry não encontrar `3.13`, informe o caminho do executável: `poetry env use <caminho-do-python>`. A versão precisa atender ao `requires-python` do `pyproject.toml`.

### `ModuleNotFoundError` por causa do layout src

Confirme que o `pyproject.toml` declara `packages = [{ include = "projeto", from = "src" }]` e que `src/projeto/__init__.py` existe. Depois, instale o pacote, sem `--no-root`, e rode pelo Poetry:

```bash
poetry install
poetry run pytest
```

Não contorne o erro alterando `PYTHONPATH` ou `sys.path`.

### `.venv` criada fora do projeto

Uma venv ativa tem prioridade sobre `.venv`, mesmo com `virtualenvs.in-project` ligado. Verifique se `VIRTUAL_ENV` está definida e limpe a variável na sessão:

```bash
# bash
echo "$VIRTUAL_ENV"
unset VIRTUAL_ENV
```

```powershell
# PowerShell
$env:VIRTUAL_ENV
Remove-Item Env:VIRTUAL_ENV
```

Depois, recrie o ambiente e confirme o caminho:

```bash
poetry config virtualenvs.in-project true
poetry env remove --all
poetry env use 3.13
poetry env info --path
poetry install
```

### Imports não reordenados após o `ruff format`

É o comportamento esperado: o `ruff format` não ordena imports. Confirme que `I` está em `select` e rode na ordem correta:

```bash
poetry run ruff check . --fix
poetry run ruff format .
```
