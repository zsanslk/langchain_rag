"""
文档流处理服务 (Document Service)
====================================
本模块对应论文第 5.2 节：《高质量文档流处理与递归切片实现》

核心职责：
1. 多格式文档解析（TXT / PDF / DOCX）
2. 基于自然语言边界的递归字符切片（RecursiveCharacterTextSplitter）
3. 文档入库全流程编排（解析 → 切片 → 向量化 → 持久化）
4. 处理耗时统计（用于论文 表6-2 延迟分析）

切片策略（论文 5.2 节）：
- CHUNK_SIZE  = 512 字符（约 256~400 中文 token）
- CHUNK_OVERLAP = 50 字符（保证相邻切片保留 2~3 句上下文衔接）
- 优先分隔符：双换行 > 单换行 > 句号/叹号/问号 > 空格 > 逐字符
"""

import os
import time
import chardet
from flask import current_app


class RecursiveCharacterTextSplitter:
    """
    纯 Python 实现的递归字符切片器
    (移除了 langchain 依赖，避免由于 torch DLL 初始化失败导致的系统崩溃)
    """

    def __init__(
        self, chunk_size=512, chunk_overlap=50, separators=None, length_function=len
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._separators = separators or [
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            ".",
            "!",
            "?",
            " ",
            "",
        ]

    def _split_text_with_regex(self, text: str, separator: str) -> list[str]:
        if separator:
            splits = text.split(separator)
            return [s + separator for s in splits[:-1]] + (
                [splits[-1]] if splits[-1] else []
            )
        return list(text)

    def split_text(self, text: str) -> list[str]:
        final_chunks = []
        separator = self._separators[-1]
        new_separators = []
        for i, _s in enumerate(self._separators):
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                new_separators = self._separators[i + 1 :]
                break

        splits = self._split_text_with_regex(text, separator)

        good_splits = []
        _separator = "" if separator == "" else separator
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, _separator)
                    final_chunks.extend(merged)
                    good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_recursive(s, new_separators)
                    final_chunks.extend(other_info)

        if good_splits:
            merged = self._merge_splits(good_splits, _separator)
            final_chunks.extend(merged)

        return final_chunks

    def _split_recursive(self, text, separators):
        # 简单递归调用
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            separators=separators,
            length_function=self._length_function,
        )
        return splitter.split_text(text)

    def _merge_splits(self, splits, separator):
        docs = []
        current_doc = []
        total = 0
        for d in splits:
            _len = self._length_function(d)
            if total + _len > self._chunk_size and current_doc:
                docs.append("".join(current_doc).strip())
                while total > self._chunk_overlap or (
                    total + _len > self._chunk_size and total > 0
                ):
                    total -= self._length_function(current_doc[0])
                    current_doc.pop(0)
            current_doc.append(d)
            total += _len
        if current_doc:
            docs.append("".join(current_doc).strip())
        return docs


