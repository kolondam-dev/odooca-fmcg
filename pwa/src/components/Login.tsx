import { useRef, useState } from "preact/hooks";
import { Brand } from "./Brand";
import { signIn } from "../data/auth";
import { BottomSheet, Button, Callout, Field } from "../ui";
export function Login({
    onSuccess,
    message = "",
    expired = false,
}: {
    onSuccess: () => Promise<void>;
    message?: string;
    /** Sesi habis (401): tampilkan lembar "Sesi berakhir" (DS: Status_401). */
    expired?: boolean;
}) {
    const [sheet, setSheet] = useState(expired);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const running = useRef(false);
    async function submit(event: SubmitEvent) {
        event.preventDefault();
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        const form = event.currentTarget as HTMLFormElement;
        const fields = new FormData(form);
        const clear = () =>
            (form.querySelector<HTMLInputElement>('[name="password"]')!.value =
                "");
        try {
            await signIn(
                String(fields.get("login") ?? ""),
                String(fields.get("password") ?? ""),
            );
            clear();
            await onSuccess();
        } catch (failure) {
            setError(
                failure instanceof Error && !(failure instanceof TypeError)
                    ? failure.message
                    : "Login belum berhasil. Coba kembali.",
            );
        } finally {
            clear();
            running.current = false;
            setBusy(false);
        }
    }
    return (
        <main class="ui-login">
            <div class="ui-login__brand">
                <Brand />
                <h1 class="ui-login__lead">Masuk untuk memulai kerja</h1>
            </div>
            {(error || message) && (
                <Callout tone="bad" icon="warning" alert>
                    {error || message}
                </Callout>
            )}
            <form class="ui-login__form" onSubmit={submit}>
                <Field
                    label="Nama pengguna"
                    name="login"
                    autoComplete="username"
                    required
                    disabled={busy}
                    autoCapitalize="none"
                    spellcheck={false}
                />
                <Field
                    label="Kata sandi"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    disabled={busy}
                />
                <Button type="submit" disabled={busy}>
                    {busy ? "Memverifikasi…" : "Masuk"}
                </Button>
            </form>
            <div class="ui-login__or">
                <span />
                atau
                <span />
            </div>
            <a
                class="ui-btn ui-btn--sec ui-btn--lg ui-login__sso"
                href="/web/login?redirect=%2Ffield%2F"
            >
                Masuk dengan SSO
            </a>
            <p class="ui-login__help">
                Lupa kata sandi? Hubungi admin atau line manager di perusahaan
                Anda.
            </p>
            <a
                class="ui-login__link"
                href="/web/session/logout?redirect=%2Ffield%2F"
            >
                Ganti akun / keluar dari sesi sebelumnya
            </a>
            {sheet ? (
                <BottomSheet
                    title="Sesi berakhir"
                    onClose={() => setSheet(false)}
                >
                    <p class="ui-sheet__text">
                        Masuk lagi untuk melanjutkan. Data yang belum terkirim
                        tetap aman di perangkat.
                    </p>
                    <Button onClick={() => setSheet(false)}>Masuk lagi</Button>
                </BottomSheet>
            ) : null}
        </main>
    );
}
