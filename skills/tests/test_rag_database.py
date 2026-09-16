import tempfile
import unittest


try:
    import chromadb  # noqa: F401
except ImportError:
    chromadb = None


@unittest.skipIf(chromadb is None, "ChromaDB is not installed")
class RagDatabaseTests(unittest.TestCase):
    def test_fresh_database_can_ingest_and_retrieve(self):
        from rag_builder import LocalRAGKnowledgeBase

        with tempfile.TemporaryDirectory(prefix="litetutor-rag-test-") as db_dir:
            rag = LocalRAGKnowledgeBase(db_path=db_dir)
            try:
                text = (
                    "KMP 字符串匹配算法通过部分匹配表避免重复比较，"
                    "适合在长文本中查找模式串。"
                )
                self.assertTrue(rag.add_document(text, source="kmp-notes.txt"))
                self.assertFalse(rag.add_document(text, source="kmp-notes.txt"))

                results = rag.query_knowledge_hybrid_with_metadata("KMP是什么", n_results=2)
                self.assertTrue(results)
                self.assertIn("KMP", results[0][0])
                self.assertEqual(results[0][1].get("source"), "kmp-notes.txt")
            finally:
                rag.close()


if __name__ == "__main__":
    unittest.main()
