"""Adaptive Event Memory module for operator-validated spacecraft operational patterns."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from astra.features.event_signature import EventSignature


@dataclass
class MemoryRecord:
    """Stored record in Adaptive Event Memory."""

    memory_id: str
    source_event_id: str
    event_timestamp: str
    operator_label: str
    affected_channels: list[str]
    feature_signature: dict[str, Any]
    feature_vector: list[float]
    creation_timestamp: str


@dataclass
class MemoryMatchResult:
    """Result of querying Adaptive Event Memory for a candidate signature."""

    classification: str  # "KNOWN_OPERATIONAL_PATTERN" or "UNKNOWN_UNUSUAL_EVENT"
    best_similarity: float
    nearest_memory: MemoryRecord | None
    matched_memory_id: str | None
    explanation: str


class AdaptiveEventMemory:
    """SQLite-backed Adaptive Event Memory for learning operator-validated rare nominal patterns."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        similarity_threshold: float = 0.80,
    ) -> None:
        self.db_path = str(db_path)
        self.similarity_threshold = float(similarity_threshold)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_memories (
                memory_id TEXT PRIMARY KEY,
                source_event_id TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                operator_label TEXT NOT NULL,
                affected_channels TEXT NOT NULL,
                feature_signature_json TEXT NOT NULL,
                feature_vector_json TEXT NOT NULL,
                creation_timestamp TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def store_memory(
        self,
        signature: EventSignature,
        operator_label: str = "VALID_OPERATION",
        memory_id: str | None = None,
    ) -> MemoryRecord:
        """Store an operator-validated event signature into memory."""
        if operator_label not in {"VALID_OPERATION", "CONFIRMED_ANOMALY"}:
            raise ValueError(f"Invalid operator_label: {operator_label}")

        now_iso = datetime.now(UTC).isoformat()
        mem_id = memory_id or f"mem_{signature.event_id}_{int(datetime.now().timestamp()*1000)}"

        record = MemoryRecord(
            memory_id=mem_id,
            source_event_id=signature.event_id,
            event_timestamp=signature.start_timestamp,
            operator_label=operator_label,
            affected_channels=signature.affected_channels,
            feature_signature=signature.to_dict(),
            feature_vector=signature.feature_vector,
            creation_timestamp=now_iso,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO event_memories (
                    memory_id, source_event_id, event_timestamp, operator_label,
                    affected_channels, feature_signature_json, feature_vector_json, creation_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.memory_id,
                    record.source_event_id,
                    record.event_timestamp,
                    record.operator_label,
                    json.dumps(record.affected_channels),
                    json.dumps(record.feature_signature),
                    json.dumps(record.feature_vector),
                    record.creation_timestamp,
                ),
            )
            conn.commit()

        return record

    def list_memories(self, label_filter: str | None = "VALID_OPERATION") -> list[MemoryRecord]:
        """List stored memories, optionally filtered by operator label."""
        query = "SELECT * FROM event_memories"
        params: list[Any] = []
        if label_filter:
            query += " WHERE operator_label = ?"
            params.append(label_filter)
        query += " ORDER BY creation_timestamp ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        records = []
        for r in rows:
            records.append(
                MemoryRecord(
                    memory_id=r["memory_id"],
                    source_event_id=r["source_event_id"],
                    event_timestamp=r["event_timestamp"],
                    operator_label=r["operator_label"],
                    affected_channels=json.loads(r["affected_channels"]),
                    feature_signature=json.loads(r["feature_signature_json"]),
                    feature_vector=json.loads(r["feature_vector_json"]),
                    creation_timestamp=r["creation_timestamp"],
                )
            )
        return records

    def compute_similarity(self, sig1: EventSignature, mem_record: MemoryRecord) -> float:
        """Compute similarity between a candidate signature and a stored memory record."""
        # Check telemetry max anomaly score discrepancy
        cand_score_max = sig1.telemetry_features.get("agg_score_max", 0.0)
        mem_score_max = mem_record.feature_signature.get("telemetry_features", {}).get("agg_score_max", 0.0)

        # If candidate anomaly score exceeds nominal memory score significantly, prevent false suppression
        if cand_score_max > 3.5 and (mem_score_max < 2.5 or cand_score_max > 2.0 * mem_score_max):
            return 0.0

        # 1. Cosine similarity of feature vectors
        v1 = np.asarray(sig1.feature_vector, dtype=np.float64)
        v2 = np.asarray(mem_record.feature_vector, dtype=np.float64)

        if len(v1) == len(v2) and len(v1) > 0:
            # Standardize feature vectors by absolute max to prevent feature scale domination
            std1 = np.abs(v1) + 1e-6
            std2 = np.abs(v2) + 1e-6
            scale = np.maximum(std1, std2)
            
            norm_v1 = v1 / scale
            norm_v2 = v2 / scale
            
            dot = float(np.dot(norm_v1, norm_v2))
            n1 = float(np.linalg.norm(norm_v1))
            n2 = float(np.linalg.norm(norm_v2))
            cos_sim = (dot / (n1 * n2)) if (n1 > 0 and n2 > 0) else 0.0
        else:
            cos_sim = 0.0

        # 2. Jaccard similarity of affected channels
        ch1 = set(sig1.affected_channels)
        ch2 = set(mem_record.affected_channels)
        jaccard_ch = len(ch1.intersection(ch2)) / len(ch1.union(ch2)) if ch1 or ch2 else 1.0

        # 3. Context similarity (nearest command time diff & 5m command count proximity)
        ctx1 = sig1.context_features
        ctx2 = mem_record.feature_signature.get("context_features", {})
        diff1 = ctx1.get("nearest_tc_diff_sec", 86400.0)
        diff2 = ctx2.get("nearest_tc_diff_sec", 86400.0)

        # Proximity in command diff log scale
        tc_diff_sim = float(np.exp(-abs(np.log1p(diff1) - np.log1p(diff2))))
        
        # Command count within 5 minutes proximity
        cnt1 = ctx1.get("tc_count_5m", 0.0)
        cnt2 = ctx2.get("tc_count_5m", 0.0)
        cnt_sim = float(np.exp(-abs(cnt1 - cnt2) / 5.0))

        # Weighted combination
        total_sim = 0.40 * max(0.0, cos_sim) + 0.20 * jaccard_ch + 0.20 * tc_diff_sim + 0.20 * cnt_sim
        return float(np.clip(total_sim, 0.0, 1.0))

    def query(self, candidate_signature: EventSignature) -> MemoryMatchResult:
        """Query memory for matches against valid operational patterns."""
        valid_memories = self.list_memories(label_filter="VALID_OPERATION")
        if not valid_memories:
            return MemoryMatchResult(
                classification="UNKNOWN_UNUSUAL_EVENT",
                best_similarity=0.0,
                nearest_memory=None,
                matched_memory_id=None,
                explanation="No operator-validated operational patterns stored in memory.",
            )

        best_sim = -1.0
        best_mem: MemoryRecord | None = None

        for mem in valid_memories:
            sim = self.compute_similarity(candidate_signature, mem)
            if sim > best_sim:
                best_sim = sim
                best_mem = mem

        if best_mem is not None and best_sim >= self.similarity_threshold:
            classification = "KNOWN_OPERATIONAL_PATTERN"
            explanation = (
                f"Matched learned operational pattern '{best_mem.memory_id}' "
                f"(source event: {best_mem.source_event_id}) with {best_sim*100:.1f}% similarity "
                f"(threshold: {self.similarity_threshold*100:.0f}%)."
            )
            matched_id = best_mem.memory_id
        else:
            classification = "UNKNOWN_UNUSUAL_EVENT"
            if best_mem is not None:
                explanation = (
                    f"Highest match was '{best_mem.memory_id}' with {best_sim*100:.1f}% similarity, "
                    f"which is below the threshold of {self.similarity_threshold*100:.0f}%."
                )
                matched_id = best_mem.memory_id
            else:
                explanation = "No matching memory found."
                matched_id = None

        return MemoryMatchResult(
            classification=classification,
            best_similarity=max(0.0, best_sim),
            nearest_memory=best_mem,
            matched_memory_id=matched_id,
            explanation=explanation,
        )

    def clear(self) -> None:
        """Clear all stored memories."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM event_memories")
            conn.commit()
