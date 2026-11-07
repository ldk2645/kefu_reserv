"""Real product data stays in this local window; no automatic approval."""
import json

from PySide6.QtCore import QThreadPool,Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QWidget,QComboBox,
    QLineEdit,QLabel,QCheckBox,QPushButton,QPlainTextEdit,QSplitter,QTabWidget,QScrollArea,QSizePolicy)

from app.services.first_product import FirstProduct
from app.ui.workers import Worker
from kbs_collector.normalizer import markdown
from kbs_collector.chunks import knowledge_chunks


class FirstProductDialog(QDialog):
    def __init__(self,db,settings,parent=None,collection_dir=None):
        super().__init__(parent)
        self.settings=settings
        self.service=FirstProduct(db,settings.data_dir,collection_dir)
        self.pool=QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.workers=set()
        self.binding=self.verification=None
        self.source_status=None
        self.selected_product_id=None
        self.loading=False
        self.setWindowTitle('小鲸 · 首个真实商品核对与离线验证')
        self.resize(1160,850)
        layout=QVBoxLayout(self)
        self.status=QLabel('选择型号明确的样本，填写真实店铺信息。原文只在本机显示；采集资料默认待审核。')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        layout.addWidget(self.status)
        self.controls=QWidget()
        outer=QVBoxLayout(self.controls)
        self.next_step=QLabel()
        self.next_step.setWordWrap(True)
        self.next_step.setTextFormat(Qt.TextFormat.PlainText)
        self.next_step.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        outer.addWidget(self.next_step)
        self.choices=QComboBox()
        self.choices.currentIndexChanged.connect(self.select_candidate)
        outer.addWidget(self.choices)
        split=QSplitter()
        form_widget=QWidget()
        form=QFormLayout(form_widget)
        self.model=QLineEdit()
        self.model.setReadOnly(True)
        self.brand=QLineEdit()
        self.sku=QLineEdit()
        self.sku.setPlaceholderText('店铺商品规格编码，需与你选中的准确型号对应')
        self.basis=QLineEdit()
        self.basis.setPlaceholderText('例如已核对商品包装/在售商品清单；不填订单或客户信息')
        self.reviewer=QLineEdit()
        self.reviewer.setPlaceholderText('填写本地审核员别名即可')
        for title,widget in [('页面准确型号',self.model),('实际品牌',self.brand),('真实店铺 SKU',self.sku),
                             ('品牌与 SKU 核对依据',self.basis),('审核员别名',self.reviewer)]:
            form.addRow(title,widget)
        self.metadata_confirmed=QCheckBox('我已核对品牌、准确型号与店铺 SKU 的对应关系')
        form.addRow(self.metadata_confirmed)
        self.bind_button=QPushButton('1 建立商品并追加为待审核')
        self.bind_button.clicked.connect(self.bind)
        form.addRow(self.bind_button)
        self.content_confirmed=QCheckBox('我已阅读原文及知识片段，确认准确、完整且适用于该型号')
        form.addRow(self.content_confirmed)
        self.review_button=QPushButton('2 人工批准这份资料')
        self.review_button.clicked.connect(self.approve)
        form.addRow(self.review_button)
        self.question=QLineEdit()
        self.question.setPlaceholderText('填写一个典型问题，仅用于本机验证')
        form.addRow('典型问题',self.question)
        self.verify_button=QPushButton('3 验证离线检索与草稿')
        self.verify_button.clicked.connect(self.verify)
        form.addRow(self.verify_button)
        self.use_button=QPushButton('4 在主窗口使用这个商品')
        self.use_button.clicked.connect(self.use_product)
        self.use_button.setEnabled(False)
        form.addRow(self.use_button)
        info=QLabel('批准资料不会发送回复。主窗口生成的每一条回复仍须编辑、审核后复制。\n本轮只接入一个商品，不自动批准视频。')
        info.setWordWrap(True)
        form.addRow(info)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        split.addWidget(scroll)
        self.tabs=QTabWidget()
        self.original=QPlainTextEdit()
        self.fragments=QPlainTextEdit()
        self.result=QPlainTextEdit()
        for title,widget in [('来源与原文',self.original),('将用于检索的片段',self.fragments),('离线验证结果',self.result)]:
            widget.setReadOnly(True)
            self.tabs.addTab(widget,title)
        split.addWidget(self.tabs)
        split.setSizes([450,650])
        outer.addWidget(split,1)
        layout.addWidget(self.controls,1)
        for widget in [self.brand,self.sku,self.basis,self.reviewer]:
            widget.textChanged.connect(self.metadata_changed)
        self.question.textChanged.connect(self.question_changed)
        self.metadata_confirmed.toggled.connect(self.update_actions)
        self.content_confirmed.toggled.connect(self.update_actions)
        self.update_actions()
        self.run(self.service.candidates,self.loaded)

    def update_actions(self,*args):
        if self.loading:
            return
        capture=self.choices.currentData()
        missing=[name for name,widget in [('实际品牌',self.brand),('店铺 SKU',self.sku),
            ('核对依据',self.basis),('审核员别名',self.reviewer)] if not widget.text().strip()]
        approved=bool(self.binding and self.source_status=='approved')
        passed=bool(approved and self.verification and self.verification['stats']['passed'])
        self.bind_button.setEnabled(bool(capture and not missing and self.metadata_confirmed.isChecked() and not self.binding))
        self.review_button.setEnabled(bool(self.binding and not approved and self.content_confirmed.isChecked()))
        self.verify_button.setEnabled(approved and bool(self.question.text().strip()))
        self.use_button.setEnabled(passed)
        if not capture:
            message='尚无可接入样本：需要页面明确标注准确型号的资料。'
        elif missing:
            message='第 1 步：尚未保存。请填写：'+'、'.join(missing)+'。'
        elif not self.binding:
            message=('第 1 步：对应关系已勾选，请点击“建立商品并追加为待审核”保存。' if self.metadata_confirmed.isChecked()
                else '第 1 步：请核对品牌、准确型号与 SKU 的关系，并勾选确认。')
        elif not approved:
            message='第 2 步：已导入，资料尚未批准。请阅读右侧原文及片段，勾选内容确认，再点击“人工批准这份资料”。'
        elif not passed:
            message='第 3 步：资料已有人审记录，请填写典型问题并点击“验证离线检索与草稿”。'
        else:
            message='第 4 步：离线验证通过，可点击“在主窗口使用这个商品”。每条回复仍需人工审核。'
        self.next_step.setText(message)

    def run(self,function,done):
        if self.workers:
            return
        self.controls.setEnabled(False)
        worker=Worker(function)
        self.workers.add(worker)
        worker.signals.done.connect(done)
        worker.signals.failed.connect(self.status.setText)
        def finished():
            self.workers.discard(worker)
            self.controls.setEnabled(True)
            self.update_actions()
        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    def loaded(self,captures):
        self.choices.clear()
        for capture in sorted(captures,key=lambda c:c.product.category!='生活电器'):
            self.choices.addItem(capture.product.category+' / '+capture.product.name+' / '+capture.product.model,capture)
        if not captures:
            self.status.setText('未找到型号明确的最新真实样本。请先在采集器核对型号证据并保存。')

    def select_candidate(self,index):
        capture=self.choices.currentData()
        if not capture:
            return
        self.loading=True
        self.binding=self.verification=None
        self.source_status=None
        self.use_button.setEnabled(False)
        self.metadata_confirmed.setChecked(False)
        self.content_confirmed.setChecked(False)
        self.model.setText(capture.product.model)
        self.brand.setText('' if 'BRAND_UNCONFIRMED' in capture.issues else capture.product.brand)
        for widget in [self.sku,self.basis,self.reviewer]:
            widget.clear()
        self.question.setText(self.service.suggested_question(capture))
        self.original.setPlainText(markdown(capture)+'\n\niframe 原始来源：'+capture.frame_url)
        self.fragments.setPlainText('\n\n'.join(section+'\n'+text for section,text in knowledge_chunks(capture)))
        self.result.clear()
        try:
            state=json.loads(self.service.state_path.read_text(encoding='utf-8'))
            saved=state['binding']
            if saved['article_id']==capture.id:
                rows=self.service.db.rows('SELECT * FROM kbs_product_bindings WHERE source_id=?',(saved['source_id'],))
                status=self.service.binding_status(saved)
                if rows and status:
                    item=rows[0]
                    self.brand.setText(item['confirmed_brand'])
                    self.sku.setText(item['confirmed_sku'])
                    self.basis.setText(item['confirmation_basis'])
                    self.reviewer.setText(item['confirmed_by'])
                    self.binding=saved
                    self.source_status=status
                    self.status.setText('已载入上次接入记录。资料审核状态以本地知识库为准，可继续验证。')
        except (OSError,ValueError,KeyError,TypeError):
            pass
        self.loading=False
        self.update_actions()

    def metadata_changed(self,*args):
        if self.loading:
            return
        self.binding=self.verification=None
        self.source_status=None
        self.metadata_confirmed.setChecked(False)
        self.content_confirmed.setChecked(False)
        self.use_button.setEnabled(False)
        self.update_actions()

    def question_changed(self,*args):
        self.verification=None
        self.use_button.setEnabled(False)
        self.update_actions()

    def bind(self):
        capture=self.choices.currentData()
        if not capture:
            return
        values=(capture.id,self.brand.text(),self.sku.text(),self.basis.text(),self.reviewer.text())
        confirmed=self.metadata_confirmed.isChecked()
        def done(binding):
            self.binding=binding
            self.source_status=self.service.binding_status(binding)
            self.content_confirmed.setChecked(False)
            self.status.setText('商品与来源已追加保存，采集原件未修改。请核对右侧原文及片段后亲自审核。')
        self.run(lambda:self.service.bind(*values,confirmed=confirmed),done)

    def approve(self):
        if not self.binding:
            self.status.setText('请先完成商品对应关系核对并追加导入。')
            return
        binding,reviewer,confirmed=dict(self.binding),self.reviewer.text(),self.content_confirmed.isChecked()
        def done(status):
            self.source_status=status
            self.status.setText('已记录你的人工审核。现在可以用典型问题验证离线检索与草稿。')
        self.run(lambda:self.service.review(binding,reviewer,confirmed=confirmed),done)

    def verify(self):
        if not self.binding:
            self.status.setText('请先建立商品并追加导入资料。')
            return
        binding,question=dict(self.binding),self.question.text()
        def done(result):
            self.verification=result
            stats=result['stats']
            lines=['离线验证：'+('通过' if stats['passed'] else '未通过：请检查资料审核状态、问题和适用范围'),
                f"命中该来源的片段：{stats['matching_source_hits']}",
                '回复未经人工审核不可复制：'+str(stats['copy_requires_review']),
                '错误 SKU 被拒绝：'+str(stats['wrong_sku_blocked']),
                '', '待审核草稿：',result['draft'].customer_reply,'','本次检索来源：']
            for hit in result['evidence'].hits:
                lines.extend([hit.title+' / '+hit.section,hit.source_url,hit.excerpt,''])
            self.result.setPlainText('\n'.join(lines))
            self.tabs.setCurrentWidget(self.result)
            self.use_button.setEnabled(stats['passed'])
            self.status.setText('验证通过，仍需在主窗口逐条审核回复。' if stats['passed'] else '验证尚未通过；没有自动批准或发送任何回复。')
        self.run(lambda:self.service.verify(binding,question),done)

    def use_product(self):
        if not self.binding or not self.verification or not self.verification['stats']['passed']:
            return
        self.settings.demo_mode=False
        try:
            self.settings.save_preferences()
        except OSError:
            self.status.setText('无法保存本地设置，请检查数据目录权限。')
            return
        self.selected_product_id=self.binding['product_id']
        self.accept()

    def reject(self):
        if self.workers:
            self.status.setText('本地任务正在完成，请稍候关闭。')
            return
        super().reject()

    def closeEvent(self,event):
        if self.workers:
            self.status.setText('本地任务正在完成，请稍候关闭。')
            event.ignore()
        else:
            event.accept()
