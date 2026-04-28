"""BM25 关键词检索通道 — 自包含实现，无外部依赖。"""

from __future__ import annotations

import math
import re
from collections import Counter

from packages.common import get_logger

log = get_logger("retrieval.keyword")


class BM25Scorer:
    """
    内置 BM25 实现，支持内存模式。

    在构建索引后，对查询文本进行 BM25 评分。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._corpus: list[dict] = []
        self._doc_freqs: Counter = Counter()
        self._avg_dl: float = 0.0
        self._n_docs: int = 0

    def build_index(self, chunks: list[dict]) -> None:
        """
        从 chunk 列表构建 BM25 索引。

        chunks: list of {chunk_id: str, doc_id: str, content: str}
        """
        self._corpus = []
        self._doc_freqs = Counter()
        total_length = 0

        for chunk in chunks:
            tokens = self._tokenize(chunk["content"])
            entry = {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "content": chunk["content"],
                "tokens": tokens,
                "length": len(tokens),
            }
            self._corpus.append(entry)
            total_length += len(tokens)

            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._doc_freqs[token] += 1

        self._n_docs = len(self._corpus)
        self._avg_dl = total_length / self._n_docs if self._n_docs > 0 else 1.0
        log.info("bm25_index_built", n_docs=self._n_docs, vocab_size=len(self._doc_freqs))

    def add_chunks(self, chunks: list[dict]) -> None:
        """增量添加文档到索引（入库时调用）。"""
        for chunk in chunks:
            tokens = self._tokenize(chunk["content"])
            entry = {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "content": chunk["content"],
                "tokens": tokens,
                "length": len(tokens),
            }
            self._corpus.append(entry)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._doc_freqs[token] += 1

        self._n_docs = len(self._corpus)
        total_length = sum(e["length"] for e in self._corpus)
        self._avg_dl = total_length / self._n_docs if self._n_docs > 0 else 1.0

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        对查询进行 BM25 评分，返回 top_k 结果。

        Returns: list of {chunk_id, doc_id, content, score}（score 归一化到 [0,1]）
        """
        if not self._corpus:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = []
        for entry in self._corpus:
            score = self._compute_bm25(query_tokens, entry)
            if score > 0:
                scores.append({
                    "chunk_id": entry["chunk_id"],
                    "doc_id": entry["doc_id"],
                    "content": entry["content"],
                    "score": score,
                })

        scores.sort(key=lambda x: x["score"], reverse=True)

        # 归一化到 [0, 1]
        if scores:
            max_score = scores[0]["score"]
            if max_score > 0:
                for s in scores:
                    s["score"] = s["score"] / max_score

        return scores[:top_k]

    def _compute_bm25(self, query_tokens: list[str], entry: dict) -> float:
        """计算单文档的 BM25 分数。"""
        doc_tokens = entry["tokens"]
        dl = entry["length"]
        tf_map = Counter(doc_tokens)
        score = 0.0

        for term in query_tokens:
            if term not in self._doc_freqs:
                continue
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            df = self._doc_freqs[term]
            idf = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1)
            tf_norm = (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * dl / self._avg_dl)
            )
            score += idf * tf_norm

        return score

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        中英文混合分词：英文按纯字母单词，中文按 bigram + 单字。
        """
        tokens = []

        # 提取纯英文单词（至少2个字母）
        english_words = re.findall(r"[a-zA-Z]{2,}", text.lower())
        tokens.extend(english_words)

        # 提取中文 bigram
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        # 单字也加入（保证单字关键词可匹配）
        tokens.extend(chinese_chars)

        return tokens
