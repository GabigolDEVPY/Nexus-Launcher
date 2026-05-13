"""
Dialogo para adicionar um novo jogo a biblioteca.
Busca metadados automaticamente e permite edicao manual.
"""

import os

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from utils.helpers import extract_game_name_from_path, sanitize_filename
from utils.logger import get_logger

logger = get_logger("AddGameDialog")


class _MetadataSearchThread(QThread):
    results_ready = Signal(list)
    error = Signal(str)

    def __init__(self, metadata_service, query: str):
        super().__init__()
        self.metadata_service = metadata_service
        self.query = query

    def run(self):
        try:
            self.results_ready.emit(self.metadata_service.search_game(self.query))
        except Exception as e:
            logger.exception("Falha na busca de metadados")
            self.error.emit(str(e))


class _MetadataDetailsThread(QThread):
    details_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, metadata_service, image_service, selection: dict):
        super().__init__()
        self.metadata_service = metadata_service
        self.image_service = image_service
        self.selection = dict(selection)

    def run(self):
        try:
            payload = dict(self.selection)
            details = self.metadata_service.get_game_details(
                rawg_id=payload.get("rawg_id"),
                steam_appid=payload.get("steam_appid"),
            )
            if details:
                payload.update(details)

            name = payload.get("name") or self.selection.get("name") or "game"
            cache_key = sanitize_filename(
                f"{name}_{payload.get('rawg_id') or payload.get('steam_appid') or 'local'}".lower()
            )

            extra_images = self.metadata_service.get_images(name)
            banner_url = (
                extra_images.get("hero")
                or extra_images.get("banner")
                or payload.get("background_url", "")
            )
            cover_url = (
                extra_images.get("cover")
                or payload.get("cover_url", "")
                or payload.get("background_url", "")
            )

            payload["banner_path"] = ""
            payload["cover_path"] = ""

            if banner_url:
                payload["banner_path"] = (
                    self.image_service.get_or_download(
                        f"banner_{cache_key}", banner_url
                    )
                    or ""
                )
            if cover_url:
                payload["cover_path"] = (
                    self.image_service.get_or_download(
                        f"cover_{cache_key}",
                        cover_url,
                    )
                    or ""
                )

            self.details_ready.emit(payload)
        except Exception as e:
            logger.exception("Falha ao obter detalhes do jogo")
            self.error.emit(str(e))


