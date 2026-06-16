import os
import re
import math
import chromadb
from chromadb.utils import embedding_functions
import urllib.request
import urllib.error
import uuid

class HashEmbeddingFunction:
    def __init__(self, dim: int = 64):
        self.dim = dim

    def name(self):
        return "hash-embedding"

    def __call__(self, input):
        vectors = []
        for text in input:
            vec = [0.0] * self.dim
            tokens = [t for t in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", str(text).lower()) if t]
            for token in tokens:
                idx = hash(token) % self.dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

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
        self.client = chromadb.PersistentClient(path=db_path)
        
        mode = os.getenv("LITETUTOR_OFFLINE", "auto").strip().lower()
        force_offline = mode in {"1", "true", "yes", "offline"}
        force_online = mode in {"0", "false", "no", "online"}
        mode_label = "offline"
        if force_offline:
            self.embedding_fn = HashEmbeddingFunction()
        else:
            allow_online = force_online or _can_reach("https://huggingface.co")
            if allow_online:
                try:
                    self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )
                    mode_label = "online"
                except Exception:
                    self.embedding_fn = HashEmbeddingFunction()
            else:
                self.embedding_fn = HashEmbeddingFunction()
        print(f"[SYSTEM] Embedding mode: {mode_label}")
        
        # Create or load the collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn
        )
        print(f"[SUCCESS] Connected to collection: {collection_name}")

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
        metadatas = [{"source": file_path} for _ in range(len(chunks))]
        
        print(f"[PROCESS] Upserting {len(chunks)} chunks into ChromaDB...")
        self.collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        print("[SUCCESS] Ingestion complete!")

    def _tokenize(self, text: str):
        return [t for t in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if t]

    def _keyword_scores(self, query_text: str):
        all_docs = self.collection.get(include=["documents"]).get("documents", [])
        query_tokens = set(self._tokenize(query_text))
        scores = []
        for doc in all_docs:
            doc_tokens = set(self._tokenize(doc))
            score = len(query_tokens & doc_tokens)
            if score > 0:
                scores.append((doc, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def query_knowledge_chunks(self, query_text: str, n_results: int = 2):
        print(f"\n[SEARCH] Querying knowledge base for: '{query_text}'")
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            return results.get("documents", [[]])[0]
        except Exception as e:
            print(f"[SEARCH] query失败，降级到关键词搜索：{e}")
            # 降级：直接全量关键词匹配
            all_docs = self.collection.get(include=["documents"]).get("documents", [])
            tokens = set(re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", query_text.lower()))
            scored = []
            for doc in all_docs:
                doc_tokens = set(re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", doc.lower()))
                score = len(tokens & doc_tokens)
                if score > 0:
                    scored.append((doc, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [d for d, _ in scored[:n_results]]

    def query_knowledge_chunks_with_scores(self, query_text: str, n_results: int = 2):
        print(f"\n[SEARCH] Querying knowledge base for: '{query_text}'")
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=["documents", "distances"]
            )
            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            return documents, distances
        except Exception as e:
            print(f"[SEARCH] query失败，降级：{e}")
            docs = self.query_knowledge_chunks(query_text, n_results)
            return docs, [0.5] * len(docs)

    def query_knowledge(self, query_text: str, n_results: int = 2) -> str:
        chunks = self.query_knowledge_chunks(query_text, n_results)
        if not chunks:
            return "No relevant context found in the local knowledge base."
        return "\n---\n".join(chunks)

    def query_knowledge_hybrid(self, query_text: str, n_results: int = 2) -> str:
        vector_chunks = self.query_knowledge_chunks(query_text, n_results * 2)
        keyword_scores = self._keyword_scores(query_text)
        combined = {}
        for idx, doc in enumerate(vector_chunks):
            combined[doc] = combined.get(doc, 0) + (1.0 / (idx + 1))
        for rank, (doc, score) in enumerate(keyword_scores[: n_results * 4]):
            combined[doc] = combined.get(doc, 0) + score + (0.5 / (rank + 1))
        if not combined:
            return "No relevant context found in the local knowledge base."
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        top_docs = [doc for doc, _ in ranked[:n_results]]
        return "\n---\n".join(top_docs)

    def add_document(self, text: str, source: str = "uploaded") -> bool:
        """动态添加文档到知识库，返回False表示已存在"""
        import hashlib
        # 计算文档指纹
        fingerprint = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
        fp_id = f"__fingerprint__{source}"
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
            if len(current_chunk) + len(para) < 300:
                current_chunk += para + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        if not chunks:
            return
        ids = [f"{source}_{i}_{uuid.uuid4().hex[:6]}" for i in range(len(chunks))]
        self.collection.add(
            documents=chunks,
            ids=ids,
            metadatas=[{"source": source} for _ in chunks]
        )
        # 存入指纹标记
        try:
            self.collection.add(
                documents=[f"__fingerprint__{fingerprint}"],
                ids=[fp_id],
                metadatas=[{"source": source, "type": "fingerprint"}]
            )
        except Exception:
            pass
        print(f"[RAG] 已添加 {len(chunks)} 个chunk，来源：{source}")
        return True


    def list_sources(self) -> list:
        """列出知识库中所有文档来源"""
        try:
            results = self.collection.get(include=["metadatas"])
            sources = list({m.get("source", "unknown") for m in results["metadatas"]})
            return sources
        except Exception:
            return []

# Quick Local Test Block
if __name__ == "__main__":
    # 1. Initialize the RAG engine
    rag = LocalRAGKnowledgeBase()
    
    # 2. Let's create a dummy textbook file for testing
    dummy_file = "data_structure_notes.txt"
    with open(dummy_file, "w", encoding="utf-8") as f:
        f.write("KMP Algorithm Core Concept: KMP avoids redundant comparisons by utilizing a partial match table (next array) to skip characters safely during string matching.\n")
        f.write("Depth-First Search (DFS): A graph traversal algorithm that explores as far as possible along each branch before backtracking. It commonly uses a Stack data structure.\n")
        f.write("Big Data Principles: Hadoop uses HDFS for distributed storage and MapReduce for distributed processing of massive datasets.\n")
    
    # 3. Feed the textbook to the database
    rag.ingest_text_file(dummy_file)
    
    # 4. Pull the trigger (Test a search)
    question = "What data structure does DFS use?"
    retrieved_info = rag.query_knowledge(question)
    
    print("\n[RESULT] Retrieved Context:")
    print("========================================")
    print(retrieved_info)
    print("========================================")
