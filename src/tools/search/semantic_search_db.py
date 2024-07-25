import os
import pickle
import sqlite3
import struct
from typing import Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from tqdm import tqdm

from src.common.embedding import EmbeddingModel
from config.globals import embedding_model
from src.tools.search.local_search_api import LocalSearchAPI
from src.common.results import SearchResult


class SemanticSearchDB(LocalSearchAPI):
    def __init__(self, db_file_path: str | Path, **kwargs):
        super().__init__(**kwargs)
        self.is_free = True
        self.db_file_path = db_file_path
        self.embedding_model = None
        if not os.path.exists(self.db_file_path):
            print(f"Warning: No {self.name} database found at '{self.db_file_path}'. Creating new one.")
        os.makedirs(os.path.dirname(self.db_file_path), exist_ok=True)
        self.db = sqlite3.connect(self.db_file_path, uri=True)
        self.cur = self.db.cursor()

    def is_empty(self) -> bool:
        """Returns True iff the database is empty."""
        raise NotImplementedError

    def _embed(self, *args, **kwargs):
        if self.embedding_model is None:
            self._setup_embedding_model()
        return self.embedding_model.embed(*args, **kwargs)

    def _embed_many(self, *args, **kwargs):
        if self.embedding_model is None:
            self._setup_embedding_model()
        return self.embedding_model.embed_many(*args, **kwargs)

    def _setup_embedding_model(self):
        self.embedding_model = EmbeddingModel(embedding_model)

    def _restore_knn_from(self, path: str) -> NearestNeighbors:
        with open(path, "rb") as f:
            return pickle.load(f)

    def _run_sql_query(self, stmt: str, *args) -> Sequence:
        """Runs the SQL statement stmt (with optional arguments) on the DB and returns the rows."""
        self.cur.execute(stmt, args)
        rows = self.cur.fetchall()
        return rows

    def _call_api(self, query: str, limit: int) -> list[SearchResult]:
        query_embedding = self._embed(query).reshape(1, -1)
        indices = self._search_semantically(query_embedding, limit)
        return self._indices_to_search_results(indices, query)

    def _search_semantically(self, query_embedding, limit: int) -> list[int]:
        """Runs a semantic search using kNN. Returns the indices (starting at 0)
        of the search results."""
        raise NotImplementedError()

    def retrieve(self, idx: int) -> (str, str, datetime):
        """Selects the row with specified index from the DB and returns the URL, the text
        and the date of the selected row's source."""
        raise NotImplementedError()

    def _indices_to_search_results(self, indices: list[int], query: str) -> list[SearchResult]:
        results = []
        for i, index in enumerate(indices):
            url, text, date = self.retrieve(index)
            result = SearchResult(
                source=url,
                text=text,
                query=query,
                rank=i,
                date=date
            )
            results.append(result)
        return results

    def _build_db(self, **kwargs) -> None:
        """Creates the SQLite database."""
        raise NotImplementedError()


def df_embedding_to_np_embedding(df: pd.DataFrame, dimension: int) -> np.array:
    """Converts a Pandas DataFrame of binary embeddings into the respective
    NumPy array with shape (num_instances, dimension) containing the unpacked embeddings."""
    embeddings = np.zeros(shape=(len(df), dimension), dtype="float32")
    for i, embedding in enumerate(tqdm(df)):
        if embedding is not None:
            embeddings[i] = struct.unpack(f"{dimension}f", embedding)
        else:
            embeddings[i] = 1000  # Put invalid "embeddings" far away
    return embeddings
