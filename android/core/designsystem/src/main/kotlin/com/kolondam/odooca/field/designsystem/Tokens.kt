// GENERATED FILE. Jangan diedit manual.
// Sumber: pwa/design/tokens.json. Regenerasi: python3 android/tools/gen_design_tokens.py <tokens.json> <Tokens.kt>
package com.kolondam.odooca.field.designsystem

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

object OdoocaColors {
    val Ink = Color(0xFF0B1F4D)
    val Mute = Color(0xFF52647A)
    val Line = Color(0xFFE6ECF3)
    val Border = Color(0xFFC5D2E0)
    val Bg = Color(0xFFF7F9FC)
    val Surface = Color(0xFFFFFFFF)
    val Primary = Color(0xFF1B5E8C)
    val Nav = Color(0xFF001A57)
    val NavFg = Color(0xFFDCE6F5)
    val Ok = Color(0xFF11663F)
    val OkBg = Color(0xFFE7F6ED)
    val Warn = Color(0xFF7A4B00)
    val WarnBg = Color(0xFFFDF0D5)
    val Bad = Color(0xFFB42318)
    val BadBg = Color(0xFFFDE8E6)
    val Info = Color(0xFF17537E)
    val InfoBg = Color(0xFFE5F0F8)
    val Neutral = Color(0xFF3F5068)
    val NeutralBg = Color(0xFFEAEFF5)
    val Disabled = Color(0xFFE3E8EF)
    val DisabledFg = Color(0xFF66758A)
    val Badge = Color(0xFFB45309)
    val Online = Color(0xFF1F9D5B)
}

object OdoocaSpacing {
    val S1 = 4.dp
    val S2 = 8.dp
    val S3 = 12.dp
    val S4 = 16.dp
    val S5 = 20.dp
    val S6 = 24.dp
}

object OdoocaRadius {
    val Sm = 8.dp
    val Md = 10.dp
    val Lg = 14.dp
    val Xl = 20.dp
    val Pill = 999.dp
}

object OdoocaSize {
    val Touch = 44.dp
    val Header = 56.dp
    val Nav = 64.dp
    val ButtonLg = 56.dp
    val ButtonMd = 48.dp
    val ButtonSm = 44.dp
    val Field = 48.dp
}

/** Spesifikasi tipografi: bobot, ukuran (sp), tinggi baris (sp). */
data class TypeSpec(val weight: Int, val sizeSp: Float, val lineHeightSp: Float)

object OdoocaTypeSpecs {
    val Caption = TypeSpec(400, 13.0f, 18.0f)
    val Label = TypeSpec(500, 13.0f, 18.0f)
    val Badge = TypeSpec(600, 12.0f, 16.0f)
    val Body = TypeSpec(400, 15.0f, 22.0f)
    val BodyStrong = TypeSpec(600, 15.0f, 22.0f)
    val Input = TypeSpec(400, 16.0f, 24.0f)
    val Title = TypeSpec(700, 18.0f, 24.0f)
    val Heading = TypeSpec(700, 20.0f, 28.0f)
    val Display = TypeSpec(700, 26.0f, 34.0f)
}
