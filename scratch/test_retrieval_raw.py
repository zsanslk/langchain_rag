import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app
from services.retrieval_service import retrieval_service

app = create_app()
with app.app_context():
    query = '如何请假'
    print('Testing query:', query)
    
    from models.document import DocumentChunk
    
    # We will manually do what search_similar_chunks does, but print raw scores
    xq = retrieval_service.embedding_service.get_embedding(query)
    chunks = DocumentChunk.query.all()
    
    from services.retrieval_service import np
    
    chunk_texts = [c.chunk_content for c in chunks]
    
    # BM25 scores
    import jieba
    from rank_bm25 import BM25Okapi
    tokenized_corpus = [list(jieba.cut(doc)) for doc in chunk_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = list(jieba.cut(query))
    bm25_scores = bm25.get_scores(tokenized_query)
    
    max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 else 0
    if max_bm25 == 0: max_bm25 = 1.0
    
    print(f"Max BM25 score: {max_bm25}")
    
    # Vector scores
    best_chunk = None
    best_score = -1
    
    for i, c in enumerate(chunks):
        v = c.embedding_vector
        if not v: continue
        # dot product
        v_score = sum(x*y for x,y in zip(xq, v))
        
        normalized_bm25 = bm25_scores[i] / max_bm25
        final_score = 0.95 * v_score + 0.05 * normalized_bm25
        
        if final_score > best_score:
            best_score = final_score
            best_chunk = c
            
    print(f"Highest fused score: {best_score:.4f}")
    if best_chunk:
        print(f"Content: {best_chunk.chunk_content[:100]}...")
