package com.kolondam.odooca.field.data.db

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/** Snapshot harian terakhir per pemilik; JSON mentah disimpan utuh agar bisa diparse ulang. */
@Entity(tableName = "snapshot")
data class SnapshotEntity(
    @PrimaryKey val ownerId: String,
    val version: String,
    val businessDate: String,
    val updatedAt: String,
    val fetchedAtMs: Long,
    val rawJson: String,
)

@Entity(tableName = "outlet", primaryKeys = ["ownerId", "id"])
data class OutletEntity(
    val ownerId: String,
    val id: String,
    val name: String,
    val channel: String,
    val address: String,
    val distance: String,
    val time: String,
    val latitude: Double,
    val longitude: Double,
    val radius: Double,
    val imageUrl: String?,
)

/** Antrean pengiriman. `id` adalah UUID klien yang stabil dan dipakai ulang pada setiap retry. */
@Entity(tableName = "outbox", indices = [Index("ownerId")])
data class OutboxEntity(
    @PrimaryKey val id: String,
    val ownerId: String,
    val kind: String,
    val state: String,
    val createdAtMs: Long,
    val attempts: Int,
    val nextAttemptAtMs: Long,
    val dependsOnJson: String,
    val payload: String,
    val error: String?,
    val receiptReference: String?,
    val receiptMessage: String?,
    /** Berkas foto bukti (hanya untuk kind EVIDENCE). */
    val filePath: String? = null,
    /** Receipt JSON mentah dari server untuk item yang sudah diterima. */
    val receiptJson: String? = null,
)
