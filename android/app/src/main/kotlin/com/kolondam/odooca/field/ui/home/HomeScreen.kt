package com.kolondam.odooca.field.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.kolondam.odooca.field.AppContainer
import com.kolondam.odooca.field.data.db.OutletEntity
import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.data.sync.OutboxScheduler
import com.kolondam.odooca.field.designsystem.BadgeTone
import com.kolondam.odooca.field.designsystem.OdoocaColors
import com.kolondam.odooca.field.designsystem.OdoocaSpacing
import com.kolondam.odooca.field.designsystem.PrimaryButton
import com.kolondam.odooca.field.designsystem.ScreenHeader
import com.kolondam.odooca.field.designsystem.StatusBadge
import com.kolondam.odooca.field.domain.sync.CommandState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class HomeUiState(val refreshing: Boolean = false, val error: String? = null)

class HomeViewModel(private val container: AppContainer) : ViewModel() {
    private val owner = container.session.ownerId.orEmpty()

    val outlets: StateFlow<List<OutletEntity>> = container.snapshots.observeOutlets(owner)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val snapshotInfo: StateFlow<String?> = container.snapshots.observeSnapshot(owner)
        .map { s -> s?.let { "Data ${it.businessDate.ifBlank { "-" }} • versi ${it.version.take(8)}" } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    val pending: StateFlow<Int> = container.outbox.observe(owner)
        .map { list ->
            list.count {
                it.state == CommandState.QUEUED.name || it.state == CommandState.SENDING.name ||
                    it.state == CommandState.AUTH_REQUIRED.name
            }
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    private val _ui = MutableStateFlow(HomeUiState())
    val ui: StateFlow<HomeUiState> = _ui.asStateFlow()

    val ownerId: String get() = owner

    fun refresh() {
        if (_ui.value.refreshing) return
        _ui.value = HomeUiState(refreshing = true)
        viewModelScope.launch {
            _ui.value = try {
                container.snapshots.refresh(owner)
                HomeUiState()
            } catch (e: ApiException) {
                if (e.status == 401) container.session.logout()
                HomeUiState(error = if (e.status == null) "Tidak ada koneksi. Menampilkan data tersimpan." else e.message)
            } catch (e: IllegalStateException) {
                HomeUiState(error = e.message)
            }
        }
    }

    fun logout() = container.session.logout()
}

@Composable
fun HomeScreen(container: AppContainer, onOpenCalibration: () -> Unit) {
    val vm: HomeViewModel = viewModel(factory = viewModelFactory { initializer { HomeViewModel(container) } })
    val identity by container.session.identity.collectAsStateWithLifecycle()
    val outlets by vm.outlets.collectAsStateWithLifecycle()
    val info by vm.snapshotInfo.collectAsStateWithLifecycle()
    val pending by vm.pending.collectAsStateWithLifecycle()
    val ui by vm.ui.collectAsStateWithLifecycle()
    val context = LocalContext.current.applicationContext

    LaunchedEffect(Unit) { vm.refresh() }

    Column(Modifier.fillMaxSize()) {
        ScreenHeader(
            title = identity?.name.orEmpty(),
            subtitle = listOfNotNull(identity?.title?.takeIf { it.isNotBlank() }, info).joinToString(" • "),
        )
        Column(
            Modifier.fillMaxWidth().padding(OdoocaSpacing.S4),
            verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S2),
        ) {
            ui.error?.let { Text(it, color = OdoocaColors.Bad, style = MaterialTheme.typography.bodyMedium) }
            Row(horizontalArrangement = Arrangement.spacedBy(OdoocaSpacing.S2)) {
                if (ui.refreshing) StatusBadge("Menyinkronkan…", BadgeTone.INFO)
                if (pending > 0) StatusBadge("$pending menunggu kirim", BadgeTone.WARN)
            }
            PrimaryButton(
                text = if (ui.refreshing) "Menyinkronkan…" else "Sinkronkan data",
                onClick = vm::refresh,
                enabled = !ui.refreshing,
            )
            if (pending > 0) {
                TextButton(onClick = { OutboxScheduler.kick(context, vm.ownerId) }) { Text("Kirim antrean sekarang") }
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                horizontal = OdoocaSpacing.S4, vertical = OdoocaSpacing.S2,
            ),
            verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S2),
        ) {
            if (outlets.isEmpty() && !ui.refreshing) {
                item {
                    Text(
                        "Belum ada outlet pada penugasan hari ini.",
                        color = OdoocaColors.Mute,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            items(outlets, key = { it.id }) { OutletCard(it) }
        }
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = OdoocaSpacing.S2),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            TextButton(onClick = onOpenCalibration) { Text("Kalibrasi GPS perangkat") }
            TextButton(onClick = vm::logout) { Text("Keluar") }
        }
    }
}

@Composable
private fun OutletCard(outlet: OutletEntity) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = OdoocaColors.Surface),
        border = BorderStroke(1.dp, OdoocaColors.Line),
    ) {
        Column(
            Modifier.padding(OdoocaSpacing.S4),
            verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S1),
        ) {
            Text(outlet.name, style = MaterialTheme.typography.titleMedium, color = OdoocaColors.Ink)
            if (outlet.address.isNotBlank()) {
                Text(outlet.address, style = MaterialTheme.typography.bodyMedium, color = OdoocaColors.Mute)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(OdoocaSpacing.S2)) {
                if (outlet.channel.isNotBlank()) StatusBadge(outlet.channel, BadgeTone.NEUTRAL)
                StatusBadge("radius ${outlet.radius.toInt()} m", BadgeTone.INFO)
                // Jarak/jam hanya ditampilkan bila server mengirim nilainya.
                if (outlet.distance.isNotBlank()) StatusBadge(outlet.distance, BadgeTone.NEUTRAL)
                if (outlet.time.isNotBlank()) StatusBadge(outlet.time, BadgeTone.NEUTRAL)
            }
        }
    }
}
