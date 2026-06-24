"""
FAISS 持久化向量索引管理服务 (FaissStore)
==========================================
本模块对应论文第 5.3 节：《基于 FAISS 的本地向量索引持久化》

核心职责：
1. 管理 FAISS IndexFlatIP 索引文件 (vector.index) 的读写
2. 维护 FAISS 内部行号 → chunk_id 的双向映射 (id_map.json)
3. 提供向量的增删查接口
4. 首次启动时自动从 MySQL 迁移构建索引

索引目录：local_models/vec_model/
"""

import os
import json
import threading
import numpy as np
import faiss


class FaissStore:
    """FAISS 本地持久化向量索引管理器"""

    def __init__(self, index_dir=None):
        """
        初始化 FAISS 索引管理器

        Args:
            index_dir: 索引文件存放目录，默认为项目根目录下的 local_models/vec_model/
        """
        if index_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            index_dir = os.path.join(base_dir, 'local_models', 'vec_model')

        self.index_dir = index_dir
        self.index_path = os.path.join(index_dir, 'vector.index')
        self.id_map_path = os.path.join(index_dir, 'id_map.json')

        self.index = None          # faiss.IndexFlatIP 实例
        self.id_map = []           # list[int]，位置 i 对应 FAISS 内部第 i 行的 chunk_id
        self.dimension = 768       # text2vec-base-chinese 输出维度

        self._lock = threading.Lock()  # 保证多线程安全

        # 确保目录存在
        os.makedirs(self.index_dir, exist_ok=True)

        # 尝试加载已有索引
        self._load()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def add_vectors(self, chunk_ids, vectors):
        """
        向索引中追加向量并持久化到磁盘

        Args:
            chunk_ids: list[int]，与 vectors 一一对应的 chunk 主键 ID
            vectors:   list[list[float]]，每条为 768 维向量
        """
        if not chunk_ids or not vectors:
            return

        with self._lock:
            xb = np.array(vectors, dtype='float32')
            faiss.normalize_L2(xb)

            if self.index is None:
                self.dimension = xb.shape[1]
                self.index = faiss.IndexFlatIP(self.dimension)
                self.id_map = []

            self.index.add(xb)
            self.id_map.extend(chunk_ids)
            self._save()

        print(f"[FaissStore] 追加 {len(chunk_ids)} 条向量，索引总量: {self.index.ntotal}")

    def remove_vectors(self, chunk_ids_to_remove):
        """
        从索引中移除指定 chunk_id 对应的向量，重建索引并持久化

        Args:
            chunk_ids_to_remove: list[int] 或 set[int]，要移除的 chunk_id 集合
        """
        if not chunk_ids_to_remove or self.index is None or self.index.ntotal == 0:
            return

        remove_set = set(chunk_ids_to_remove)

        with self._lock:
            # 找出要保留的行
            keep_indices = [i for i, cid in enumerate(self.id_map) if cid not in remove_set]

            if not keep_indices:
                # 全部删光了，重置为空索引
                self.index = faiss.IndexFlatIP(self.dimension)
                self.id_map = []
                self._save()
                print(f"[FaissStore] 索引已清空")
                return

            # 从旧索引中提取要保留的向量
            all_vectors = faiss.rev_swig_ptr(self.index.get_xb(), self.index.ntotal * self.dimension)
            all_vectors = np.array(all_vectors, dtype='float32').reshape(self.index.ntotal, self.dimension)

            keep_vectors = all_vectors[keep_indices]
            keep_ids = [self.id_map[i] for i in keep_indices]

            # 重建索引
            new_index = faiss.IndexFlatIP(self.dimension)
            new_index.add(keep_vectors)

            self.index = new_index
            self.id_map = keep_ids
            self._save()

        removed_count = len(chunk_ids_to_remove)
        print(f"[FaissStore] 移除 {removed_count} 条向量，索引剩余: {self.index.ntotal}")

    def search(self, query_vector, top_k=None):
        """
        在 FAISS 索引中执行近邻搜索

        Args:
            query_vector: list[float]，查询向量 (768 维)
            top_k:        返回前 K 个结果，默认返回全部

        Returns:
            dict[int, float]: {chunk_id: similarity_score}，得分从高到低
        """
        if self.index is None or self.index.ntotal == 0:
            return {}

        if top_k is None:
            top_k = self.index.ntotal
        # 转为C++可识别的类型
        xq = np.array([query_vector], dtype='float32')
        # 进行L2 归一化，方便计算相似度 内积=余弦相似度
        faiss.normalize_L2(xq)
        # 防止崩溃，当查询的数量大于索引的数量时取min
        k = min(top_k, self.index.ntotal)
        # 搜索最近的k个向量,进行点积运算（就是在计算余弦相似度）
        D, I = self.index.search(xq, k)

        scores = {}
        # 查出FAISS中I（索引）所对应的行号，并取出对应的相似度
        for i in range(k):
            idx = I[0][i]
            # 防止崩溃，如果查出的索引超出了id_map的长度
            if 0 <= idx < len(self.id_map):
                scores[self.id_map[idx]] = float(D[0][i])

        return scores

    def rebuild_from_db(self):
        """
        从 MySQL 全量数据重建 FAISS 索引（迁移/恢复用）

        需要在 Flask 应用上下文中调用
        """
        from models import db
        from models.document import DocumentChunk, Document

        try:
            print("[FaissStore] 正在从数据库全量重建 FAISS 索引...")
            query_obj = db.session.query(DocumentChunk).join(
                DocumentChunk.document
            ).filter(Document.status == 'completed')
            all_chunks = query_obj.all()

            if not all_chunks:
                print("[FaissStore] 数据库中无已完成的文档切片，创建空索引")
                with self._lock:
                    self.index = faiss.IndexFlatIP(self.dimension)
                    self.id_map = []
                    self._save()
                return

            chunk_ids = []
            vectors = []

            for chunk in all_chunks:
                try:
                    vec = json.loads(chunk.embedding_vector) if isinstance(chunk.embedding_vector, str) else chunk.embedding_vector
                    if vec and len(vec) == self.dimension:
                        vectors.append(vec)
                        chunk_ids.append(chunk.id)
                except Exception:
                    continue

            if not vectors:
                print("[FaissStore] 数据库中没有有效的向量数据，创建空索引")
                with self._lock:
                    self.index = faiss.IndexFlatIP(self.dimension)
                    self.id_map = []
                    self._save()
                return

            xb = np.array(vectors, dtype='float32')
            faiss.normalize_L2(xb)

            with self._lock:
                self.index = faiss.IndexFlatIP(self.dimension)
                self.index.add(xb)
                self.id_map = chunk_ids
                self._save()

            print(f"[FaissStore] 从数据库重建完成，共索引 {len(chunk_ids)} 条向量")
        except Exception as e:
            print(f"[FaissStore] 从数据库重建索引失败: {e}")
            import traceback
            traceback.print_exc()

    def is_ready(self):
        """检查索引是否已加载且可用"""
        return self.index is not None and self.index.ntotal > 0

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _save(self):
        """将索引和映射表持久化到磁盘
        
        注意：FAISS C++ 层在 Windows 上不支持路径中包含非 ASCII 字符（如中文），
        因此先写到临时文件再移动到目标路径。
        """
        import shutil
        import tempfile

        if self.index is not None:
            # 先写到系统临时目录（纯 ASCII 路径），再复制到目标位置
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.index')
            os.close(tmp_fd)
            try:
                faiss.write_index(self.index, tmp_path)
                shutil.move(tmp_path, self.index_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

        with open(self.id_map_path, 'w', encoding='utf-8') as f:
            json.dump(self.id_map, f)

        print(f"[FaissStore] 索引已保存到 {self.index_path} (共 {self.index.ntotal if self.index else 0} 条)")

    def _load(self):
        """从磁盘加载索引和映射表
        
        注意：FAISS C++ 层在 Windows 上不支持路径中包含非 ASCII 字符，
        因此先复制到临时文件再读取。
        """
        import shutil
        import tempfile

        if os.path.exists(self.index_path) and os.path.exists(self.id_map_path):
            try:
                # 复制到临时目录（纯 ASCII 路径）后读取
                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.index')
                os.close(tmp_fd)
                shutil.copy2(self.index_path, tmp_path)
                self.index = faiss.read_index(tmp_path)
                os.remove(tmp_path)

                with open(self.id_map_path, 'r', encoding='utf-8') as f:
                    self.id_map = json.load(f)

                if self.index.ntotal > 0:
                    self.dimension = self.index.d

                print(f"[FaissStore] 索引加载成功 | 路径: {self.index_path} | 向量数: {self.index.ntotal}")
            except Exception as e:
                print(f"[FaissStore] 索引加载失败: {e}，将在首次使用时重建")
                import traceback
                traceback.print_exc()
                self.index = None
                self.id_map = []
        else:
            print(f"[FaissStore] 未找到已有索引文件，将在首次使用时从数据库重建")


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------
faiss_store = FaissStore()
