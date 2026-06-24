"""
向量化服务 - 使用 QWEN API 进行文本向量化和相似度检索
"""

import json
import httpx
from flask import current_app
from models import db
from models.document import DocumentChunk


class EmbeddingService:
    """向量化服务"""

    def __init__(self):
        """初始化向量模型"""
        self.model = None
        try:
            # 设置 Hugging Face 镜像 (国内加速)
            import os
            from sentence_transformers import SentenceTransformer

            # 优先尝试本地模型路径
            # 使用 os.getcwd() 或 __file__ 定位，避免 current_app 上下文错误
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            local_model_path = os.path.join(
                base_dir, "local_models", "text2vec-base-chinese"
            )
            model_name = "shibing624/text2vec-base-chinese"

            print(f"正在加载向量模型...")
            try:
                if (
                    os.path.exists(local_model_path)
                    and os.path.isdir(local_model_path)
                    and any(os.scandir(local_model_path))
                ):
                    print(f"检测到本地模型，正在加载: {local_model_path}")
                    try:
                        self.model = SentenceTransformer(local_model_path)
                    except TypeError as te:
                        # 这是一个常见错误：用户手动下载时漏掉了 子目录 (1_Pooling)
                        # 我们尝试手动构建模型
                        print(f"标准加载失败 ({te})，尝试手动构建模型布局...")
                        from sentence_transformers import models

                        word_embedding_model = models.Transformer(local_model_path)
                        pooling_model = models.Pooling(
                            word_embedding_model.get_word_embedding_dimension()
                        )
                        self.model = SentenceTransformer(
                            modules=[word_embedding_model, pooling_model]
                        )
                else:
                    print(f"本地模型未找到，尝试在线加载: {model_name}")
                    self.model = SentenceTransformer(model_name)

                print("向量模型加载完成！")
            except Exception as e:
                print(f"向量模型加载失败: {e}")
                print("WARNING: 将降级使用 MVP 伪向量模式 (语义搜索精度会下降)")
                self.model = None
        except Exception as e:
            print(f"向量模型库未安装或加载失败: {e}")
            print("WARNING: 将降级使用 MVP 伪向量模式 (语义搜索精度会下降)")

    def _get_api_config(self):
        """获取 API 配置"""
        return {
            "api_key": current_app.config.get("QWEN_API_KEY", ""),
            "base_url": current_app.config.get(
                "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            ),
        }

    def get_embedding(self, text):
        """
        获取文本的向量表示 (使用 SentenceTransformer)
        """
        if self.model:
            try:
                # encode 返回 numpy array，需要转为 list
                vector = self.model.encode(text)
                return vector.tolist()
            except Exception as e:
                print(f"向量生成失败: {e}")
                return [0.0] * 768  # 降级

        # 降级方案：MVP 伪向量 (仅当模型加载失败时使用)
        vector = [0.0] * 768  # 维度调整为 768 以保持兼容性尝试
        for i, char in enumerate(text[:1000]):
            idx = ord(char) % 768
            vector[idx] += 1.0

        # 归一化
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def store_chunk_embeddings(self, document_id, chunks):
        """
        为文档切片生成并存储向量（双写：MySQL + FAISS 持久化索引）

        Args:
            document_id: 文档ID
            chunks: 切片文本列表

        Returns:
            int: 存储的切片数量
        """
        from services.faiss_store import faiss_store

        count = 0
        new_chunk_ids = []
        new_vectors = []

        for idx, chunk_text in enumerate(chunks):
            embedding = self.get_embedding(chunk_text)  # 进行向量化

            chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=idx,
                chunk_content=chunk_text,
                embedding_vector=json.dumps(embedding),
            )
            db.session.add(chunk)
            db.session.flush()  # flush 以获取自增 ID

            new_chunk_ids.append(chunk.id)
            new_vectors.append(embedding)
            count += 1

        db.session.commit()

        # 同步写入 FAISS 持久化索引
        if new_chunk_ids and new_vectors:
            faiss_store.add_vectors(new_chunk_ids, new_vectors)

        return count


# 全局实例
embedding_service = EmbeddingService()
