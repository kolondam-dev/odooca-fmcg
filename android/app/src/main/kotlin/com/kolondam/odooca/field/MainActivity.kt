package com.kolondam.odooca.field

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.kolondam.odooca.field.designsystem.OdoocaTheme
import com.kolondam.odooca.field.ui.AppNav

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as OdoocaApplication).container
        setContent {
            OdoocaTheme { AppNav(container) }
        }
    }
}
