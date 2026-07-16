import sys
import os
import json
import re
from datetime import datetime
from PySide6.QtWidgets import *
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QTextCursor

# ========== 从 backend 导入核心功能（统一使用 SQLite 存储）==========
from backend.core import call_ai_stream, SYSTEM_PROMPTS, export_result
from backend.database import HistoryDB, TemplateDB

# ========== main.py 配置（与 FastAPI 后端共享 SQLite 数据目录）==========
DATA_DIR = os.path.join(os.path.dirname(__file__), "backend", "data")
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "data", "exports")

os.makedirs(EXPORT_DIR, exist_ok=True)


# ========== AI工作线程 ==========
class AIWorker(QThread):
    text_updated = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, prompt, system_prompt=""):
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self):
        try:
            result = call_ai_stream(self.prompt, self.system_prompt, self.text_updated.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ========== 历史记录管理（使用 SQLite，与 Web 后端共享）==========
class HistoryManager:
    @staticmethod
    def load():
        """加载历史记录列表（返回 list[dict]）"""
        return HistoryDB.list(page=1, size=200).get("items", [])

    @staticmethod
    def add(mode, user_input, result):
        """添加一条历史记录"""
        mode_key = mode.replace("📖 ", "").replace("📝 ", "").replace("📋 ", "").replace("💬 ", "")
        HistoryDB.add(mode_key, user_input, result)


# ========== 提示词模板管理（使用 SQLite，与 Web 后端共享）==========
class TemplateManager:
    @staticmethod
    def load():
        """加载模板字典 {name: content}"""
        return TemplateDB.list_all() or {}

    @staticmethod
    def save(templates):
        """保存模板（合并写入）"""
        if isinstance(templates, dict):
            for name, content in templates.items():
                TemplateDB.save(name, content)


# ========== 主窗口 ==========
class AIStudyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📚 AI 学习助手 - 完整版")
        self.setGeometry(50, 50, 1200, 800)

        # 批量处理变量
        self.batch_lines = []
        self.batch_index = 0
        self.batch_results = []
        self.current_batch_worker = None

        # 当前AI工作线程
        self.worker = None

        self.setup_ui()
        self.load_history_list()
        self.load_templates()
        self.on_mode_change(self.mode_combo.currentText())

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # ===== 左侧主工作区 =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("📚 AI 学习助手")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50; padding: 10px;")
        left_layout.addWidget(title)

        # 功能选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("功能："))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["📖 考点拆分", "📝 生成题库", "📋 整理笔记", "💬 自由对话"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_change)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        left_layout.addLayout(mode_layout)

        # 输入区
        left_layout.addWidget(QLabel("输入内容："))
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("粘贴章节内容、知识点或输入问题...")
        self.input_text.setMinimumHeight(150)
        left_layout.addWidget(self.input_text)

        self.prompt_hint = QLabel("💡 输入内容后点击「提交」")
        self.prompt_hint.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        left_layout.addWidget(self.prompt_hint)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.btn_submit = QPushButton("🚀 提交")
        self.btn_submit.setStyleSheet(
            "background-color: #3498db; color: white; padding: 8px 20px; border-radius: 5px; font-weight: bold;"
        )
        self.btn_submit.clicked.connect(self.handle_submit)
        btn_layout.addWidget(self.btn_submit)

        self.btn_batch = QPushButton("📦 批量处理")
        self.btn_batch.setStyleSheet(
            "background-color: #9b59b6; color: white; padding: 8px 20px; border-radius: 5px; font-weight: bold;"
        )
        self.btn_batch.clicked.connect(self.handle_batch)
        btn_layout.addWidget(self.btn_batch)

        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        # 输出区
        left_layout.addWidget(QLabel("输出结果："))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(250)
        self.output_text.setStyleSheet(
            "border: 1px solid #ccc; border-radius: 5px; padding: 8px; font-family: 'Microsoft YaHei', 'Consolas', monospace;"
        )
        left_layout.addWidget(self.output_text)

        # 底部操作栏
        bottom_layout = QHBoxLayout()
        self.btn_export_md = QPushButton("📥 导出Markdown")
        self.btn_export_md.clicked.connect(lambda: self.export_current("markdown"))
        bottom_layout.addWidget(self.btn_export_md)

        self.btn_export_txt = QPushButton("📥 导出TXT")
        self.btn_export_txt.clicked.connect(lambda: self.export_current("txt"))
        bottom_layout.addWidget(self.btn_export_txt)

        self.btn_save_history = QPushButton("💾 保存到历史")
        self.btn_save_history.clicked.connect(self.save_to_history)
        bottom_layout.addWidget(self.btn_save_history)

        bottom_layout.addStretch()

        self.status_label = QLabel("✅ 就绪")
        self.status_label.setStyleSheet("color: #27ae60;")
        bottom_layout.addWidget(self.status_label)

        left_layout.addLayout(bottom_layout)

        # ===== 右侧边栏 =====
        right_widget = QWidget()
        right_widget.setMaximumWidth(350)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)

        right_layout.addWidget(QLabel("📜 历史记录"))
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.load_history)
        self.history_list.setMaximumHeight(200)
        right_layout.addWidget(self.history_list)

        btn_clear_history = QPushButton("清空历史")
        btn_clear_history.clicked.connect(self.clear_history)
        right_layout.addWidget(btn_clear_history)

        right_layout.addWidget(QLabel("📋 提示词模板"))
        self.template_combo = QComboBox()
        self.template_combo.currentTextChanged.connect(self.apply_template)
        right_layout.addWidget(self.template_combo)

        template_layout = QHBoxLayout()
        self.template_input = QLineEdit()
        self.template_input.setPlaceholderText("新模板名称")
        template_layout.addWidget(self.template_input)

        btn_save_template = QPushButton("保存")
        btn_save_template.clicked.connect(self.save_template)
        template_layout.addWidget(btn_save_template)
        right_layout.addLayout(template_layout)

        right_layout.addWidget(QLabel("📦 批量处理（每行一个）"))
        self.batch_input = QTextEdit()
        self.batch_input.setPlaceholderText("每行一个章节名或知识点...")
        self.batch_input.setMaximumHeight(120)
        right_layout.addWidget(self.batch_input)

        right_layout.addStretch()

        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(right_widget, 1)

    # ===== 辅助方法 =====
    def on_mode_change(self, mode):
        if mode == "💬 自由对话":
            self.prompt_hint.setText("💡 直接输入问题，AI会回答")
        else:
            self.prompt_hint.setText("💡 粘贴内容后点击「提交」")

    def get_template_names(self):
        templates = TemplateManager.load()
        return list(templates.keys())

    def load_templates(self):
        self.template_combo.clear()
        templates = TemplateManager.load()
        for name in templates:
            self.template_combo.addItem(name)

    def load_history_list(self):
        self.history_list.clear()
        history = HistoryManager.load()
        for item in history:
            display = f"[{item['time']}] {item['mode']}: {item['input'][:30]}"
            self.history_list.addItem(display)

    # ===== 提交（单条） =====
    def handle_submit(self):
        user_input = self.input_text.toPlainText().strip()
        if not user_input:
            self.output_text.setHtml("<p style='color: #e74c3c;'>⚠️ 请先输入内容！</p>")
            return

        mode = self.mode_combo.currentText()
        if mode == "📖 考点拆分":
            system_prompt = SYSTEM_PROMPTS["考点拆分"]
            prompt = f"请拆分以下章节的考点：\n\n{user_input}"
        elif mode == "📝 生成题库":
            system_prompt = SYSTEM_PROMPTS["生成题库"]
            prompt = f"请根据以下知识点生成题库：\n\n{user_input}"
        elif mode == "📋 整理笔记":
            system_prompt = SYSTEM_PROMPTS["整理笔记"]
            prompt = f"请整理以下内容为笔记：\n\n{user_input}"
        else:
            system_prompt = ""
            prompt = user_input

        self.btn_submit.setEnabled(False)
        self.btn_submit.setText("⏳ 处理中...")
        self.status_label.setText("⏳ AI 思考中...")
        self.status_label.setStyleSheet("color: #f39c12;")
        self.output_text.clear()

        self.worker = AIWorker(prompt, system_prompt)
        self.worker.text_updated.connect(self.append_text)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.error.connect(self.on_ai_error)
        self.worker.start()

    def append_text(self, text):
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output_text.setTextCursor(cursor)
        self.output_text.ensureCursorVisible()
        QApplication.processEvents()

    def on_ai_finished(self, result):
        self.btn_submit.setEnabled(True)
        self.btn_submit.setText("🚀 提交")
        self.status_label.setText("✅ 完成")
        self.status_label.setStyleSheet("color: #27ae60;")

    def on_ai_error(self, error_msg):
        self.output_text.setPlainText(f"❌ 错误：{error_msg}")
        self.btn_submit.setEnabled(True)
        self.btn_submit.setText("🚀 提交")
        self.status_label.setText("❌ 出错了")
        self.status_label.setStyleSheet("color: #e74c3c;")

    # ===== 批量处理 =====
    def handle_batch(self):
        lines = self.batch_input.toPlainText().strip().split('\n')
        self.batch_lines = [l.strip() for l in lines if l.strip()]
        if not self.batch_lines:
            self.output_text.setHtml("<p style='color: #e74c3c;'>⚠️ 请在批量输入区每行写一个知识点！</p>")
            return

        self.btn_batch.setEnabled(False)
        self.btn_batch.setText("⏳ 处理中...")
        self.output_text.clear()
        self.batch_results = []
        self.batch_index = 0
        self.process_next_batch()

    def process_next_batch(self):
        if self.batch_index >= len(self.batch_lines):
            self.output_text.setPlainText("\n\n---\n\n".join(self.batch_results))
            self.btn_batch.setEnabled(True)
            self.btn_batch.setText("📦 批量处理")
            self.status_label.setText(f"✅ 完成 {len(self.batch_results)} 项")
            self.status_label.setStyleSheet("color: #27ae60;")
            return

        user_input = self.batch_lines[self.batch_index]
        self.status_label.setText(f"⏳ 处理 {self.batch_index + 1}/{len(self.batch_lines)}")
        self.status_label.setStyleSheet("color: #f39c12;")
        QApplication.processEvents()

        mode = self.mode_combo.currentText()
        if mode == "📖 考点拆分":
            system_prompt = SYSTEM_PROMPTS["考点拆分"]
            prompt = f"请拆分以下章节的考点：\n\n{user_input}"
        elif mode == "📝 生成题库":
            system_prompt = SYSTEM_PROMPTS["生成题库"]
            prompt = f"请根据以下知识点生成题库：\n\n{user_input}"
        elif mode == "📋 整理笔记":
            system_prompt = SYSTEM_PROMPTS["整理笔记"]
            prompt = f"请整理以下内容为笔记：\n\n{user_input}"
        else:
            system_prompt = ""
            prompt = user_input

        worker = AIWorker(prompt, system_prompt)
        worker.finished.connect(self.on_batch_item_finished)
        worker.error.connect(self.on_batch_item_error)
        self.current_batch_worker = worker
        worker.start()

    def on_batch_item_finished(self, result):
        self.batch_results.append(result)
        self.batch_index += 1
        self.process_next_batch()

    def on_batch_item_error(self, error_msg):
        self.batch_results.append(f"❌ 错误：{error_msg}")
        self.batch_index += 1
        self.process_next_batch()

    # ===== 导出 =====
    def export_current(self, export_type):
        content = self.output_text.toPlainText().strip()
        if not content:
            self.status_label.setText("⚠️ 没有内容可导出")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return
        filename = export_result(content, export_type)
        self.status_label.setText(f"✅ 已导出：{os.path.basename(filename)}")
        self.status_label.setStyleSheet("color: #27ae60;")
        QMessageBox.information(self, "导出成功", f"文件已保存到：\n{filename}")

    # ===== 历史记录 =====
    def save_to_history(self):
        user_input = self.input_text.toPlainText().strip()
        result = self.output_text.toPlainText().strip()
        if not user_input or not result:
            self.status_label.setText("⚠️ 没有内容可保存")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return
        mode = self.mode_combo.currentText()
        HistoryManager.add(mode, user_input, result)
        self.load_history_list()
        self.status_label.setText("✅ 已保存到历史")
        self.status_label.setStyleSheet("color: #27ae60;")

    def load_history(self, item):
        idx = self.history_list.currentRow()
        history = HistoryManager.load()
        if idx < len(history):
            self.output_text.setPlainText(history[idx]['result'])
            self.status_label.setText("✅ 已加载历史记录")
            self.status_label.setStyleSheet("color: #27ae60;")

    def clear_history(self):
        if QMessageBox.question(self, "确认", "确定要清空所有历史记录吗？") == QMessageBox.StandardButton.Yes:
            HistoryDB.clear()
            self.load_history_list()
            self.status_label.setText("✅ 历史已清空")
            self.status_label.setStyleSheet("color: #27ae60;")

    # ===== 提示词模板 =====
    def save_template(self):
        name = self.template_input.text().strip()
        if not name:
            self.status_label.setText("⚠️ 请输入模板名称")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return
        content = self.output_text.toPlainText().strip()
        if not content:
            self.status_label.setText("⚠️ 输出区没有内容可保存为模板")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return
        templates = TemplateManager.load()
        templates[name] = content
        TemplateManager.save(templates)
        self.load_templates()
        self.status_label.setText(f"✅ 模板已保存：{name}")
        self.status_label.setStyleSheet("color: #27ae60;")
        self.template_input.clear()

    def apply_template(self, name):
        templates = TemplateManager.load()
        if name in templates:
            self.output_text.setPlainText(templates[name])
            self.status_label.setText(f"✅ 已应用模板：{name}")
            self.status_label.setStyleSheet("color: #27ae60;")


# ========== 启动 ==========
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AIStudyApp()
    window.show()
    sys.exit(app.exec())
