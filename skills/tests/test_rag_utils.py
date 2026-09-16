import sys
import types
import unittest
from pathlib import Path


# Keep the pure tokenizer/embedding tests runnable even when ChromaDB is absent.
try:
    import chromadb  # noqa: F401
except ImportError:
    chromadb = types.ModuleType("chromadb")
    chromadb_utils = types.ModuleType("chromadb.utils")
    chromadb_utils.embedding_functions = types.SimpleNamespace()
    sys.modules["chromadb"] = chromadb
    sys.modules["chromadb.utils"] = chromadb_utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag_builder import StableHashEmbeddingFunction, tokenise_for_retrieval


class RagUtilityTests(unittest.TestCase):
    def test_chinese_text_is_split_into_searchable_ngrams(self):
        tokens = tokenise_for_retrieval("深度优先搜索使用栈")
        self.assertIn("深度", tokens)
        self.assertIn("搜索", tokens)
        self.assertIn("栈", tokens)

    def test_offline_embedding_is_repeatable(self):
        embed = StableHashEmbeddingFunction(dim=256)
        first = embed(["KMP 字符串匹配"])[0]
        second = embed(["KMP 字符串匹配"])[0]
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)


if __name__ == "__main__":
    unittest.main()