class AddGameDialog(QDialog):
    """Dialogo completo para adicionar um jogo."""

    def __init__(self, metadata_service, image_service, parent=None):
        super().__init__(parent)
        self.metadata_service = metadata_service
        self.image_service = image_service
        self.result_data = None

        self._search_thread = None
        self._details_thread = None
        self._search_results = []
        self._selected_metadata = {}
        self._cover_path = ""
        self._banner_path = ""

        self.setWindowTitle("Adicionar Jogo")
        self.setMinimumSize(720, 640)
        self.setStyleSheet(
            """
            QDialog { background-color: #0d0d0d; }
            QGroupBox {
                border: 1px solid #2a2a2a; border-radius: 8px;
                margin-top: 12px; padding-top: 20px;
                color: #1EA1FF; font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; padding: 0 10px; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        exe_group = QGroupBox("EXECUTAVEL")
        exe_layout = QHBoxLayout(exe_group)
        self._exe_input = QLineEdit()
        self._exe_input.setPlaceholderText("Caminho para o .exe do jogo...")
        exe_layout.addWidget(self._exe_input)

        browse_btn = QPushButton("Procurar...")
        browse_btn.clicked.connect(self._browse_exe)
        exe_layout.addWidget(browse_btn)
        layout.addWidget(exe_group)

        search_group = QGroupBox("BUSCAR METADADOS")
        search_layout = QVBoxLayout(search_group)

        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Digite o nome do jogo para buscar...")
        self._search_input.returnPressed.connect(self._search_game)
        search_row.addWidget(self._search_input)

        self._search_btn = QPushButton("Buscar")
        self._search_btn.clicked.connect(self._search_game)
        search_row.addWidget(self._search_btn)
        search_layout.addLayout(search_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #9aa4b2; font-size: 12px;")
        search_layout.addWidget(self._status_label)

        self._results_list = QListWidget()
        self._results_list.setMaximumHeight(140)
        self._results_list.itemClicked.connect(self._select_search_result)
        self._results_list.itemDoubleClicked.connect(self._select_search_result)
        search_layout.addWidget(self._results_list)

        self._result_hint = QLabel(
            "Clique em um resultado para preencher nome, descricao e imagens automaticamente."
        )
        self._result_hint.setWordWrap(True)
        self._result_hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        search_layout.addWidget(self._result_hint)

        layout.addWidget(search_group)

        data_group = QGroupBox("DADOS DO JOGO")
        form = QFormLayout(data_group)
        form.setSpacing(10)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Nome do jogo")
        form.addRow("Nome:", self._name_input)

        self._genre_input = QLineEdit()
        self._genre_input.setPlaceholderText("Acao, RPG, etc.")
        form.addRow("Genero:", self._genre_input)

        self._platform_input = QLineEdit("PC")
        form.addRow("Plataforma:", self._platform_input)

        self._dev_input = QLineEdit()
        self._dev_input.setPlaceholderText("Desenvolvedor")
        form.addRow("Desenvolvedor:", self._dev_input)

        self._desc_input = QTextEdit()
        self._desc_input.setMaximumHeight(90)
        self._desc_input.setPlaceholderText("Descricao do jogo...")
        form.addRow("Descricao:", self._desc_input)

        save_row = QHBoxLayout()
        self._save_input = QLineEdit()
        self._save_input.setPlaceholderText("Pasta de saves do jogo...")
        save_row.addWidget(self._save_input)

        save_btn = QPushButton("Procurar...")
        save_btn.clicked.connect(self._browse_save)
        save_row.addWidget(save_btn)
        form.addRow("Pasta de Saves:", save_row)

        img_row = QHBoxLayout()
        cover_btn = QPushButton("Selecionar Capa")
        cover_btn.clicked.connect(lambda: self._browse_image("cover"))
        img_row.addWidget(cover_btn)

        banner_btn = QPushButton("Selecionar Banner")
        banner_btn.clicked.connect(lambda: self._browse_image("banner"))
        img_row.addWidget(banner_btn)
        img_row.addStretch()
        form.addRow("Imagens:", img_row)

        layout.addWidget(data_group)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._add_btn = QPushButton("Adicionar Jogo")
        self._add_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1EA1FF; color: #ffffff;
                font-weight: bold; padding: 10px 30px;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4DB8FF; }
            QPushButton:disabled { background-color: #0D4A7A; color: #8EC3E8; }
            """
        )
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)

        layout.addLayout(btn_row)
        self._update_source_hint()

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Executavel",
            "",
            "Executaveis (*.exe);;Todos (*.*)",
        )
        if not path:
            return

        self._exe_input.setText(path)
        name = extract_game_name_from_path(path)
        if not self._name_input.text().strip():
            self._name_input.setText(name)
        if not self._search_input.text().strip():
            self._search_input.setText(name)

        if self.metadata_service.settings.get("auto_fetch_metadata", True):
            self._search_game()

    def _browse_save(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saves")
        if path:
            self._save_input.setText(path)

    def _browse_image(self, image_type: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Selecionar {image_type.title()}",
            "",
            "Imagens (*.png *.jpg *.jpeg *.webp);;Todos (*.*)",
        )
        if not path:
            return

        if image_type == "cover":
            self._cover_path = path
        else:
            self._banner_path = path
        self._set_status("Imagem manual selecionada.", "success")

    def _search_game(self):
        query = self._search_input.text().strip()
        if not query:
            self._set_status("Digite o nome do jogo para buscar.", "warning")
            return
        if self._search_thread and self._search_thread.isRunning():
            return

        self._results_list.clear()
        self._search_btn.setEnabled(False)
        self._search_btn.setText("Buscando...")
        self._set_status(
            "Buscando metadados online..."
            if self.metadata_service.rawg_key or self.metadata_service.sgdb_key
            else "Buscando no catalogo publico da Steam (sem precisar de chave)...",
            "info",
        )

        self._search_thread = _MetadataSearchThread(self.metadata_service, query)
        self._search_thread.results_ready.connect(self._on_results)
        self._search_thread.error.connect(self._on_search_error)
        self._search_thread.finished.connect(self._on_search_finished)
        self._search_thread.start()

    def _on_results(self, results):
        self._search_results = results or []
        self._results_list.clear()

        if not self._search_results:
            self._set_status(
                "Nenhum resultado online. Voce ainda pode cadastrar manualmente.",
                "warning",
            )
            return

        for result in self._search_results:
            source = result.get("source", "manual").upper()
            item = QListWidgetItem(f"{result.get('name', 'Desconhecido')}  [{source}]")
            item.setData(Qt.UserRole, result)
            self._results_list.addItem(item)

        first = self._search_results[0]
        if first.get("source") == "fallback":
            self._set_status(
                "Nao encontrei detalhes completos online. O cadastro pode ser finalizado manualmente.",
                "warning",
            )
        else:
            self._set_status(
                "Selecione um resultado para preencher os campos automaticamente.",
                "success",
            )

    def _on_search_error(self, message: str):
        self._results_list.clear()
        self._set_status(
            f"Falha ao buscar metadados: {message or 'erro desconhecido'}.",
            "error",
        )

    def _on_search_finished(self):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Buscar")

    def _select_search_result(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if self._details_thread and self._details_thread.isRunning():
            return

        self._selected_metadata = dict(data)
        self._name_input.setText(data.get("name", ""))
        self._add_btn.setEnabled(False)
        self._results_list.setEnabled(False)
        self._set_status("Carregando descricao e imagens do jogo...", "info")

        self._details_thread = _MetadataDetailsThread(
            self.metadata_service,
            self.image_service,
            data,
        )
        self._details_thread.details_ready.connect(self._on_details_ready)
        self._details_thread.error.connect(self._on_details_error)
        self._details_thread.finished.connect(self._on_details_finished)
        self._details_thread.start()

    def _on_details_ready(self, data: dict):
        self._selected_metadata = dict(data)
        self._name_input.setText(data.get("name", self._name_input.text()))
        self._desc_input.setText(data.get("description", ""))
        self._genre_input.setText(data.get("genre", ""))
        self._dev_input.setText(data.get("developer", ""))
        self._platform_input.setText(data.get("platforms", "PC") or "PC")

        if data.get("cover_path"):
            self._cover_path = data["cover_path"]
        if data.get("banner_path"):
            self._banner_path = data["banner_path"]

        if self._cover_path or self._banner_path:
            self._set_status(
                "Metadados carregados com sucesso. Imagens ja foram baixadas para o cache.",
                "success",
            )
        else:
            self._set_status(
                "Metadados carregados, mas sem imagens adicionais disponiveis.",
                "warning",
            )

    def _on_details_error(self, message: str):
        self._set_status(
            f"Falha ao carregar detalhes: {message or 'erro desconhecido'}.",
            "error",
        )

    def _on_details_finished(self):
        self._add_btn.setEnabled(True)
        self._results_list.setEnabled(True)

    def _on_add(self):
        if self._details_thread and self._details_thread.isRunning():
            QMessageBox.information(
                self,
                "Aguarde",
                "A busca de metadados ainda esta em andamento.",
            )
            return

        exe = self._exe_input.text().strip()
        name = self._name_input.text().strip()

        if not exe:
            QMessageBox.warning(self, "Erro", "Selecione o executavel do jogo.")
            return
        if not os.path.isfile(exe):
            QMessageBox.warning(self, "Erro", "O executavel nao existe.")
            return
        if not name:
            QMessageBox.warning(self, "Erro", "Informe o nome do jogo.")
            return

        self.result_data = {
            "name": name,
            "executable_path": exe,
            "save_folder": self._save_input.text().strip(),
            "genre": self._genre_input.text().strip(),
            "platform": self._platform_input.text().strip() or "PC",
            "developer": self._dev_input.text().strip(),
            "publisher": self._selected_metadata.get("publisher", ""),
            "release_date": self._selected_metadata.get("release_date", ""),
            "description": self._desc_input.toPlainText().strip(),
            "rawg_id": self._selected_metadata.get("rawg_id"),
            "cover_path": self._cover_path,
            "banner_path": self._banner_path,
            "background_path": self._banner_path or self._cover_path,
        }
        self.accept()

    def _update_source_hint(self):
        if self.metadata_service.rawg_key or self.metadata_service.sgdb_key:
            self._set_status(
                "Busca online pronta. Se houver chaves configuradas, RAWG e SteamGridDB serao usados automaticamente.",
                "info",
            )
        else:
            self._set_status(
                "Sem chaves configuradas. O launcher vai tentar buscar no catalogo publico da Steam e permitir edicao manual.",
                "warning",
            )

    def _set_status(self, message: str, level: str = "info"):
        colors = {
            "info": "#9aa4b2",
            "success": "#4ade80",
            "warning": "#FB923C",
            "error": "#f87171",
        }
        self._status_label.setStyleSheet(
            f"color: {colors.get(level, colors['info'])}; font-size: 12px;"
        )
        self._status_label.setText(message)

    def reject(self):
        if (self._search_thread and self._search_thread.isRunning()) or (
            self._details_thread and self._details_thread.isRunning()
        ):
            QMessageBox.information(
                self,
                "Aguarde",
                "Espere a busca de metadados terminar antes de fechar esta janela.",
            )
            return
        super().reject()
