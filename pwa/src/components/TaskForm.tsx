import { useState } from "preact/hooks";
import type { Dialog } from "../ui/navigation";
import { SheetHeader } from "../ui";
import { useDialog } from "../ui/useDialog";
import { ExpenseContextFields } from "./ExpenseContextFields";
import { LocalDateInput } from "./LocalDateInput";
import { AttendanceCapture } from "./AttendanceCapture";
import { Icon } from "./Icon";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import {
    type Command,
    type Identity,
    type Snapshot,
} from "../domain/contracts";
import { validateExpense } from "../domain/expense";
import { money } from "../domain/format";
import type { FieldStore, QueueItem } from "../storage/store";
export function TaskForm({
    dialog,
    identity,
    snapshot,
    owner,
    submit,
    startSession,
    close,
    workStatus,
    store,
}: {
    workStatus: string;
    store: FieldStore;
    dialog: Exclude<Dialog, { type: "order" | "display" }>;
    identity: Identity;
    snapshot: Snapshot;
    owner: string;
    submit: (
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<QueueItem>;
    startSession: (
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) => Promise<void>;
    close: () => void;
}) {
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const dialogRef = useDialog(() => {
        if (!busy) close();
    });
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [category, setCategory] = useState("fuel_planned");
    const title = {
        extra: "Ajukan extra call",
        proof: "Bukti pengiriman",
        expense: "Uang lapangan",
        attendance: "Absensi foto & lokasi",
        leave: "Pengajuan cuti",
        profile: "Profil & Sesi Akun",
    }[dialog.type];
    async function send(e: SubmitEvent) {
        e.preventDefault();
        if (busy) return;
        setError("");
        const f = new FormData(e.currentTarget as HTMLFormElement);
        setBusy(true);
        try {
            let type: Command["type"];
            let payload: Record<string, unknown>;
            let label: string;
            if (dialog.type === "extra") {
                type = "sales.extra_call.request";
                payload = {
                    outlet_name: f.get("outlet"),
                    reason: f.get("reason"),
                };
                label = `Extra call • ${f.get("outlet")}`;
            } else if (dialog.type === "expense") {
                const amount = Number(f.get("amount"));
                if (!Number.isFinite(amount) || amount < 1)
                    throw new Error("Nominal harus lebih dari nol.");
                type = "field_expense.request";
                payload = validateExpense(
                    {
                        category,
                        amount: String(amount),
                        trip_id: String(f.get("trip") ?? ""),
                        delivery_id:
                            f.get("scope") === "delivery"
                                ? String(f.get("delivery") ?? "").trim() || null
                                : null,
                        expense_scope: f.get("scope"),
                        scheduled_date: f.get("date"),
                        odometer:
                            f.get("odometer") === null ||
                            f.get("odometer") === ""
                                ? null
                                : Number(f.get("odometer")),
                        reason: f.get("reason"),
                        evidence: evidence ?? null,
                    },
                    identity.businessDate,
                );
                label = `Petty cash • ${money(amount)}`;
            } else if (dialog.type === "leave") {
                const from = String(f.get("from")),
                    to = String(f.get("to"));
                if (to < from)
                    throw new Error(
                        "Tanggal selesai tidak boleh sebelum mulai.",
                    );
                type = "hris.leave.request";
                payload = {
                    date_from: from,
                    date_to: to,
                    reason: f.get("reason"),
                };
                label = "Pengajuan cuti";
            } else {
                if (!evidence)
                    throw new Error("Simpan foto dan lokasi dahulu.");
                if (dialog.type === "attendance") {
                    await startSession(dialog.event ?? "check_in", evidence);
                    close();
                    return;
                }
                if (dialog.type !== "proof")
                    throw new Error("Form bukti tidak dikenal.");
                type = "delivery.proof.submit";
                payload = {
                    event: f.get("event"),
                    delivery_id: dialog.delivery,
                    result: f.get("result"),
                    evidence,
                    map_status: "pending",
                };
                label = `POD • ${dialog.delivery}`;
            }
            // Evidence remains local: receipts must not claim the backend has verified it.
            if (
                evidence &&
                ["hris.attendance.capture", "delivery.proof.submit"].includes(
                    type,
                )
            )
                throw new Error(
                    "Bukti tersimpan lokal. Pengiriman resmi menunggu API evidence & snapshot peta.",
                );
            await submit(type, payload, label);
        } catch (x) {
            setError(
                x instanceof Error
                    ? x.message
                    : "Penyimpanan gagal. Form tetap tersedia.",
            );
        } finally {
            setBusy(false);
        }
    }
    return (
        <div class="modal-backdrop page-backdrop">
            <section
                ref={dialogRef}
                class="sheet full-page-form"
                role="dialog"
                aria-modal="true"
                aria-labelledby="dialog-title"
            >
                <SheetHeader
                    eyebrow={identity.name}
                    title={title}
                    titleId="dialog-title"
                    onClose={close}
                    closeLabel="Tutup form"
                    closeDisabled={busy}
                />
                <form onSubmit={(e) => void send(e)}>
                    <div class="sheet-body">
                        {dialog.type === "extra" && (
                            <>
                                <p class="notice">
                                    Kunjungan di luar PJP baru sah setelah
                                    supervisor menyetujui.
                                </p>
                                <label>
                                    Nama outlet
                                    <input
                                        name="outlet"
                                        required
                                        maxLength={100}
                                    />
                                </label>
                                <label>
                                    Alasan extra call
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                            </>
                        )}
                        {dialog.type === "expense" && (
                            <>
                                <label>
                                    Kategori
                                    <select
                                        aria-label="Kategori"
                                        value={category}
                                        onChange={(e) =>
                                            setCategory(e.currentTarget.value)
                                        }
                                    >
                                        <option value="fuel_planned">
                                            BBM terencana (H-1)
                                        </option>
                                        <option value="fuel_emergency">
                                            BBM insidentil
                                        </option>
                                        <option value="meal">
                                            Uang makan luar kota
                                        </option>
                                        <option value="lodging">
                                            Penginapan luar kota
                                        </option>
                                        <option value="repair">
                                            Perbaikan darurat / derek
                                        </option>
                                    </select>
                                </label>
                                <ExpenseContextFields
                                    deliveries={snapshot.deliveries}
                                    trip={dialog.trip}
                                />
                                <p class="notice">
                                    {category === "fuel_emergency"
                                        ? "BBM insidentil: Supervisor + Branch Manager, berapa pun nominalnya."
                                        : "Wajib approval supervisor. Di atas limit kewenangan diteruskan ke Branch Manager."}
                                </p>
                                <LocalDateInput
                                    name="date"
                                    label="Tanggal perjalanan"
                                />
                                <label>
                                    Nominal pengajuan (Rp)
                                    <input
                                        name="amount"
                                        type="number"
                                        min="1"
                                        max="100000000"
                                        inputMode="numeric"
                                        required
                                    />
                                </label>
                                {category.startsWith("fuel") && (
                                    <>
                                        <label>
                                            KM / odometer awal
                                            <input
                                                name="odometer"
                                                type="number"
                                                min="0"
                                                required
                                            />
                                        </label>
                                        <p class="footnote">
                                            Tanggal bisnis:{" "}
                                            {identity.businessDate}. Pengajuan
                                            BBM H-1 memerlukan foto odometer;
                                            realisasi memerlukan struk dan foto
                                            odometer setelah isi.
                                        </p>
                                    </>
                                )}
                                <label>
                                    Tujuan / alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "attendance" && (
                            <>
                                <label>
                                    Aktivitas
                                    <select
                                        name="event"
                                        value={dialog.event ?? "check_in"}
                                        disabled
                                    >
                                        <option value="check_in">
                                            Absensi Masuk (Checkin)
                                        </option>
                                        <option value="check_out">
                                            Absensi Keluar (Checkout)
                                        </option>
                                    </select>
                                </label>
                                <AttendanceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                    employeeName={identity.name}
                                    companyName={
                                        identity.companyName ??
                                        `Perusahaan #${identity.companyId}`
                                    }
                                    mapSite={
                                        snapshot.office
                                            ? {
                                                  ...snapshot.office,
                                                  simulated:
                                                      snapshot.office
                                                          .coordinate_status !==
                                                      "verified",
                                              }
                                            : undefined
                                    }
                                />
                            </>
                        )}
                        {dialog.type === "proof" && (
                            <>
                                <p class="muted">{dialog.delivery}</p>
                                <label>
                                    Hasil serah terima
                                    <select name="result">
                                        <option value="accepted">
                                            Diterima lengkap
                                        </option>
                                        <option value="partial">
                                            Diterima sebagian / retur
                                        </option>
                                    </select>
                                </label>
                                <p class="notice">
                                    Bukti lokal · status DO menunggu validasi
                                    server.
                                </p>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "leave" && (
                            <>
                                <LocalDateInput
                                    name="from"
                                    label="Tanggal mulai"
                                />
                                <LocalDateInput
                                    name="to"
                                    label="Tanggal selesai"
                                />
                                <label>
                                    Alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <p class="footnote">
                                    Pengajuan menunggu validasi saldo cuti dan
                                    persetujuan atasan.
                                </p>
                            </>
                        )}
                        {dialog.type === "profile" && (
                            <div
                                style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "16px",
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "14px",
                                        padding: "14px",
                                        background: "#f8fafc",
                                        borderRadius: "14px",
                                        border: "1px solid #e2e8f0",
                                    }}
                                >
                                    <span class="avatar large">
                                        {identity.name[0]}
                                    </span>
                                    <div>
                                        <h3
                                            style={{
                                                fontSize: "1.1rem",
                                                fontWeight: "700",
                                                margin: 0,
                                            }}
                                        >
                                            {identity.name}
                                        </h3>
                                        <p
                                            class="muted"
                                            style={{ margin: "2px 0 0" }}
                                        >
                                            {identity.title}
                                        </p>
                                        <small
                                            style={{
                                                color: "#004ecc",
                                                fontWeight: "600",
                                                display: "block",
                                                marginTop: "2px",
                                            }}
                                        >
                                            PT Manado Distribusi Utama
                                        </small>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "8px",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Perusahaan</span>
                                        <strong>
                                            PT Manado Distribusi Utama
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Gudang & Hub</span>
                                        <strong>
                                            {snapshot.warehouseName ??
                                                (snapshot.scope?.warehouse_id
                                                    ? `Gudang ${snapshot.scope.warehouse_id}`
                                                    : "Belum tersedia")}
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Rute & Sesi</span>
                                        <strong>{workStatus}</strong>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "10px",
                                        marginTop: "10px",
                                    }}
                                >
                                    <a
                                        href="/web/login?redirect=/field/"
                                        class="button primary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#001a57",
                                            color: "#ffffff",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="user" size={18} /> Masuk
                                        Akun Odoo / Ganti Akun
                                    </a>
                                    <a
                                        href="/web/session/logout?redirect=/field/"
                                        class="button secondary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#fff0f0",
                                            color: "#dc2626",
                                            border: "1px solid #fecaca",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="close" size={18} /> Keluar
                                        dari Sesi (Logout)
                                    </a>
                                </div>
                            </div>
                        )}
                        {error && (
                            <div class="error-box" role="alert">
                                <Icon name="warning" size={20} />
                                {error}
                            </div>
                        )}
                    </div>
                    {dialog.type !== "profile" ? (
                        <footer class="sheet-footer">
                            <>
                                <button
                                    type="button"
                                    class="secondary"
                                    onClick={close}
                                    disabled={busy}
                                >
                                    Kembali
                                </button>
                                <button
                                    type="submit"
                                    disabled={
                                        busy ||
                                        (dialog.type === "attendance" &&
                                            !evidence)
                                    }
                                >
                                    {busy
                                        ? "Menyimpan…"
                                        : dialog.type === "attendance"
                                          ? dialog.event === "check_out"
                                              ? "Check out"
                                              : "Check in"
                                          : "Simpan ke antrean"}
                                </button>
                            </>
                        </footer>
                    ) : (
                        <footer
                            class="sheet-footer"
                            style={{ justifyContent: "center" }}
                        >
                            <button
                                type="button"
                                class="secondary full"
                                onClick={close}
                                style={{ margin: 0 }}
                            >
                                Tutup
                            </button>
                        </footer>
                    )}
                </form>
            </section>
        </div>
    );
}
