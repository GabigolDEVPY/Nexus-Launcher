"""
Dialogo de configuracoes do NexusLauncher.
"""
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """Configuracoes globais: GitHub, APIs e comportamento da aplicacao."""

    def __init__(self, settings, sync_manager, startup_service, tray_supported, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.sync_manager = sync_manager
        self.startup_service = startup_service
        self.tray_supported = tray_supported

        self.setWindowTitle("Configuracoes")
        self.setMinimumSize(680, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        tabs = QTabWidget()
        tabs.addTab(self._build_github_tab(), "GitHub Sync")
        tabs.addTab(self._build_api_tab(), "APIs")
        tabs.addTab(self._build_general_tab(), "Geral")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Salvar")
        save_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e8c547; color: #0d0d0d;
                font-weight: bold; padding: 10px 30px;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #f0d060; }
            """
        )
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _build_github_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("CONFIGURACAO DO GITHUB")
        form = QFormLayout(group)

        self._repo_url = QLineEdit(self.settings.get("github_repo_url", ""))
        self._repo_url.setPlaceholderText(
            "https://github.com/usuario/saves-repo.git ou usuario/saves-repo"
        )
        form.addRow("URL do Repositorio:", self._repo_url)

        self._repo_name = QLineEdit(self.settings.get("github_repo_name", ""))
        self._repo_name.setPlaceholderText("Opcional: nome da pasta local")
        form.addRow("Pasta Local:", self._repo_name)

        self._token = QLineEdit(self.settings.get("github_token", ""))
        self._token.setPlaceholderText("ghp_xxxxxxxxxxxx")
        self._token.setEchoMode(QLineEdit.Password)
        form.addRow("Token GitHub:", self._token)

        self._sync_enabled = QCheckBox("Ativar sincronizacao automatica")
        self._sync_enabled.setChecked(self.settings.get("save_sync_enabled", False))
        form.addRow("", self._sync_enabled)

        layout.addWidget(group)

        help_label = QLabel(
            "Se a pasta local ficar vazia, o launcher usa automaticamente o nome do repositorio."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #9aa4b2; font-size: 12px;")
        layout.addWidget(help_label)

        test_btn = QPushButton("Testar Conexao")
        test_btn.clicked.connect(self._test_connection)
        layout.addWidget(test_btn)
        layout.addStretch()
        return widget

    def _build_api_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("APIS EXTERNAS")
        form = QFormLayout(group)

        self._rawg_key = QLineEdit(self.settings.get("rawg_api_key", ""))
        self._rawg_key.setPlaceholderText("Chave da RAWG API")
        form.addRow("RAWG API Key:", self._rawg_key)

        self._sgdb_key = QLineEdit(self.settings.get("steamgriddb_api_key", ""))
        self._sgdb_key.setPlaceholderText("Chave da SteamGridDB API")
        form.addRow("SteamGridDB API Key:", self._sgdb_key)

        self._auto_fetch = QCheckBox("Buscar metadados automaticamente")
        self._auto_fetch.setChecked(self.settings.get("auto_fetch_metadata", True))
        form.addRow("", self._auto_fetch)

        help_label = QLabel(
            "Sem chaves, o launcher ainda tenta buscar informacoes pelo catalogo publico da Steam."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #9aa4b2; font-size: 12px;")

        layout.addWidget(group)
        layout.addWidget(help_label)
        layout.addStretch()
        return widget

    def _build_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("COMPORTAMENTO DO APP")
        form = QFormLayout(group)

        self._minimize_tray = QCheckBox("Fechar para a bandeja do sistema")
        self._minimize_tray.setChecked(self.settings.get("minimize_to_tray", False))
        self._minimize_tray.setEnabled(self.tray_supported)
        form.addRow("", self._minimize_tray)

        self._start_with_windows = QCheckBox("Iniciar com o Windows")
        startup_enabled = self.settings.get("start_with_windows", False)
        if self.startup_service.supported:
            startup_enabled = self.startup_service.is_enabled()
        self._start_with_windows.setChecked(startup_enabled)
        self._start_with_windows.setEnabled(self.startup_service.supported)
        form.addRow("", self._start_with_windows)

        if not self.tray_supported:
            tray_note = QLabel("A bandeja do sistema nao esta disponivel neste ambiente.")
            tray_note.setWordWrap(True)
            tray_note.setStyleSheet("color: #facc15; font-size: 12px;")
            form.addRow("", tray_note)

        if not self.startup_service.supported:
            startup_note = QLabel("Iniciar com o Windows so esta disponivel no Windows.")
            startup_note.setWordWrap(True)
            startup_note.setStyleSheet("color: #facc15; font-size: 12px;")
            form.addRow("", startup_note)

        live_note = QLabel(
            "As horas jogadas sao acompanhadas em tempo real enquanto o launcher estiver em execucao."
        )
        live_note.setWordWrap(True)
        live_note.setStyleSheet("color: #9aa4b2; font-size: 12px;")
        form.addRow("", live_note)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _test_connection(self):
        url = self._repo_url.text().strip()
        token = self._token.text().strip()
        if not url or not token:
            QMessageBox.warning(self, "Erro", "Preencha a URL e o token.")
            return

        QMessageBox.information(
            self,
            "Teste",
            "A conexao sera testada ao salvar. Verifique as configuracoes.",
        )

    def _save(self):
        try:
            self.startup_service.set_enabled(self._start_with_windows.isChecked())
        except Exception as e:
            QMessageBox.warning(
                self,
                "Startup do Windows",
                f"Nao foi possivel atualizar a inicializacao com o Windows:\n{e}",
            )
            return

        self.settings.set("github_repo_url", self._repo_url.text().strip())
        self.settings.set("github_repo_name", self._repo_name.text().strip())
        self.settings.set("github_token", self._token.text().strip())
        self.settings.set("save_sync_enabled", self._sync_enabled.isChecked())
        self.settings.set("rawg_api_key", self._rawg_key.text().strip())
        self.settings.set("steamgriddb_api_key", self._sgdb_key.text().strip())
        self.settings.set("auto_fetch_metadata", self._auto_fetch.isChecked())
        self.settings.set("minimize_to_tray", self._minimize_tray.isChecked())
        self.settings.set("start_with_windows", self._start_with_windows.isChecked())

        if self._sync_enabled.isChecked():
            self.sync_manager.initialize()

        self.accept()
