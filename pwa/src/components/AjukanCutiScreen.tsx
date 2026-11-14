import { useState } from "preact/hooks";
import { LeaveRequestSchema, workingDays } from "../domain/leave";
import {
    Button,
    Callout,
    Card,
    Field,
    Screen,
    ScreenHeader,
    Select,
} from "../ui";
import { Textarea } from "../ui/Textarea";
import { useBackLayer } from "../ui/navigation";

/**
 * Layar penuh Ajukan cuti (DS: Ajukan_cuti). Kontrak server hanya mendukung rentang tanggal + alasan,
 * jadi jenis cuti selain tahunan, lampiran surat dokter, dan saldo ditampilkan sebagai belum tersedia (K21).
 */
export function AjukanCutiScreen({
    submit,
    close,
}: {
    submit: (
        type: "hris.leave.request",
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [reason, setReason] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const days = workingDays(from, to);
    async function send() {
        if (busy) return;
        setError("");
        const parsed = LeaveRequestSchema.safeParse({
            date_from: from,
            date_to: to,
            reason,
        });
        if (!parsed.success) {
            const p = parsed.error.issues[0]?.path[0];
            setError(
                p === "date_to" && from && to
                    ? "Tanggal selesai tidak boleh sebelum mulai."
                    : p === "reason"
                      ? "Alasan wajib diisi (minimal 3 karakter)."
                      : "Tanggal mulai dan selesai wajib diisi.",
            );
            return;
        }
        setBusy(true);
        try {
            await submit("hris.leave.request", parsed.data, "Pengajuan cuti");
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
    return (
        <Screen
            label="Ajukan cuti"
            class="ui-screen--over ui-screen--top"
            header={<ScreenHeader title="Ajukan cuti" onBack={close} />}
            footer={
                <Button
                    icon="check"
                    disabled={busy}
                    onClick={() => void send()}
                >
                    {busy ? "Menyimpan…" : "Kirim pengajuan"}
                </Button>
            }
        >
            <Card>
                <span class="exp-saldo__label">Saldo cuti tahunan</span>
                <strong class="exp-saldo__amt">Dihitung server</strong>
            </Card>
            <Select
                label="Jenis cuti"
                value="annual"
                disabled
                onChange={() => undefined}
                options={[{ value: "annual", label: "Cuti tahunan" }]}
            />
            <Field label="Mulai" type="date" value={from} onInput={setFrom} />
            <Field label="Selesai" type="date" value={to} onInput={setTo} />
            <div class="ui-kv">
                <span>Durasi</span>
                <strong>
                    {days === undefined ? "—" : `${days} hari kerja`}
                </strong>
            </div>
            <Textarea
                label="Alasan"
                value={reason}
                maxLength={500}
                onInput={setReason}
            />
            <Callout tone="info">
                Pengajuan diteruskan ke atasan. Tidak ada notifikasi otomatis;
                hubungi atasan bila mendesak. Cuti sakit dengan lampiran surat
                dokter belum tersedia.
            </Callout>
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
