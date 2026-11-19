package com.kolondam.odooca.field.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

/** Tombol utama: tinggi 56 dp sesuai token `size.buttonLg`. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = OdoocaSize.ButtonLg),
        shape = RoundedCornerShape(OdoocaRadius.Md),
        colors = ButtonDefaults.buttonColors(
            containerColor = OdoocaColors.Primary,
            disabledContainerColor = OdoocaColors.Disabled,
            disabledContentColor = OdoocaColors.DisabledFg,
        ),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

enum class BadgeTone { OK, WARN, BAD, INFO, NEUTRAL }

/** Lencana status kecil; warna dari token status. */
@Composable
fun StatusBadge(text: String, tone: BadgeTone, modifier: Modifier = Modifier) {
    val (bg, fg) = when (tone) {
        BadgeTone.OK -> OdoocaColors.OkBg to OdoocaColors.Ok
        BadgeTone.WARN -> OdoocaColors.WarnBg to OdoocaColors.Warn
        BadgeTone.BAD -> OdoocaColors.BadBg to OdoocaColors.Bad
        BadgeTone.INFO -> OdoocaColors.InfoBg to OdoocaColors.Info
        BadgeTone.NEUTRAL -> OdoocaColors.NeutralBg to OdoocaColors.Neutral
    }
    Box(
        modifier = modifier
            .background(bg, RoundedCornerShape(OdoocaRadius.Pill))
            .padding(horizontal = OdoocaSpacing.S3, vertical = OdoocaSpacing.S1),
        contentAlignment = Alignment.Center,
    ) { Text(text, color = fg, style = MaterialTheme.typography.labelSmall) }
}

/** Header layar berlatar navy merek. */
@Composable
fun ScreenHeader(title: String, subtitle: String? = null, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(OdoocaColors.Nav)
            .padding(horizontal = OdoocaSpacing.S4, vertical = OdoocaSpacing.S3),
        verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S1),
    ) {
        Text(title, color = Color.White, style = MaterialTheme.typography.titleMedium)
        if (subtitle != null) Text(subtitle, color = OdoocaColors.NavFg, style = MaterialTheme.typography.bodySmall)
    }
}
