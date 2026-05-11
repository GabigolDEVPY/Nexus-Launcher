# NexusLauncher

Launcher de jogos para Windows com biblioteca local, rastreamento de horas e sincronizacao de saves e dados do usuario com GitHub.

## O que o launcher faz

- Organiza seus jogos em uma biblioteca local.
- Permite adicionar capa, descricao e outros metadados automaticamente.
- Monitora tempo de jogo.
- Sincroniza saves com GitHub.
- Sincroniza tambem os dados do launcher, como jogos adicionados, horas jogadas e configuracoes.

## Onde os dados ficam salvos

O launcher salva os dados do usuario em:

`Documentos\NexusLauncher`

Ali ficam:

- banco local
- configuracoes
- cache
- logs

## Como usar

### 1. Abrir o launcher

Abra o `NexusLauncher.exe` instalado normalmente pelo setup.

### 2. Adicionar um jogo

1. Clique em `+ Adicionar`.
2. Selecione o executavel do jogo.
3. Ajuste o nome se quiser.
4. Se souber onde o jogo salva o progresso, informe a pasta de save.
5. Confirme.

### 3. Configurar sincronizacao com GitHub

1. Clique em `Config`.
2. Preencha o token do GitHub.
3. Preencha a URL do repositorio.
4. Ative `GitHub Sync`.
5. Salve.

Exemplo de URL:

`https://github.com/seu-usuario/seu-repo.git`

## Configurar um jogo depois de adicionar

Selecione o jogo e use o botao `CONFIG`.

Ali voce pode:

- mudar o nome do jogo
- trocar o executavel
- mudar a pasta de save
- ativar ou desativar o sync daquele jogo
- usar `Salvar e Sincronizar Agora`

Se voce mudar o nome do jogo, o launcher tenta atualizar tambem os metadados dele.

## Como o sync funciona

- Ao abrir o launcher, ele tenta sincronizar os dados do usuario.
- Os dados do launcher tambem sao sincronizados periodicamente.
- Se existir save no GitHub e nao existir save local, o launcher restaura o save para a maquina.
- Se local e GitHub tiverem saves diferentes na primeira sincronizacao, o launcher pergunta antes de sobrescrever.
- Depois que aquela maquina ja estiver sincronizada, os saves locais podem ser enviados normalmente.

## Mudou a pasta de save do jogo?

Se voce reinstalou o jogo, mudou de plataforma, ou o jogo passou a usar outra pasta de save:

1. Abra o `CONFIG` do jogo.
2. Salve o novo caminho da pasta de save.
3. Abra o jogo uma vez para ele criar a estrutura nova.
4. Feche o jogo.
5. O launcher aplica o save do GitHub nessa nova pasta.

## Restaurar tudo depois de formatar o PC

Se o repositorio do GitHub ja estiver configurado e sincronizado:

1. Instale o launcher.
2. Abra o launcher.
3. Configure o token e a URL do repositorio.
4. O launcher puxa os dados do GitHub e reconstrui a biblioteca local.

## Dicas importantes

- Use um repositorio privado no GitHub.
- Guarde seu token com cuidado.
- Se voce trocar o token, atualize no launcher.
- Se o save local sumir, o launcher pode restaurar do GitHub se ele ja tiver sido sincronizado antes.

## Problemas comuns

### O jogo nao sincronizou

Confira:

- se o token do GitHub esta correto
- se a URL do repositorio esta correta
- se a pasta de save do jogo esta configurada
- se o sync global esta ativo

### O jogo cria save em outra pasta

Atualize a pasta no `CONFIG` do jogo e abra o jogo uma vez para ele criar a estrutura nova.

## Observacao

O launcher usa Git no processo de sincronizacao. No build de producao, ele pode sair com `PortableGit` embutido no instalador, sem depender de Git instalado manualmente no Windows.
