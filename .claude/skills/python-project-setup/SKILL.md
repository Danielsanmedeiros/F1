---
name: python-project-setup
description: Use ao criar, configurar ou padronizar um projeto Python com Poetry, pyenv, Ruff, pytest e MkDocs Material.
---

# Padrão de projeto Python

Nos exemplos, substitua:

- `projeto` pelo nome real do pacote.
- `3.13.13`, `>=3.13,<4.0` e `py313` pela versão de Python do projeto, mantendo os três coerentes. Use uma versão estável, não alfa, beta ou rc.

Os comandos funcionam em bash e em PowerShell.

## Pré-requisitos

pyenv e Poetry são as únicas ferramentas fora da venv. Verifique se estão disponíveis:

```bash
pyenv --version
poetry --version
```

Se algum faltar, peça ao usuário para instalá-lo. Não instale com `pip`.

## Setup do zero

Execute na raiz do projeto, nesta ordem.

### 1. Python com pyenv

```bash
pyenv install 3.13.13
pyenv local 3.13.13
```

Isso gera `.python-version` na raiz.

### 2. Poetry com venv no projeto

```bash
poetry init --no-interaction --name projeto --python ">=3.13,<4.0"
poetry config virtualenvs.in-project true --local
poetry env use $(pyenv which python)
poetry env info --path
```

