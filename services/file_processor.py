"""
文件处理服务 - 解析文件内容并进行文本切片
"""
import os
import chardet
from PyPDF2 import PdfReader
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from flask import current_app


class FileProcessor:
    """文件解析与切片服务"""

    SUPPORTED_TYPES = {'txt', 'doc', 'docx', 'pdf'}

    def __init__(self):
        self.text_splitter = None

    def _get_splitter(self):
        """获取文本切片器"""
        if self.text_splitter is None:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=current_app.config.get('CHUNK_SIZE', 512),
                chunk_overlap=current_app.config.get('CHUNK_OVERLAP', 50),
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
            )
        return self.text_splitter

    @staticmethod
    def allowed_file(filename):
        """检查文件类型是否允许"""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in current_app.config.get('ALLOWED_EXTENSIONS', FileProcessor.SUPPORTED_TYPES)

    @staticmethod
    def get_file_extension(filename):
        """获取文件扩展名"""
        if '.' not in filename:
            return ''
        return filename.rsplit('.', 1)[1].lower()

    def extract_text(self, file_path, file_type):
        """
        根据文件类型提取文本内容

        Args:
            file_path: 文件路径
            file_type: 文件类型 (txt, doc, docx, pdf)

        Returns:
            str: 提取的文本内容
        """
        if file_type == 'txt':
            return self._extract_txt(file_path)
        elif file_type == 'pdf':
            return self._extract_pdf(file_path)
        elif file_type in ('doc', 'docx'):
            return self._extract_docx(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")

    @staticmethod
    def _extract_txt(file_path):
        """提取 TXT 文件文本"""
        # 先检测编码
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')

        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            return f.read()

    @staticmethod
    def _extract_pdf(file_path):
        """提取 PDF 文件文本"""
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return '\n'.join(text_parts)

    @staticmethod
    def _extract_docx(file_path):
        """提取 DOCX 文件文本"""
        doc = DocxDocument(file_path)
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        return '\n'.join(text_parts)

    def split_text(self, text):
        """
        将文本切分为多个片段

        Args:
            text: 待切分的文本

        Returns:
            list[str]: 切片列表
        """
        if not text or not text.strip():
            return []
        splitter = self._get_splitter()
        chunks = splitter.split_text(text)
        return chunks

    def process_file(self, file_path, file_type):
        """
        处理文件：提取文本 + 切片

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            list[str]: 切片列表
        """
        text = self.extract_text(file_path, file_type)
        chunks = self.split_text(text)
        return chunks


# 全局实例
file_processor = FileProcessor()
