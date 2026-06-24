"""
双路混合检索服务 (Retrieval Service)
====================================
本模块对应论文第 5.3 节：《双路混合检索与加权融合算法》

核心职责：
1. 向量语义检索 (Dense Retrieval) — 基于 FAISS 持久化本地向量索引
2. BM25 关键词检索 (Sparse Retrieval)
3. 归一化与加权融合策略
4. 处理耗时统计 (用于论文表 6-2 延迟拆解分析)
"""

import time
import json
from concurrent.futures import ThreadPoolExecutor
from flask import current_app
from models import db
from models.document import DocumentChunk, Document
from services.embedding_service import embedding_service
from services.faiss_store import faiss_store

class RetrievalService:
    """检索服务：实现基于语义与关键词的双路混合检索"""

    def __init__(self):
        pass

    def search_similar_chunks(self, query, top_k=5, user_id=None):
        """
        混合检索主链路（对应论文5.3节：双异步线程扫描）
        """
        t_start = time.perf_counter()

        # 1. 获取所有状态为 completed 的切片（共享知识库模式）
        query_obj = db.session.query(DocumentChunk).join(
            DocumentChunk.document
        ).filter(
            Document.status == 'completed'
        )
        
        all_chunks = query_obj.all()
        if not all_chunks:
            print(f"[RetrievalService] 用户 {user_id} 暂无已处理完成的文档切片")
            return []

        # 如果 FAISS 索引尚未就绪，自动从数据库重建
        if not faiss_store.is_ready():
            print("[RetrievalService] FAISS 索引未就绪，触发自动重建...")
            faiss_store.rebuild_from_db()

        # 获取 query 的向量
        t_vec = time.perf_counter()
        query_vector = embedding_service.get_embedding(query)
        vec_ms = (time.perf_counter() - t_vec) * 1000

        vector_scores = {}
        bm25_scores = {}

        # 论文 5.3 节声明：同步开启两个异步线程进行检索
        def run_vector_search():
            """使用 FAISS 持久化索引进行向量语义检索"""
            nonlocal vector_scores
            try:
                vector_scores = faiss_store.search(query_vector)
            except Exception as e:
                print(f"[RetrievalService] 向量检索失败: {e}")
                vector_scores = {}

        def run_bm25_search():
            """执行 BM25 关键词检索"""
            nonlocal bm25_scores
            try:
                bm25_scores = self._bm25_search(query, all_chunks)
            except Exception as e:
                print(f"[RetrievalService] BM25 检索失败: {e}")
                bm25_scores = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_vec = executor.submit(run_vector_search)
            fut_bm25 = executor.submit(run_bm25_search)
            fut_vec.result()
            fut_bm25.result()

        # 4. 加权融合 (针对论文 5.3 节公式的优化修正)
        # 修正：避免 0.95 权重导致本已达标的 v_score 被压低到阈值以下
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0
        if max_bm25 == 0:
            max_bm25 = 1.0

        final_results = []
        similarity_threshold = current_app.config.get('SIMILARITY_THRESHOLD', 0.45) 

        for chunk in all_chunks:
            c_id = chunk.id
            v_score = vector_scores.get(c_id, 0.0)
            b_score = bm25_scores.get(c_id, 0.0)
            
            # 归一化 BM25
            normalized_bm25 = (b_score / max_bm25) * 0.05
            
            # 融合得分计算：保持向量得分比例，BM25 作为辅助增强
            # 这样如果 v_score 已经 > 0.45，就不会因为没有关键词匹配而被 0.95 降权导致过滤
            final_score = v_score + normalized_bm25
            
            # 相似度阈值过滤（论文 5.4 节防幻觉机制）
            if final_score < similarity_threshold:
                continue
            
            final_results.append({
                'chunk_id': chunk.id,
                'document_id': chunk.document_id,
                'chunk_index': chunk.chunk_index,
                'content': chunk.chunk_content,
                'similarity': min(final_score, 1.0), # 限制在 1.0 以内
                'vector_score': v_score,
                'bm25_score': b_score
            })

        # 5. 排序返回
        final_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        t_end = time.perf_counter()
        retrieval_ms = (t_end - t_start) * 1000 - vec_ms
        total_ms = (t_end - t_start) * 1000

        print(f"[RetrievalService] 混合检索完成 | 结果数: {len(final_results)} | 耗时: {total_ms:.1f}ms")

        return final_results[:top_k]

    def _bm25_search(self, query, chunks):
        """
        BM25 关键词检索
        """
        try:
            import jieba
            from rank_bm25 import BM25Okapi
        except ImportError:
            return {}

        tokenized_corpus = [list(jieba.cut(c.chunk_content)) for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        
        tokenized_query = list(jieba.cut(query))
        doc_scores = bm25.get_scores(tokenized_query)
        
        scores = {}
        for idx, score in enumerate(doc_scores):
            if score > 0:
                scores[chunks[idx].id] = score
        return scores

    @staticmethod
    def _cosine_similarity(vec_a, vec_b):
        """计算余弦相似度"""
        if len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)


# 全局实例
retrieval_service = RetrievalService()
