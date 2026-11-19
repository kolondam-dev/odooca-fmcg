package com.kolondam.odooca.field.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * Versi 1. Migrasi wajib ditulis eksplisit pada perubahan skema berikutnya;
 * sengaja tidak memakai penghapusan destruktif karena outbox berisi data yang belum terkirim.
 */
@Database(
    entities = [SnapshotEntity::class, OutletEntity::class, OutboxEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class OdoocaDatabase : RoomDatabase() {
    abstract fun snapshots(): SnapshotDao
    abstract fun outlets(): OutletDao
    abstract fun outbox(): OutboxDao

    companion object {
        fun create(context: Context): OdoocaDatabase =
            Room.databaseBuilder(context, OdoocaDatabase::class.java, "odooca-field.db").build()
    }
}
