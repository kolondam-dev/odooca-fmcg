import { useEffect, useRef, useState } from "preact/hooks";
import type { z } from "zod";
import { AttendanceInboxSchema } from "../domain/attendance-correction";

const queues = {
    actionable: "Perlu keputusan Anda",
    history: "Pengajuan dan riwayat",
} as const;
type Queue = keyof typeof queues;

const endpoint = "/api/v1/attendance/corrections";
const status: Record<string, string> = {
    pending: "Menunggu persetujuan",
    waiting: "Menunggu giliran",
    approved: "Disetujui",
    rejected: "Ditolak",
    draft: "Draf",
};
function hour(value: string) {
    const [hours, minutes] = value.split(":").map(Number);
    return hours + minutes / 60;
}

async function request(path: string, form?: URLSearchParams) {
    const result = await fetch(endpoint + path, {
        ...(form ? { method: "POST", body: form } : {}),
        credentials: "same-origin",
        redirect: "manual",
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
    });
    const body = await result.json().catch(() => null);
    if (!result.ok)
        throw new Error(
            body?.error ?? "Masuk ke Odoo atau periksa koneksi dan coba lagi.",
        );
    return body;
}

export function AttendanceCorrections() {
    const [data, setData] = useState<z.infer<typeof AttendanceInboxSchema>>();
    const [queue, setQueue] = useState<Queue>("actionable");
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const pending = useRef<{ fingerprint: string; key: string } | undefined>(
        undefined,
    );
    const active = useRef(false);
    async function run(
        action?: () => Promise<unknown>,
        target = queue,
        before?: number,
    ) {
        if (active.current) return;
        active.current = true;
        setBusy(true);
        setMessage("");
        try {
            if (action) await action();
            const params = new URLSearchParams({ queue: target });
            if (before !== undefined) params.set("before", String(before));
            const page = AttendanceInboxSchema.parse(
                await request(`?${params}`),
            );
            setQueue(target);
            setData(page);
        } catch (error) {
            setMessage(
                error instanceof Error ? error.message : "Permintaan gagal.",
            );
        } finally {
            active.current = false;
            setBusy(false);
        }
    }
    useEffect(() => {
        void run();
    }, []);
    function post(path: string, fields: Record<string, string>) {
        if (!data) throw new Error("Sesi Odoo belum terhubung.");
        return request(
            path,
            new URLSearchParams({ ...fields, csrf_token: data.csrfToken }),
        );
    }

    return (
        <main class="read-shell">
            <header>
                <h1>Koreksi Absensi</h1>
                <a href="/field/">Kembali</a>
            </header>
            <nav class="read-actions" aria-label="Sesi dan persetujuan">
                <a href="/web/login?redirect=%2Ffield%2F%3Fattendance-approval">
                    Masuk Odoo
                </a>
                <button disabled={busy} onClick={() => void run()}>
                    Muat ulang
                </button>
            </nav>
            <p role="status">{busy ? "Memproses…" : message}</p>
            {data && (
                <>
                    <form
                        class="read-card"
                        onSubmit={(event) => {
                            event.preventDefault();
                            const form = event.currentTarget;
                            const vals = new FormData(form);
                            const fields = {
                                business_date: String(vals.get("date")),
                                start_hour: String(
                                    hour(String(vals.get("start"))),
                                ),
                                end_hour: String(hour(String(vals.get("end")))),
                                reason: String(vals.get("reason")).trim(),
                            };
                            const fingerprint = JSON.stringify(fields);
                            if (pending.current?.fingerprint !== fingerprint) {
                                pending.current = {
                                    fingerprint,
                                    key: crypto.randomUUID(),
                                };
                            }
                            const key = pending.current.key;
                            void run(async () => {
                                await post("", { ...fields, client_key: key });
                                pending.current = undefined;
                                form.reset();
                            });
                        }}
                    >
                        <h2>Ajukan koreksi</h2>
                        <p>
                            Gunakan jam WITA untuk tanggal yang sudah ditutup.
                        </p>
                        <label>
                            Tanggal <input name="date" type="date" required />
                        </label>{" "}
                        <label>
                            Masuk <input name="start" type="time" required />
                        </label>{" "}
                        <label>
                            Pulang <input name="end" type="time" required />
                        </label>{" "}
                        <label>
                            Alasan{" "}
                            <textarea name="reason" maxLength={1000} required />
                        </label>{" "}
                        <button disabled={busy}>Kirim pengajuan</button>
                    </form>
                    <nav class="read-actions" aria-label="Antrean koreksi">
                        {(Object.keys(queues) as Queue[]).map((target) => (
                            <button
                                key={target}
                                type="button"
                                disabled={busy}
                                aria-pressed={queue === target}
                                onClick={() => void run(undefined, target)}
                            >
                                {queues[target]}
                            </button>
                        ))}
                    </nav>
                    <section>
                        <h2>{queues[queue]}</h2>
                        {data.items.length === 0 && <p>Belum ada pengajuan.</p>}
                        {data.items.map((entry) => (
                            <article class="read-card" key={entry.id}>
                                <h3>{entry.reference}</h3>
                                <p>
                                    {entry.mine ? "Pengajuan saya · " : ""}
                                    {status[entry.state] ?? entry.state}
                                </p>
                                <p>{entry.reason}</p>
                                <ol>
                                    {entry.steps.map((tier) => (
                                        <li key={tier.name}>
                                            {tier.name} ·{" "}
                                            {status[tier.state] ?? tier.state}
                                            {tier.actor && ` · ${tier.actor}`}
                                            {tier.notes && ` · ${tier.notes}`}
                                        </li>
                                    ))}
                                </ol>
                                {entry.canDecide && (
                                    <form
                                        onSubmit={(event) => {
                                            event.preventDefault();
                                            const fields = new FormData(
                                                event.currentTarget,
                                                event.submitter,
                                            );
                                            void run(() =>
                                                post("/decision", {
                                                    approval_id: String(
                                                        entry.id,
                                                    ),
                                                    tier: String(entry.tier),
                                                    decision: String(
                                                        fields.get("decision"),
                                                    ),
                                                    notes: String(
                                                        fields.get("notes") ??
                                                            "",
                                                    ),
                                                }),
                                            );
                                        }}
                                    >
                                        <label>
                                            Catatan{" "}
                                            <textarea
                                                name="notes"
                                                maxLength={1000}
                                            />
                                        </label>{" "}
                                        <button
                                            name="decision"
                                            value="approve"
                                            disabled={busy}
                                        >
                                            Setujui
                                        </button>{" "}
                                        <button
                                            name="decision"
                                            value="reject"
                                            disabled={busy}
                                        >
                                            Tolak
                                        </button>
                                    </form>
                                )}
                            </article>
                        ))}
                        {data.nextBefore != null && (
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                    void run(undefined, queue, data.nextBefore!)
                                }
                            >
                                Halaman berikutnya
                            </button>
                        )}
                    </section>
                </>
            )}
        </main>
    );
}
