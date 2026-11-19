package com.kolondam.odooca.field.data.repo

import androidx.room.withTransaction
import com.kolondam.odooca.field.data.db.OdoocaDatabase
import com.kolondam.odooca.field.data.db.OutletEntity
import com.kolondam.odooca.field.data.db.SnapshotEntity
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.data.network.OutletDto
import com.kolondam.odooca.field.data.network.SnapshotDto
import kotlinx.coroutines.flow.Flow

class SnapshotRepository(private val api: OdoocaApi, private val db: OdoocaDatabase) {
    fun observeSnapshot(ownerId: String): Flow<SnapshotEntity?> = db.snapshots().observe(ownerId)

    fun observeOutlets(ownerId: String): Flow<List<OutletEntity>> = db.outlets().observe(ownerId)

    /** Mengambil snapshot dari server dan menggantikan cache pemilik dalam satu transaksi. */
    suspend fun refresh(ownerId: String): SnapshotDto {
        val (raw, dto) = api.snapshot()
        db.withTransaction {
            db.snapshots().upsert(
                SnapshotEntity(
                    ownerId = ownerId,
                    version = dto.version,
                    businessDate = dto.scope?.businessDate.orEmpty(),
                    updatedAt = dto.updatedAt,
                    fetchedAtMs = System.currentTimeMillis(),
                    rawJson = raw,
                ),
            )
            db.outlets().deleteFor(ownerId)
            db.outlets().insertAll(dto.outlets.map { it.toEntity(ownerId) })
        }
        return dto
    }

    private fun OutletDto.toEntity(ownerId: String) = OutletEntity(
        ownerId = ownerId,
        id = id,
        name = name,
        channel = channel,
        address = address,
        distance = distance,
        time = time,
        latitude = latitude,
        longitude = longitude,
        radius = radius,
        imageUrl = imageUrl,
    )
}