- `--local` grava a configuração em `poetry.toml`, que vai para o Git e vale em qualquer máquina.
- O último comando deve imprimir o caminho de `.venv` dentro do projeto. Se imprimir outro caminho, pare e resolva em [Solução de problemas](#solução-de-problemas) antes de instalar qualquer coisa.

### 3. Dependências

```bash
poetry add --group dev ruff pytest pytest-cov
poetry add --group docs mkdocs-material
```

Dependências de runtime: `poetry add <pacote>`.

### 4. Estrutura de pastas

```bash
mkdir src
mkdir src/projeto
mkdir tests
mkdir docs
```

Estrutura final:

```text
.
├── .gitignore
├── .python-version
├── mkdocs.yml
├── poetry.lock
├── poetry.toml
├── pyproject.toml
├── docs/
│   └── index.md
├── src/
│   └── projeto/
│       ├── __init__.py
│       └── core.py
└── tests/
    └── test_core.py
```

Crie `.gitignore`:

```gitignore
.venv/
__pycache__/
.coverage
.pytest_cache/
.ruff_cache/
site/
```

Versione `poetry.lock`, `poetry.toml` e `.python-version`.

### 5. Configurações

Acrescente ao `pyproject.toml` as seções `[tool.poetry]`, `[tool.ruff]`, `[tool.ruff.lint]` e `[tool.pytest.ini_options]`, conforme o modelo abaixo. Mantenha as versões que o `poetry add` gravou em `[dependency-groups]`.

```toml
[project]
name = "projeto"
version = "0.1.0"
description = "Descrição curta do projeto."
authors = [
    {name = "Nome do Autor", email = "autor@example.com"}
]
requires-python = ">=3.13,<4.0"
dependencies = []

[dependency-groups]
dev = [
    "ruff (>=0.17.4,<0.18.0)",
    "pytest (>=9.2.0,<10.0.0)",
    "pytest-cov (>=7.1.0,<8.0.0)"
]
docs = [
    "mkdocs-material (>=9.8.0,<10.0.0)"
]

[tool.poetry]
packages = [{include = "projeto", from = "src"}]

[tool.ruff]
target-version = "py313"
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/projeto --cov-report=term-missing --cov-fail-under=50"

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"
```

Ruff é o único linter e formatador:

```bash
poetry run ruff check .
poetry run ruff check . --fix
poetry run ruff format .
```

### 6. Primeiro teste

`src/projeto/__init__.py`:

```python
"""Pacote projeto."""
```

`src/projeto/core.py`:

```python
"""Funções principais do projeto."""


def somar(a: int, b: int) -> int:
    """Retorna a soma de dois inteiros."""
    return a + b
```

`tests/test_core.py`:

```python
from projeto.core import somar


def test_somar() -> None:
    assert somar(2, 3) == 5
```

Instale o pacote na venv e rode os testes. O `poetry install` é necessário porque o `poetry add` da etapa 3 rodou antes de o pacote existir.

```bash
poetry install
poetry run pytest
```

### 7. Documentação

`mkdocs.yml`:

```yaml
site_name: Projeto
theme:
  name: material
nav:
  - Início: index.md
```

`docs/index.md`:

```markdown
# Projeto

Descrição curta do projeto.
```

```bash
poetry run mkdocs serve
poetry run mkdocs build
```

#### Opcional: referência da API a partir das docstrings

```bash
poetry add --group docs "mkdocstrings[python]"
```

Crie `docs/api.md`:

```markdown
# Referência da API

::: projeto.core
```

Use este `mkdocs.yml`:

```yaml
site_name: Projeto
theme:
  name: material
nav:
  - Início: index.md
  - API: api.md
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
```

## Manutenção

```bash
poetry add <pacote>
poetry add --group dev <pacote>
poetry remove <pacote>
poetry update
poetry install
```

Rode `poetry install` depois de clonar o projeto ou de atualizar `poetry.lock`. Ao mudar a versão do Python, atualize `.python-version`, `requires-python` e `target-version`, depois rode `poetry env use $(pyenv which python)` e `poetry install`.

## Padronizar um projeto existente

1. Aplique as etapas 1 a 3, usando `poetry add` para migrar cada dependência de `requirements.txt` ou de outro gerenciador.
2. Mova o código para `src/projeto/` e os testes para `tests/`, ajustando os imports.
3. Aplique as etapas 5 e 7.
4. Remova as configurações e dependências de flake8, isort e black.
5. Rode `poetry run ruff check . --fix` e `poetry run ruff format .`.
6. Se a cobertura ficar abaixo de 50%, escreva os testes que faltam.

## Checklist de verificação final

Rode antes de dar o trabalho como concluído. Todos os comandos devem terminar com sucesso:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run pytest
poetry run mkdocs build
```

1. `poetry run ruff check .` sem erros.
2. `poetry run ruff format --check .` sem alterações pendentes.
3. `poetry run pytest` passando com cobertura ≥ 50% em `src/projeto`.
4. `poetry run mkdocs build` sem erros.

## Regras

NUNCA:

- Instalar pacotes ou ferramentas do projeto fora da venv.
- Usar `pip` diretamente (`pip install`, `python -m pip`, `poetry run pip`). Use `poetry add`.
- Ignorar a cobertura mínima: não reduza `--cov-fail-under`, não use `--no-cov`, não amplie exclusões de cobertura e não remova testes para passar.
- Misturar outras ferramentas de lint ou formatação (flake8, isort, black, pylint, autopep8).
- Executar ferramentas do projeto sem `poetry run`.
- Versionar `.venv/` ou editar `poetry.lock` à mão.

## Solução de problemas

### Poetry usa a versão errada do Python

```bash
pyenv local 3.13.13
poetry env remove --all
poetry env use $(pyenv which python)
poetry install
poetry run python --version
```

### `.venv` não é criada no projeto

Primeiro, verifique se há uma venv ativa, pois o Poetry a usa no lugar de `.venv`. Se `VIRTUAL_ENV` estiver definida, limpe a variável na sessão:

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

Depois, recrie o ambiente:

```bash
poetry config virtualenvs.in-project true --local
poetry env remove --all
poetry env use $(pyenv which python)
poetry install
poetry env info --path
```

### `ModuleNotFoundError: No module named 'projeto'`

Confirme que `pyproject.toml` declara `packages = [{include = "projeto", from = "src"}]` e que `src/projeto/__init__.py` existe. Depois, instale o pacote e rode os testes pelo Poetry:

```bash
poetry install
poetry run pytest
```

Não contorne o erro alterando `PYTHONPATH` nem `sys.path`.

### `poetry` encerra sem mensagem de erro

Verifique em qual Python o próprio Poetry roda, na seção `Poetry` da saída:

```bash
poetry debug info
```

Se for uma versão alfa, beta ou rc, peça ao usuário para reinstalar o Poetry sobre uma versão estável. Isso altera uma ferramenta global, então não faça sem autorização.