class DocumentService:
    """
    文档流处理服务

    封装了从原始文件到可检索知识切片的完整处理链路:
    原始文件 → 文本提取 → 递归切片 → (向量化由 EmbeddingService 负责)
    """

    # 支持的文档格式及其对应的解析引擎（论文 5.2 节）
    SUPPORTED_TYPES = {
        "txt": "chardet + 原生读取",
        "pdf": "PyPDF2 / PDFMiner",
        "doc": "python-docx (Docx2txt)",
        "docx": "python-docx (Docx2txt)",
    }

    def __init__(self):
        self._splitter = None  # 延迟初始化，等待 Flask 应用上下文

    # ------------------------------------------------------------------
    # 1. 文本切片器（递归字符策略）
    # ------------------------------------------------------------------

    def _get_splitter(self) -> RecursiveCharacterTextSplitter:
        """
        获取递归字符切片器（懒加载，确保在 Flask 上下文中读取配置）

        分隔符优先级（论文 5.2 节描述）：
          双换行符（段落边界）> 单换行符 > 中文句号/叹号/问号
          > 英文punct > 空格 > 逐字符兜底
        """
        if self._splitter is None:
            chunk_size = current_app.config.get("CHUNK_SIZE", 512)
            chunk_overlap = current_app.config.get("CHUNK_OVERLAP", 50)

            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                separators=[
                    "\n\n",  # 段落分隔（最优先）
                    "\n",  # 行分隔
                    "。",  # 中文句号
                    "！",  # 中文叹号
                    "？",  # 中文问号
                    ".",  # 英文句号
                    "!",  # 英文叹号
                    "?",  # 英文问号
                    "；",  # 中文分号
                    ";",  # 英文分号
                    " ",  # 空格
                    "",  # 逐字符（最终兜底）
                ],
            )
            print(
                f"[DocumentService] 递归切片器已初始化 | "
                f"CHUNK_SIZE={chunk_size} | CHUNK_OVERLAP={chunk_overlap}"
            )
        return self._splitter

    # ------------------------------------------------------------------
    # 2. 多格式文本提取
    # ------------------------------------------------------------------

    def extract_text(self, file_path: str, file_type: str) -> str:
        """
        根据文件后缀名调用对应的解析引擎提取纯文本（论文 5.2 节）

        Args:
            file_path: 文件的绝对路径
            file_type: 文件类型，如 'txt' / 'pdf' / 'docx'

        Returns:
            str: 提取出的纯文本内容

        Raises:
            ValueError: 不支持的文件类型
            RuntimeError: 文件解析失败
        """
        file_type = file_type.lower().strip(".")

        if file_type == "txt":
            return self._extract_txt(file_path)
        elif file_type == "pdf":
            return self._extract_pdf(file_path)
        elif file_type in ("doc", "docx"):
            return self._extract_docx(file_path)
        else:
            raise ValueError(
                f"不支持的文件类型: '{file_type}'，"
                f"当前支持: {list(self.SUPPORTED_TYPES.keys())}"
            )

    @staticmethod
    def _extract_txt(file_path: str) -> str:
        """
        TXT 文本提取

        使用 chardet 自动检测编码，避免 GBK/UTF-8 乱码问题（论文 5.2 节）
        """
        with open(file_path, "rb") as f:
            raw_data = f.read()

        detected = chardet.detect(raw_data)
        encoding = detected.get("encoding") or "utf-8"
        confidence = detected.get("confidence", 0)

        print(
            f"[DocumentService] TXT 编码检测: {encoding} " f"(置信度 {confidence:.0%})"
        )

        return raw_data.decode(encoding, errors="ignore")

    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        """
        PDF 文本提取（论文 5.2 节：调用 PDFMiner/PyPDF2 解析引擎）

        优先使用 PyPDF2，若失败则尝试 pdfplumber 兜底
        """
        text_parts = []

        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_parts.append(page_text)
            print(
                f"[DocumentService] PDF 解析完成 | "
                f"共 {len(reader.pages)} 页，提取 {len(text_parts)} 页有效文本"
            )
        except Exception as e:
            print(f"[DocumentService] PyPDF2 解析失败: {e}，尝试 pdfplumber...")
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text and text.strip():
                            text_parts.append(text)
            except ImportError:
                raise RuntimeError(f"PDF 解析失败，请安装 PyPDF2 或 pdfplumber: {e}")

        return "\n".join(text_parts)

    @staticmethod
    def _extract_docx(file_path: str) -> str:
        """
        DOCX 文本提取（论文 5.2 节：调用 python-docx 解析引擎）

        同时提取段落文本和表格内容（增强版，基础版仅提取段落）
        """
        try:
            from docx import Document as DocxDocument
        except ImportError:
            raise RuntimeError("请安装 python-docx: pip install python-docx")

        doc = DocxDocument(file_path)
        text_parts = []

        # 提取正文段落
        para_count = 0
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
                para_count += 1

        # 提取表格内容（确保表格中的关键信息不丢失）
        table_count = 0
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    text_parts.append(row_text)
                    table_count += 1

        print(
            f"[DocumentService] DOCX 解析完成 | "
            f"段落: {para_count} | 表格行: {table_count}"
        )
        return "\n".join(text_parts)

    # ------------------------------------------------------------------
    # 3. 递归切片
    # ------------------------------------------------------------------

    def split_text(self, text: str) -> list[str]:
        """
        对提取的长文本进行递归字符切片（论文 5.2 节核心算法）

        切片策略：
        - 优先寻找双换行符（段落界限）作为切割点
        - 若段落过长则退化到中文句号、英文句号
        - 最终按字符计数兜底
        - 保留 CHUNK_OVERLAP 字符的滑动窗口重叠，确保跨切片语义衔接

        Args:
            text: 从文件中提取的原始文本

        Returns:
            list[str]: 切片列表（平均长度约为 CHUNK_SIZE 字符）
        """
        if not text or not text.strip():
            print("[DocumentService] ⚠️ 输入文本为空，跳过切片")
            return []

        t_start = time.perf_counter()
        splitter = self._get_splitter()
        chunks = splitter.split_text(text)
        elapsed_ms = (time.perf_counter() - t_start) * 1000

        # 过滤掉长度过短（< 10字符）的无意义碎片
        chunks = [c for c in chunks if len(c.strip()) >= 10]

        print(
            f"[DocumentService] 切片完成 | "
            f"原文 {len(text)} 字符 → {len(chunks)} 个切片 | "
            f"耗时 {elapsed_ms:.1f}ms"
        )
        return chunks

    # ------------------------------------------------------------------
    # 4. 文档处理全流程编排（解析 + 切片）
    # ------------------------------------------------------------------

    def process_document(
        self,
        file_path: str,
        file_type: str,
        document_id: int = None,
    ) -> dict:
        """
        文档入库处理主函数（论文 5.2 节所描述的"文档入库流程"）

        流程:
          文件 → [文本提取] → [递归切片] → 返回切片列表
          （向量化与数据库持久化由调用方 EmbeddingService 负责）

        Args:
            file_path:   文件绝对路径
            file_type:   文件类型（txt/pdf/docx）
            document_id: 文档ID，用于日志标识（可选）

        Returns:
            dict: {
                'chunks':      list[str],   # 切片文本列表
                'chunk_count': int,         # 切片数量
                'char_count':  int,         # 原文字符总数
                'extract_ms':  float,       # 文本提取耗时(ms)
                'split_ms':    float,       # 切片耗时(ms)
            }
        """
        doc_tag = f"[doc_id={document_id}]" if document_id else ""
        print(f"[DocumentService] {doc_tag} 开始处理: {os.path.basename(file_path)}")

        # Step 1: 文本提取
        t0 = time.perf_counter()
        text = self.extract_text(file_path, file_type)
        extract_ms = (time.perf_counter() - t0) * 1000

        if not text or not text.strip():
            raise ValueError(f"文件 '{file_path}' 内容为空或解析后无有效文本")

        # Step 2: 递归切片
        t1 = time.perf_counter()
        chunks = self.split_text(text)
        split_ms = (time.perf_counter() - t1) * 1000

        if not chunks:
            raise ValueError(f"文件 '{file_path}' 切片后结果为空")

        print(
            f"[DocumentService] {doc_tag} ✅ 处理完成 | "
            f"字符数: {len(text)} | 切片数: {len(chunks)} | "
            f"提取: {extract_ms:.1f}ms | 切片: {split_ms:.1f}ms"
        )

        return {
            "chunks": chunks,
            "chunk_count": len(chunks),
            "char_count": len(text),
            "extract_ms": round(extract_ms, 2),
            "split_ms": round(split_ms, 2),
        }

    # ------------------------------------------------------------------
    # 5. 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def allowed_file(filename: str) -> bool:
        """检查文件扩展名是否在允许列表中"""
        if "." not in filename:
            return False
        # xxxxx.pdf -> [xxxx, pdf]
        ext = filename.rsplit(".", 1)[1].lower()
        try:
            allowed = current_app.config.get(
                "ALLOWED_EXTENSIONS", {"txt", "doc", "docx", "pdf"}
            )
            return ext in allowed  # True / f
        except RuntimeError:
            # 无 Flask 上下文时的兜底
            return ext in {"txt", "doc", "docx", "pdf"}

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """提取文件扩展名（小写）"""
        if "." not in filename:
            return ""
        return filename.rsplit(".", 1)[1].lower()  # 'pdf'


# ------------------------------------------------------------------
# 全局单例（与其他 service 保持一致的使用方式）
# ------------------------------------------------------------------
document_service = DocumentService()
