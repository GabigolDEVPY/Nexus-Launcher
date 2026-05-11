# PortableGit

Para gerar um instalador sem depender do Git instalado no Windows do usuario:

1. Baixe o `PortableGit` do projeto Git for Windows.
2. Extraia a pasta para:

`vendor/PortableGit`

3. Confirme que um destes arquivos exista:

- `vendor/PortableGit/cmd/git.exe`
- `vendor/PortableGit/bin/git.exe`

Quando essa pasta existir, o build do `PyInstaller` vai embutir o Git no launcher e o `SyncManager` vai priorizar esse executavel automaticamente.
