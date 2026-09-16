import os
import re
import math
import hashlib
from collections import Counter
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import urllib.request
from pathlib import Path

def tokenise_for_retrieval(text: str):
    """Tokenise English words and Chinese character n-grams.

    The previous regex treated an entire Chinese sentence as one token, which
    made both keyword search and offline embeddings unreliable.
    """
    parts = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", str(text).lower())
    tokens = []
    for part in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            tokens.extend(part)
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part)
    return [token for token in tokens if token]


def keyword_tokens_for_retrieval(text: str):
    """Use words and Chinese bigrams for lexical ranking (avoid noisy char hits)."""
    parts = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", str(text).lower())
    tokens = []
    for part in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) == 1:
                tokens.append(part)
            else:
                tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part)
    return tokens


class StableHashEmbeddingFunction:
    def __init__(self, dim: int = 256):
        self.dim = dim

    def name(self):
        return "stable-hash-embedding-v2"

    def __call__(self, input):
        vectors = []
        for text in input:
            vec = [0.0] * self.dim
            for token, count in Counter(tokenise_for_retrieval(text)).items():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign * (1.0 + math.log(count))
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    # Chroma 1.x calls these explicit methods; older releases call __call__.
    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self(input)

def _can_reach(url: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False

class LocalRAGKnowledgeBase:
    """
    Offline RAG Knowledge Base using ChromaDB.
    Ingests professional course materials (e.g., Big Data, Data Structures) 
    to eliminate LLM hallucinations.
    """
    def __init__(self, db_path="./chroma_db", collection_name="lite_tutor_kb"):
        print("[SYSTEM] Initializing Local Vector Database...")
        # Persist the database locally in the project folder
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection_name = collection_name
        
        mode = os.getenv("LITETUTOR_OFFLINE", "auto").strip().lower()
        force_offline = mode in {"1", "true", "yes", "offline"}
        force_online = mode in {"0", "false", "no", "online"}
        mode_label = "offline"
        self.using_stable_embedding = not force_online
        if force_offline or not force_online:
            self.embedding_fn = StableHashEmbeddingFunction()
        else:
            allow_online = _can_reach("https://huggingface.co")
            if allow_online:
                try:
                    self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )
                    mode_label = "online"
                    self.using_stable_embedding = False
                except Exception:
                    self.embedding_fn = StableHashEmbeddingFunction()
                    self.using_stable_embedding = True
            else:
                self.embedding_fn = StableHashEmbeddingFunction()
                self.using_stable_embedding = True
        print(f"[SYSTEM] Embedding mode: {mode_label}")
        
        # Create or load the collection
        try:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"知识库 {self.db_path} 与当前 ChromaDB 版本不兼容。"
                "请先备份该目录，再将其移走后重新启动。"
            ) from exc
        if self.using_stable_embedding:
            self._migrate_legacy_embeddings()
        self._repair_legacy_metadata()
        print(f"[SUCCESS] Connected to collection: {collection_name}")

    def close(self):
        """Release ChromaDB resources, mainly for tests and orderly shutdown."""
        system = getattr(self.client, "_system", None)
        stop = getattr(system, "stop", None)
        if callable(stop):
            stop()
        try:
            from chromadb.api.client import SharedSystemClient

            SharedSystemClient.clear_system_cache()
        except (ImportError, AttributeError):
            pass

    def _migrate_legacy_embeddings(self):
        """Re-embed legacy chunks once so old salted hash vectors do not linger."""
        metadata = self.collection.metadata or {}
        if metadata.get("embedding_version") == "stable-hash-v3":
            return
        snapshot = self.collection.get(include=["documents", "metadatas"])
        ids = snapshot.get("ids", [])
        documents = snapshot.get("documents", [])
        metadatas = snapshot.get("metadatas", [])
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"embedding_version": "stable-hash-v3"},
        )
        if ids and documents:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"[RAG] 已迁移 {len(ids)} 个旧向量到稳定离线嵌入")

    def _repair_legacy_metadata(self):
        snapshot = self.collection.get(include=["documents", "metadatas"])
        changed_ids = []
        changed_metadatas = []
        for item_id, document, metadata in zip(
            snapshot.get("ids", []),
            snapshot.get("documents", []),
            snapshot.get("metadatas", []),
        ):
            repaired = dict(metadata or {})
            if str(document).startswith("__fingerprint__"):
                repaired["type"] = "fingerprint"
            else:
                repaired.setdefault("type", "content")
                page_match = re.search(r"【第(\d+)页】", str(document))
                if page_match:
                    repaired.setdefault("page", int(page_match.group(1)))
            if repaired != (metadata or {}):
                changed_ids.append(item_id)
                changed_metadatas.append(repaired)
        if changed_ids:
            self.collection.update(ids=changed_ids, metadatas=changed_metadatas)
            print(f"[RAG] 已补全 {len(changed_ids)} 个旧数据来源标记")

    def ingest_text_file(self, file_path: str, chunk_size: int = 500):
        """Reads a text file, chunks it, and upserts to the vector database."""
        if not os.path.exists(file_path):
            print(f"[ERROR] File not found: {file_path}")
            return
            
        print(f"\n[PROCESS] Reading and chunking {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
            
        # Simple chunking strategy (splitting by paragraphs/length)
        # In a real scenario, you'd use LangChain's RecursiveCharacterTextSplitter
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        ids = [f"{os.path.basename(file_path)}_chunk_{i}" for i in range(len(chunks))]
        source_name = Path(file_path).name
        metadatas = [
            {"source": source_name, "type": "content"}
            for _ in range(len(chunks))
        ]
        
        print(f"[PROCESS] Upserting {len(chunks)} chunks into ChromaDB...")
        self.collection.upsert(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        print("[SUCCESS] Ingestion complete!")

    def _tokenize(self, text: str):
        return tokenise_for_retrieval(text)

    def _keyword_scores(self, query_text: str):
        result = self.collection.get(include=["documents", "metadatas"])
        all_docs = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        query_tokens = set(keyword_tokens_for_retrieval(query_text))
        searchable = [
            (doc, metadata or {})
            for doc, metadata in zip(all_docs, metadatas)
            if (metadata or {}).get("type") != "fingerprint"
        ]
        doc_token_sets = [set(keyword_tokens_for_retrieval(doc)) for doc, _ in searchable]
        doc_frequency = Counter(
            token for tokens in doc_token_sets for token in (query_tokens & tokens)
        )
        document_count = max(1, len(searchable))
        scores = []
        for (doc, metadata), doc_tokens in zip(searchable, doc_token_sets):
            matched = query_tokens & doc_tokens
            score = sum(
                math.log((document_count + 1) / (doc_frequency[token] + 1)) + 1
                for token in matched
            )
            # Exact Latin identifiers (KMP, SQL, DFS, API...) are usually the
            # strongest intent signal in mixed Chinese/English course queries.
            score += 15.0 * sum(
                1 for token in matched if re.fullmatch(r"[a-z0-9]+", token)
            )
            if score > 0:
                scores.append((doc, score, metadata))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def keyword_confidence(self, query_text: str) -> float:
        """Map the strongest lexical match to a bounded confidence score."""
        scores = self._keyword_scores(query_text)
        if not scores:
            return 0.0
        return 1.0 - math.exp(-scores[0][1] / 5.0)

    def query_knowledge_chunks(self, query_text: str, n_results: int = 2):
        print(f"\n[SEARCH] Querying knowledge base for: '{query_text}'")
        try:
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(max(n_results * 2, n_results), count),
                include=["documents", "metadatas"],
            )
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            return [
                doc for doc, metadata in zip(documents, metadatas)
                if (metadata or {}).get("type") != "fingerprint"
            ][:n_results]
        except Exception as e:
            print(f"[SEARCH] query失败，降级到关键词搜索：{e}")
            # 降级：直接全量关键词匹配
            result = self.collection.get(include=["documents", "metadatas"])
            all_docs = result.get("documents", [])
            metadatas = result.get("metadatas", [])
            tokens = set(self._tokenize(query_text))
            scored = []
            for doc, metadata in zip(all_docs, metadatas):
                if (metadata or {}).get("type") == "fingerprint":
                    continue
                doc_tokens = set(self._tokenize(doc))
                score = len(tokens & doc_tokens)
                if score > 0:
                    scored.append((doc, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [d for d, _ in scored[:n_results]]

    def query_knowledge_chunks_with_scores(self, query_text: str, n_results: int = 2):
        print(f"\n[SEARCH] Querying knowledge base for: '{query_text}'")
        try:
            count = self.collection.count()
            if count == 0:
                return [], [], []
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(max(n_results * 2, n_results), count),
                include=["documents", "distances", "metadatas"]
            )
            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            filtered = [
                (doc, distance, metadata or {})
                for doc, distance, metadata in zip(documents, distances, metadatas)
                if (metadata or {}).get("type") != "fingerprint"
            ][:n_results]
            return (
                [item[0] for item in filtered],
                [item[1] for item in filtered],
                [item[2] for item in filtered],
            )
        except Exception as e:
            print(f"[SEARCH] query失败，降级：{e}")
            docs = self.query_knowledge_chunks(query_text, n_results)
            return docs, [0.5] * len(docs), [{} for _ in docs]

    def query_knowledge(self, query_text: str, n_results: int = 2) -> str:
        chunks = self.query_knowledge_chunks(query_text, n_results)
        if not chunks:
            return ""
        return "\n---\n".join(chunks)

    def query_knowledge_hybrid(self, query_text: str, n_results: int = 2) -> str:
        ranked = self.query_knowledge_hybrid_with_metadata(query_text, n_results)
        if not ranked:
            return ""
        return "\n---\n".join(doc for doc, _ in ranked)

    def query_knowledge_hybrid_with_metadata(self, query_text: str, n_results: int = 2):
        vector_chunks, _, vector_metadatas = self.query_knowledge_chunks_with_scores(
            query_text, n_results * 2
        )
        keyword_scores = self._keyword_scores(query_text)
        combined = {}
        metadata_by_doc = {}
        for idx, (doc, metadata) in enumerate(zip(vector_chunks, vector_metadatas)):
            combined[doc] = combined.get(doc, 0) + (1.0 / (idx + 1))
            metadata_by_doc[doc] = metadata
        for rank, (doc, score, metadata) in enumerate(keyword_scores[: n_results * 4]):
            combined[doc] = combined.get(doc, 0) + score + (0.5 / (rank + 1))
            metadata_by_doc[doc] = metadata
        if not combined:
            return []
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        return [(doc, metadata_by_doc.get(doc, {})) for doc, _ in ranked[:n_results]]

    def add_document(self, text: str, source: str = "uploaded") -> bool:
        """动态添加文档到知识库，返回False表示已存在"""
        # 计算文档指纹
        fingerprint = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
        fp_id = f"__fingerprint__{fingerprint}"
        # 检查是否已存在
        try:
            existing = self.collection.get(ids=[fp_id])
            if existing and existing.get("ids"):
                print(f"[RAG] 文档已存在，跳过：{source}")
                return False
        except Exception:
            pass
        chunks = []
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
        current_chunk = ""
        for para in paragraphs:
            starts_new_page = bool(re.match(r"【第\d+页】", para))
            if starts_new_page and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            if len(para) > 600:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.extend(para[i:i + 600] for i in range(0, len(para), 600))
            elif len(current_chunk) + len(para) < 600:
                current_chunk += para + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        if not chunks:
            return False
        source_hash = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
        ids = [f"{source_hash}_{fingerprint}_{i}" for i in range(len(chunks))]
        metadatas = []
        for chunk in chunks:
            page_match = re.search(r"【第(\d+)页】", chunk)
            metadata = {"source": source, "fingerprint": fingerprint, "type": "content"}
            if page_match:
                metadata["page"] = int(page_match.group(1))
            metadatas.append(metadata)
        self.collection.add(
            documents=chunks,
            ids=ids,
            metadatas=metadatas
        )
        # 存入指纹标记
        try:
            self.collection.add(
                documents=[f"__fingerprint__{fingerprint}"],
                ids=[fp_id],
                metadatas=[{"source": source, "fingerprint": fingerprint, "type": "fingerprint"}]
            )
        except Exception:
            pass
        print(f"[RAG] 已添加 {len(chunks)} 个chunk，来源：{source}")
        return True
    def list_sources(self) -> list:
        """列出知识库中所有文档来源"""
        try:
            results = self.collection.get(include=["metadatas"])
            sources = list({
                m.get("source", "unknown")
                for m in results["metadatas"]
                if m.get("type") != "fingerprint"
            })
            return sources
        except Exception:
            return []
