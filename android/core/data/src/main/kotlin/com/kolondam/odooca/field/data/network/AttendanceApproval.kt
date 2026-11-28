package com.kolondam.odooca.field.data.network

import kotlinx.serialization.Serializable

@Serializable
data class AttendanceApprovalStep(val name: String, val state: String, val actor: String, val notes: String)

@Serializable
data class AttendanceApproval(
    val id: Long,
    val reference: String,
    val reason: String,
    val state: String,
    val tier: Int,
    val canDecide: Boolean,
    val mine: Boolean,
    val steps: List<AttendanceApprovalStep>,
)

@Serializable
data class AttendanceInbox(val items: List<AttendanceApproval>, val csrfToken: String, val nextBefore: Long? = null)

enum class AttendanceQueue(val query: String, val label: String) {
    ACTIONABLE("actionable", "Perlu keputusan Anda"),
    HISTORY("history", "Pengajuan dan riwayat"),
}

data class AttendanceCorrectionDraft(
    val key: String,
    val date: String,
    val start: Double,
    val end: Double,
    val reason: String,
)
