"""What a process pays before its first question.

Measured on 0.2.0rc17: `import nlp2sql` took about 3.2 s, about 2 s of it scikit-learn
(imported at module level for TF-IDF), and every warm connect() encoded the text
"warmup", a paid request with OpenAI embeddings.
"""

import subprocess
import sys
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest

from nlp2sql.adapters import local_embedding_adapter
from nlp2sql.ports.embedding_provider import EmbeddingProviderPort


def test_import_does_not_load_scikit_learn():
    code = "import sys, nlp2sql; print('sklearn' in sys.modules)"
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout

    assert output.strip() == "False"


class _RemoteEmbeddings(EmbeddingProviderPort):
    def __init__(self):
        self.encoded: List[List[str]] = []

    async def encode(self, texts: List[str]) -> np.ndarray:
        self.encoded.append(texts)
        return np.zeros((len(texts), 4))

    def get_embedding_dimension(self) -> int:
        return 4

    @property
    def provider_type(self) -> str:
        return "remote"


@pytest.mark.asyncio
async def test_default_warmup_sends_nothing():
    provider = _RemoteEmbeddings()

    await provider.warmup()

    assert provider.encoded == []


@pytest.mark.asyncio
async def test_local_warmup_loads_the_model(monkeypatch: pytest.MonkeyPatch):
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384
    sentence_transformer = MagicMock(return_value=model)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=sentence_transformer))
    monkeypatch.setattr(local_embedding_adapter, "_model_cache", {})

    adapter = local_embedding_adapter.LocalEmbeddingAdapter("test-model")
    await adapter.warmup()

    sentence_transformer.assert_called_once_with("test-model")
    assert adapter.get_embedding_dimension() == 384
    model.encode.assert_not_called()
