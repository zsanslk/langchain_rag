import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app
from services.retrieval_service import retrieval_service

app = create_app()
with app.app_context():
    query = '如何请假'
    print('Testing query:', query)
    
    from models.document import DocumentChunk
    count = DocumentChunk.query.count()
    print('Total chunks in DB:', count)
    
    if count > 0:
        results = retrieval_service.search_similar_chunks(query, top_k=5)
        print('Retrieval Results:')
        for r in results:
            print(f"- Score: {r['similarity']:.4f}, Content: {r['content'][:100]}...")
        if not results:
            print("No results returned. (Threshold might be filtering them out)")
