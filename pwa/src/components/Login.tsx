import { useRef, useState } from "preact/hooks";
import { Brand } from "./Brand";
import { signIn } from "../data/auth";
export function Login({
    onSuccess,
    message = "",
}: {
    onSuccess: () => Promise<void>;
    message?: string;
}) {
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const running = useRef(false);
    return (
        <main class="login-page">
            <div class="login-layout">
                <Brand />
                <form
                    class="login-box"
                    onSubmit={async (event) => {
                        event.preventDefault();
                        if (running.current) return;
                        running.current = true;
                        setBusy(true);
                        setError("");
                        const form = event.currentTarget;
                        const fields = new FormData(form);
                        try {
                            await signIn(
                                String(fields.get("login") ?? ""),
                                String(fields.get("password") ?? ""),
                            );
                            form.querySelector<HTMLInputElement>(
                                '[name="password"]',
                            )!.value = "";
                            await onSuccess();
                        } catch (failure) {
                            setError(
                                failure instanceof Error &&
                                    !(failure instanceof TypeError)
                                    ? failure.message
                                    : "Login belum berhasil. Coba kembali.",
                            );
                        } finally {
                            form.querySelector<HTMLInputElement>(
                                '[name="password"]',
                            )!.value = "";
                            running.current = false;
                            setBusy(false);
                        }
                    }}
                >
                    <h1>Masuk</h1>
                    <p class="muted">Gunakan akun perusahaan Anda.</p>
                    <label>
                        Nama pengguna
                        <input
                            name="login"
                            autoComplete="username"
                            required
                            disabled={busy}
                            autoCapitalize="none"
                            spellcheck={false}
                        />
                    </label>
                    <label>
                        Kata sandi
                        <input
                            name="password"
                            type="password"
                            autoComplete="current-password"
                            required
                            disabled={busy}
                        />
                    </label>
                    {(error || message) && (
                        <p class="form-error" role="alert">
                            {error || message}
                        </p>
                    )}
                    <button type="submit" disabled={busy}>
                        {busy ? "Memverifikasi…" : "Masuk"}
                    </button>
                    <p class="login-help">
                        Butuh bantuan? Hubungi admin atau line manager di
                        perusahaan Anda.
                    </p>
                    <a
                        class="text-button"
                        href="/web/login?redirect=%2Ffield%2F"
                    >
                        Opsi login perusahaan / verifikasi akun
                    </a>
                </form>
            </div>
        </main>
    );
}
