import { ApiError } from "../domain/contracts";

// Use Odoo's native login form, CSRF protection, session cookie and throttling.
// Credentials and CSRF tokens stay in memory and are never persisted.
export async function signIn(login: string, password: string) {
    const options: RequestInit = {
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(20000),
    };
    const response = await fetch("/web/login?redirect=%2Ffield%2F", options);
    if (!response.ok)
        throw new Error("Layanan login belum tersedia. Coba lagi.");
    const document = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
    );
    const csrf = document.querySelector<HTMLInputElement>(
        'input[name="csrf_token"]',
    )?.value;
    if (!csrf) throw new Error("Form login belum tersedia. Hubungi admin.");
    const body = new URLSearchParams({
        login: login.trim(),
        password,
        csrf_token: csrf,
        redirect: "/field/",
    });
    // The database, when supplied, must come from the server's login form.
    const db =
        document.querySelector<HTMLInputElement>('input[name="db"]')?.value;
    if (db) body.set("db", db);
    const result = await fetch("/web/login", {
        ...options,
        method: "POST",
        body,
    });
    if (!result.ok)
        throw new Error(
            "Login belum berhasil. Periksa akun atau coba kembali nanti.",
        );
    const html = new DOMParser().parseFromString(
        await result.text(),
        "text/html",
    );
    if (html.querySelector('form.oe_login_form, input[name="password"]'))
        throw new ApiError(
            401,
            "Login belum berhasil. Periksa nama pengguna dan kata sandi Anda.",
        );
    // MFA/SSO needs Odoo's native flow; never treat its intermediate page as login success.
    const session = await fetch("/web/session/get_session_info", {
        ...options,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {},
            id: 1,
        }),
    });
    const info = await session.json();
    if (!session.ok || !info.result?.uid)
        throw new Error("Selesaikan verifikasi akun melalui login Odoo.");
}
