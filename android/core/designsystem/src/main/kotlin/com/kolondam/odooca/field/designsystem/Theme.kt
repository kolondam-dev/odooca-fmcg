package com.kolondam.odooca.field.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val OdoocaLightColors = lightColorScheme(
    primary = OdoocaColors.Primary,
    onPrimary = Color.White,
    secondary = OdoocaColors.Nav,
    onSecondary = OdoocaColors.NavFg,
    background = OdoocaColors.Bg,
    onBackground = OdoocaColors.Ink,
    surface = OdoocaColors.Surface,
    onSurface = OdoocaColors.Ink,
    surfaceVariant = OdoocaColors.NeutralBg,
    onSurfaceVariant = OdoocaColors.Mute,
    outline = OdoocaColors.Border,
    outlineVariant = OdoocaColors.Line,
    error = OdoocaColors.Bad,
    onError = Color.White,
    errorContainer = OdoocaColors.BadBg,
    onErrorContainer = OdoocaColors.Bad,
)

private val OdoocaShapes = Shapes(
    small = RoundedCornerShape(OdoocaRadius.Sm),
    medium = RoundedCornerShape(OdoocaRadius.Md),
    large = RoundedCornerShape(OdoocaRadius.Lg),
    extraLarge = RoundedCornerShape(OdoocaRadius.Xl),
)

@Composable
fun OdoocaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = OdoocaLightColors,
        typography = OdoocaTypography,
        shapes = OdoocaShapes,
        content = content,
    )
}
