# NexusLauncher

Game launcher portatil para Windows com biblioteca local, rastreamento de horas e sincronizacao de saves e dados do usuario com o GitHub.

## Como funciona

- **Portatil e onefile**: o build gera um unico `NexusLauncher.exe`. Nao ha instalador: basta copiar o exe e executar.
- **Zero dependencias externas**: nao precisa de Git, Python ou qualquer outra coisa instalada. A sincronizacao usa a API oficial do GitHub por HTTPS, direto de dentro do app.
- **Instancia unica**: abrir o exe de novo nao cria uma segunda copia; a janela ja aberta e trazida para frente.
- **Fica em segundo plano**: ao fechar, o launcher continua na bandeja do sistema (indice ao lado do relogio). Para sair de verdade, use o menu da bandeja.

## Onde os dados ficam salvos

Os dados do usuario ficam em `Documentos\NexusLauncher`:

- banco local (`nexus.db`)
- configuracoes (`config.json`)
- cache de imagens, saves e logs

## Como usar

### 1. Abrir o launcher

Execute o `NexusLauncher.exe`. Nao precisa instalar nada.

### 2. Adicionar um jogo

1. Clique em `+ Adicionar`.
2. Selecione o executavel do jogo.
3. Se souber onde o jogo salva o progresso, informe a pasta de save.
4. Confirme.

### 3. Configurar sincronizacao com GitHub

1. Clique em `Config`.
2. Preencha o token do GitHub (precisa de permissao de escrita no repositorio).
3. Preencha a URL do repositorio, por exemplo `https://github.com/seu-usuario/seu-repo.git`.
4. Ative `Ativar sincronizacao de saves`.
5. Salve.

Use um repositorio **privado** e guarde o token com cuidado.

### 4. Sincronizar

O launcher envia os dados para o GitHub de duas formas:

- **Automatico, no maximo 1x por dia** (estado do launcher: jogos, horas jogadas e configuracoes).
- **Botao `Sync` no topo**, quando voce quiser sincronizar agora: envia o estado do launcher e os saves de todos os jogos com sync ativado.

Tambem e possivel sincronizar um jogo especifico pelo `CONFIG` do jogo (`Salvar e Sincronizar Agora`).

Mudancas nos arquivos de save **nao** disparam sync sozinhas; o sync acontece no ritmo descrito acima.

## Restaurar depois de formatar o PC

1. Execute o launcher novo.
2. Configure o mesmo token e a mesma URL do repositorio.
3. O launcher puxa do GitHub e reconstrui a biblioteca, as horas e as configuracoes.
4. Se existir save no GitHub e nao existir no PC, ele e restaurado automaticamente.

## Sobre conflitos de save

Se o save local e o do GitHub estiverem diferentes, o launcher pergunta antes de sobrescrever (enviar o local ou baixar o remoto). No botao `Sync` global, jogos em conflito sao ignorados e informados, para nao sobrescrever nada sem voce ver.

## Desenvolvimento

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

### Build do exe portatil

```powershell
.venv\Scripts\pip install -r requirements-build.txt
powershell -File build_release.ps1
```

O resultado fica em `dist\NexusLauncher.exe`.
