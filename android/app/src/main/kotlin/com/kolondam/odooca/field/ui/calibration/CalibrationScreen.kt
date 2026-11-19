package com.kolondam.odooca.field.ui.calibration

import android.Manifest
import android.app.Application
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kolondam.odooca.field.designsystem.BadgeTone
import com.kolondam.odooca.field.designsystem.OdoocaColors
import com.kolondam.odooca.field.designsystem.OdoocaSpacing
import com.kolondam.odooca.field.designsystem.PrimaryButton
import com.kolondam.odooca.field.designsystem.ScreenHeader
import com.kolondam.odooca.field.designsystem.StatusBadge
import com.kolondam.odooca.field.device.IntegrityCollector
import com.kolondam.odooca.field.device.LocationCollector
import com.kolondam.odooca.field.domain.location.CalibrationInput
import com.kolondam.odooca.field.domain.location.GpsQualification
import com.kolondam.odooca.field.domain.location.LocationSample
import com.kolondam.odooca.field.domain.location.LocationStatus
import com.kolondam.odooca.field.domain.location.QualificationCategory
import com.kolondam.odooca.field.domain.location.QualificationReport
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

sealed interface CalibrationUi {
    data object Idle : CalibrationUi
    data class Running(val samples: Int, val target: Int) : CalibrationUi
    data class Done(val report: QualificationReport) : CalibrationUi
    data class Failed(val message: String) : CalibrationUi
}

class CalibrationViewModel(app: Application) : AndroidViewModel(app) {
    private val collector = LocationCollector(app)
    private val integrity = IntegrityCollector(app)
    private val _ui = MutableStateFlow<CalibrationUi>(CalibrationUi.Idle)
    val ui: StateFlow<CalibrationUi> = _ui.asStateFlow()
    private var job: Job? = null

    fun start() {
        if (job?.isActive == true) return
        job = viewModelScope.launch {
            val permission = collector.hasPermission()
            val gps = collector.gpsEnabled()
            val startMs = System.currentTimeMillis()
            val samples = mutableListOf<LocationSample>()
            var flagged = false

            if (permission && gps) {
                _ui.value = CalibrationUi.Running(0, TARGET_SAMPLES)
                withTimeoutOrNull(SESSION_TIMEOUT_MS) {
                    collector.fixes().takeWhile { samples.size < TARGET_SAMPLES }.collect { fix ->
                        samples += fix.sample
                        flagged = flagged || fix.flaggedBySystem
                        _ui.value = CalibrationUi.Running(samples.size, TARGET_SAMPLES)
                    }
                }
            }
            val report = GpsQualification.evaluate(
                CalibrationInput(
                    samples = samples,
                    nowMs = System.currentTimeMillis(),
                    sessionStartMs = startMs,
                    permissionGranted = permission,
                    locationServicesEnabled = gps,
                    integrity = integrity.collect(spoofingFlagged = flagged),
                ),
            )
            _ui.value = CalibrationUi.Done(report)
        }
    }

    fun cancel() {
        job?.cancel()
        _ui.value = CalibrationUi.Idle
    }

    private companion object {
        const val TARGET_SAMPLES = 30
        const val SESSION_TIMEOUT_MS = 150_000L
    }
}

@Composable
fun CalibrationScreen(onBack: () -> Unit) {
    val vm: CalibrationViewModel = viewModel()
    val ui by vm.ui.collectAsStateWithLifecycle()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.start() }
    val context = LocalContext.current

    Column(Modifier.fillMaxSize()) {
        ScreenHeader("Kalibrasi GPS perangkat", "Diam di area terbuka selama pengukuran")
        Column(
            Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(OdoocaSpacing.S4),
            verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S3),
        ) {
            when (val s = ui) {
                CalibrationUi.Idle -> {
                    Text(
                        "Pengukuran mengumpulkan hingga 30 sampel GPS lalu menilai akurasi, waktu fix pertama, " +
                            "kestabilan, konsistensi waktu, dan integritas perangkat.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = OdoocaColors.Mute,
                    )
                    PrimaryButton("Mulai pengukuran", onClick = {
                        val granted = androidx.core.content.ContextCompat.checkSelfPermission(
                            context, Manifest.permission.ACCESS_FINE_LOCATION,
                        ) == android.content.pm.PackageManager.PERMISSION_GRANTED
                        if (granted) vm.start() else launcher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                    })
                }
                is CalibrationUi.Running -> {
                    Text("Mengumpulkan sampel: ${s.samples} / ${s.target}", style = MaterialTheme.typography.titleMedium)
                    PrimaryButton("Batalkan", onClick = vm::cancel)
                }
                is CalibrationUi.Done -> ReportView(s.report, onAgain = vm::start)
                is CalibrationUi.Failed -> Text(s.message, color = OdoocaColors.Bad)
            }
        }
        Row(Modifier.fillMaxWidth().navigationBarsPadding()) {
            TextButton(onClick = onBack) { Text("Kembali") }
        }
    }
}

@Composable
private fun ReportView(r: QualificationReport, onAgain: () -> Unit) {
    val tone = when (r.category) {
        QualificationCategory.QUALIFIED -> BadgeTone.OK
        QualificationCategory.CONDITIONAL -> BadgeTone.WARN
        QualificationCategory.UNQUALIFIED -> BadgeTone.BAD
    }
    Row(horizontalArrangement = Arrangement.spacedBy(OdoocaSpacing.S2)) {
        StatusBadge(r.category.name, tone)
        StatusBadge(r.status.name, if (r.status == LocationStatus.TRUSTED) BadgeTone.OK else BadgeTone.NEUTRAL)
    }
    Text("Skor ${r.total} / 100", style = MaterialTheme.typography.headlineMedium, color = OdoocaColors.Ink)
    val m = r.metrics
    Text(
        listOf(
            "Sampel valid: ${m.validSamples} dari ${m.totalSamples}",
            "Akurasi median: ${m.medianAccuracyM?.let { "%.1f m".format(it) } ?: "-"}",
            "Akurasi P90: ${m.p90AccuracyM?.let { "%.1f m".format(it) } ?: "-"}",
            "Fix pertama: ${m.firstFixMs?.let { "%.1f detik".format(it / 1000.0) } ?: "-"}",
            "Simpangan median: ${m.medianDisplacementM?.let { "%.1f m".format(it) } ?: "-"}",
        ).joinToString("\n"),
        style = MaterialTheme.typography.bodyMedium,
        color = OdoocaColors.Ink,
    )
    if (r.reasons.isNotEmpty()) {
        Text("Catatan: " + r.reasons.joinToString(", ") { it.name }, style = MaterialTheme.typography.bodySmall, color = OdoocaColors.Mute)
    }
    Text(
        "Kebijakan ${r.policyVersion}: ambang masih hipotesis awal dan harus dikalibrasi dari uji lapangan. " +
            "Hasil ini belum dikirim ke server.",
        style = MaterialTheme.typography.bodySmall,
        color = OdoocaColors.Mute,
    )
    PrimaryButton("Ukur ulang", onClick = onAgain)
}
