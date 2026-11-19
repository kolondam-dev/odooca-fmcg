package com.kolondam.odooca.field.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val InterFamily = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
)

private fun TypeSpec.style() = TextStyle(
    fontFamily = InterFamily,
    fontWeight = FontWeight(weight),
    fontSize = sizeSp.sp,
    lineHeight = lineHeightSp.sp,
)

val OdoocaTypography = Typography(
    displayMedium = OdoocaTypeSpecs.Display.style(),
    headlineMedium = OdoocaTypeSpecs.Heading.style(),
    titleMedium = OdoocaTypeSpecs.Title.style(),
    bodyLarge = OdoocaTypeSpecs.Input.style(),
    bodyMedium = OdoocaTypeSpecs.Body.style(),
    labelLarge = OdoocaTypeSpecs.BodyStrong.style(),
    labelMedium = OdoocaTypeSpecs.Label.style(),
    labelSmall = OdoocaTypeSpecs.Badge.style(),
    bodySmall = OdoocaTypeSpecs.Caption.style(),
)
