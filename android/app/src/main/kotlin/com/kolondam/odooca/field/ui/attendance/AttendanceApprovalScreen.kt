package com.kolondam.odooca.field.ui.attendance

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kolondam.odooca.field.AppContainer
import com.kolondam.odooca.field.data.network.AttendanceApproval
import com.kolondam.odooca.field.data.network.AttendanceCorrectionDraft
import com.kolondam.odooca.field.data.network.AttendanceInbox
import com.kolondam.odooca.field.data.network.AttendanceQueue
import com.kolondam.odooca.field.data.repo.SessionAccess
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

private fun hour(text: String): Double? {
    val parts = text.split(":")
    if (parts.size != 2) return null
    val hours = parts[0].toIntOrNull() ?: return null
    val minutes = parts[1].toIntOrNull() ?: return null
    if (hours !in 0..23 || minutes !in 0..59) return null
    return hours + minutes / 60.0
}

private fun status(value: String): String = when (value) {
    "pending" -> "Menunggu persetujuan"
    "waiting" -> "Menunggu giliran"
    "approved" -> "Disetujui"
    "rejected" -> "Ditolak"
    else -> value
}

@Composable
fun AttendanceApprovalScreen(container: AppContainer, ownerId: String, onExit: () -> Unit, exitLabel: String) {
    val scope = rememberCoroutineScope()
    var inbox by remember(ownerId) { mutableStateOf<AttendanceInbox?>(null) }
    var queue by remember(ownerId) { mutableStateOf(AttendanceQueue.ACTIONABLE) }
    var busy by remember(ownerId) { mutableStateOf(false) }
    var message by remember(ownerId) { mutableStateOf("") }
    var date by remember(ownerId) { mutableStateOf("") }
    var start by remember(ownerId) { mutableStateOf("") }
    var end by remember(ownerId) { mutableStateOf("") }
    var reason by remember(ownerId) { mutableStateOf("") }
    var pending by remember(ownerId) { mutableStateOf<AttendanceCorrectionDraft?>(null) }

    fun run(target: AttendanceQueue = queue, before: Long? = null, action: (suspend (String) -> Unit)? = null) {
        if (busy) return
        busy = true
        message = ""
        scope.launch {
            try {
                val result = container.session.withOwner(ownerId) {
                    if (action != null) action(checkNotNull(inbox).csrfToken)
                    container.api.attendanceInbox(target, before)
                }
                inbox = when (result) {
                    is SessionAccess.Granted -> {
                        queue = target
                        result.value
                    }
                    SessionAccess.Denied -> null
                }
                if (inbox == null) message = "Sesi berubah. Masuk kembali."
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                message = error.message ?: "Persetujuan tidak dapat dimuat."
            } finally {
                busy = false
            }
        }
    }

    LaunchedEffect(ownerId) { run() }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Koreksi Absensi", style = MaterialTheme.typography.headlineSmall)
        Row {
            TextButton(onClick = onExit, enabled = !busy) { Text(exitLabel) }
            TextButton(onClick = { run() }, enabled = !busy) { Text("Muat ulang") }
        }
        if (busy) Text("Memproses…")
        if (message.isNotEmpty()) Text(message, color = MaterialTheme.colorScheme.error)
        val data = inbox ?: return@Column
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Text("Ajukan koreksi", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(date, { date = it }, label = { Text("Tanggal (YYYY-MM-DD)") }, enabled = !busy)
                OutlinedTextField(start, { start = it }, label = { Text("Jam masuk WITA (HH:MM)") }, enabled = !busy)
                OutlinedTextField(end, { end = it }, label = { Text("Jam pulang WITA (HH:MM)") }, enabled = !busy)
                OutlinedTextField(reason, { if (it.length <= 1000) reason = it },
                    label = { Text("Alasan") }, enabled = !busy)
                Button(enabled = !busy, onClick = {
                    val low = hour(start)
                    val high = hour(end)
                    if (!date.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")) ||
                        low == null || high == null || low >= high || reason.isBlank()
                    ) {
                        message = "Isi tanggal, urutan jam WITA, dan alasan."
                    } else {
                        val draft = AttendanceCorrectionDraft("", date, low, high, reason.trim())
                        val submitted = pending?.takeIf { it.copy(key = "") == draft }
                            ?: draft.copy(key = UUID.randomUUID().toString())
                        pending = submitted
                        run { csrf ->
                            container.api.submitAttendanceCorrection(csrf, submitted)
                            pending = null
                            reason = ""
                        }
                    }
                }) { Text("Kirim pengajuan") }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (target in AttendanceQueue.entries) {
                        TextButton(onClick = { run(target) }, enabled = !busy) { Text(target.label) }
                    }
                }
                Text(queue.label, style = MaterialTheme.typography.titleMedium)
            }
            if (data.items.isEmpty()) item { Text("Belum ada pengajuan.") }
            items(data.items, key = { it.id }) { entry ->
                ApprovalCard(entry, busy) { approved, notes ->
                    run { csrf -> container.api.decideAttendanceCorrection(csrf, entry, approved, notes) }
                }
            }
            data.nextBefore?.let { cursor ->
                item {
                    Button(onClick = { run(before = cursor) }, enabled = !busy) { Text("Halaman berikutnya") }
                }
            }
        }
    }
}

@Composable
private fun ApprovalCard(entry: AttendanceApproval, busy: Boolean, decide: (Boolean, String) -> Unit) {
    var notes by remember(entry.id, entry.tier) { mutableStateOf("") }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(entry.reference, style = MaterialTheme.typography.titleMedium)
            Text((if (entry.mine) "Pengajuan saya · " else "") + status(entry.state))
            Text(entry.reason)
            for (step in entry.steps) {
                Text(listOf(step.name, status(step.state), step.actor, step.notes)
                    .filter { it.isNotBlank() }.joinToString(" · "))
            }
            if (entry.canDecide) {
                OutlinedTextField(notes, { if (it.length <= 1000) notes = it },
                    label = { Text("Catatan") }, enabled = !busy)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = !busy, onClick = { decide(true, notes) }) { Text("Setujui") }
                    TextButton(enabled = !busy, onClick = { decide(false, notes) }) { Text("Tolak") }
                }
            }
        }
    }
}
