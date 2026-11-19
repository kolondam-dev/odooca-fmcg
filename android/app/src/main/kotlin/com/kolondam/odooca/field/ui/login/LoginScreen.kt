package com.kolondam.odooca.field.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.text.KeyboardOptions
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.kolondam.odooca.field.AppContainer
import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.designsystem.OdoocaColors
import com.kolondam.odooca.field.designsystem.OdoocaSpacing
import com.kolondam.odooca.field.designsystem.PrimaryButton
import com.kolondam.odooca.field.designsystem.ScreenHeader
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class LoginUiState(
    val login: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
    val configured: Boolean = true,
)

class LoginViewModel(private val container: AppContainer) : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState(configured = container.config.isConfigured))
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun onLogin(value: String) = _state.update { it.copy(login = value, error = null) }
    fun onPassword(value: String) = _state.update { it.copy(password = value, error = null) }

    fun submit(onSuccess: () -> Unit) {
        val s = _state.value
        if (s.loading || s.login.isBlank() || s.password.isEmpty()) return
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            try {
                container.session.login(s.login, s.password)
                onSuccess()
            } catch (e: ApiException) {
                _state.update { it.copy(loading = false, error = e.message ?: "Login gagal") }
            } catch (e: IllegalStateException) {
                _state.update { it.copy(loading = false, error = e.message) }
            }
        }
    }

    private inline fun <T> MutableStateFlow<T>.update(block: (T) -> T) {
        value = block(value)
    }
}

@Composable
fun LoginScreen(container: AppContainer, onLoggedIn: () -> Unit) {
    val vm: LoginViewModel = viewModel(factory = viewModelFactory { initializer { LoginViewModel(container) } })
    val state by vm.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        ScreenHeader(title = "Odooca Field", subtitle = "Masuk dengan akun Odoo Anda")
        Column(
            modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(OdoocaSpacing.S4),
            verticalArrangement = Arrangement.spacedBy(OdoocaSpacing.S3),
        ) {
            if (!state.configured) {
                Text(
                    "Alamat backend belum dikonfigurasi. Isi properti Gradle odooca.baseUrl lalu bangun ulang aplikasi.",
                    color = OdoocaColors.Bad,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            OutlinedTextField(
                value = state.login,
                onValueChange = vm::onLogin,
                label = { Text("Pengguna") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = state.password,
                onValueChange = vm::onPassword,
                label = { Text("Kata sandi") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth(),
            )
            state.error?.let {
                Text(it, color = OdoocaColors.Bad, style = MaterialTheme.typography.bodyMedium)
            }
            PrimaryButton(
                text = if (state.loading) "Memproses…" else "Masuk",
                onClick = { vm.submit(onLoggedIn) },
                enabled = state.configured && !state.loading && state.login.isNotBlank() && state.password.isNotEmpty(),
            )
        }
    }
}
