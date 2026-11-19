package com.kolondam.odooca.field.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface SnapshotDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: SnapshotEntity)

    @Query("SELECT * FROM snapshot WHERE ownerId = :owner")
    fun observe(owner: String): Flow<SnapshotEntity?>
}

@Dao
interface OutletDao {
    @Query("SELECT * FROM outlet WHERE ownerId = :owner ORDER BY name")
    fun observe(owner: String): Flow<List<OutletEntity>>

    @Query("DELETE FROM outlet WHERE ownerId = :owner")
    suspend fun deleteFor(owner: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(items: List<OutletEntity>)
}

@Dao
interface OutboxDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    suspend fun insert(entity: OutboxEntity)

    @Update
    suspend fun update(entity: OutboxEntity)

    @Query("SELECT * FROM outbox WHERE id = :id")
    suspend fun get(id: String): OutboxEntity?

    @Query("SELECT * FROM outbox WHERE ownerId = :owner ORDER BY createdAtMs, id")
    suspend fun all(owner: String): List<OutboxEntity>

    @Query("SELECT * FROM outbox WHERE ownerId = :owner ORDER BY createdAtMs DESC")
    fun observe(owner: String): Flow<List<OutboxEntity>>
}
