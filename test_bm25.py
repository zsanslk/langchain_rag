import jieba
from rank_bm25 import BM25Okapi

query = "周末双休吗"
corpus = [
    "康泰瑞行政及研发中心实行 周末双休 制度。标准办公时间为 09:00-18:00，支持 1 小时弹性浮动。",
    "员工人均综合年薪约 22-28 万元（含基本薪资、五险一金及科研/销售绩效）。公司设立了年度",
    "无关文档"
]

tokenized_corpus = [list(jieba.cut(c)) for c in corpus]
bm25 = BM25Okapi(tokenized_corpus)

tokenized_query = list(jieba.cut(query))
doc_scores = bm25.get_scores(tokenized_query)

print("Query tokens:", tokenized_query)
for i, tokens in enumerate(tokenized_corpus):
    print(f"Corpus {i} tokens:", tokens)

print("BM25 scores:", doc_scores)
