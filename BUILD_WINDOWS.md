# Build Windows

O launcher agora salva dados do usuario em:

`%USERPROFILE%\Documents\NexusLauncher`

Arquivos principais:

- `NexusLauncher.spec`: build `PyInstaller` em modo pasta (`onedir`)
- `build_release.ps1`: gera a pasta `dist\NexusLauncher` e tenta compilar o instalador
- `installer\NexusLauncher.iss`: script do Inno Setup
- `vendor\PortableGit`: Git embutido opcional para nao depender do Git do sistema

## Pre-requisitos

- Python com a `.venv` do projeto ativa ou funcional
- Dependencias do projeto instaladas
- `PyInstaller`
- Inno Setup 6 para gerar o `setup.exe`

## Comandos

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build_release.ps1
```

## Build sem depender de Git instalado

Antes do build, extraia o `PortableGit` para:

`vendor\PortableGit`

O launcher vai procurar automaticamente por:

- `vendor\PortableGit\cmd\git.exe`
- `vendor\PortableGit\bin\git.exe`

Se essa pasta existir, o `setup.exe` sai com Git embutido.

## Saida

- App em pasta: `dist\NexusLauncher\NexusLauncher.exe`
- Instalador: `dist-installer\NexusLauncher-Setup-<versao>.exe`

## Observacoes

- O instalador e per-user e instala em `{localappdata}\Programs\NexusLauncher`.
- Banco, config, cache e logs ficam fora da pasta do programa.
- Se existir `config.json` ou `nexus.db` antigo ao lado do projeto, o app copia esses arquivos para `Documentos\NexusLauncher` no primeiro boot.
- Se `vendor\PortableGit` nao existir no momento do build, o app continua funcionando, mas vai depender do Git instalado na maquina do usuario.
