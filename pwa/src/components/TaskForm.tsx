import { useState } from "preact/hooks";
import type { Dialog } from "../ui/navigation";
import { SheetHeader } from "../ui";
import { useDialog } from "../ui/useDialog";
import { Icon } from "./Icon";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import {
    type Command,
    type Identity,
    type Snapshot,
} from "../domain/contracts";
import type { FieldStore, QueueItem } from "../storage/store";
export function TaskForm({
    dialog,
    identity,
    snapshot,
    owner,
    submit,
    close,
    workStatus,
    store,
}: {
    workStatus: string;
    store: FieldStore;
    dialog: Exclude<
        Dialog,
        { type: "order" | "display" | "extra" | "expense" }
    >;
    identity: Identity;
    snapshot: Snapshot;
    owner: string;
    submit: (
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<QueueItem>;
    close: () => void;
}) {
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const dialogRef = useDialog(() => {
        if (!busy) close();
    });
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const title = {
        proof: "Bukti pengiriman",
        profile: "Profil & Sesi Akun",
    }[dialog.type as "proof" | "profile"];
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
            {
                if (!evidence)
                    throw new Error("Simpan foto dan lokasi dahulu.");
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
                                <button type="submit" disabled={busy}>
                                    {busy ? "Menyimpan…" : "Simpan ke antrean"}
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
