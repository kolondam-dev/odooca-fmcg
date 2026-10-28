import { useState } from "preact/hooks";
import type { FieldStore, QueueItem } from "../storage/store";
export function DiscountApproval({
    store,
    owner,
    queue,
    changed,
}: {
    store: FieldStore;
    owner: string;
    queue: QueueItem[];
    changed: () => void;
}) {
    const [reason, setReason] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const rows = queue.filter(
        (q) =>
            (q.command?.type === "sales.order.revise" ||
                (q.command?.type === "sales.order.submit" &&
                    q.command.payload?.discount_request)) &&
            q.state === "needs_approval",
    );
    async function decide(row: QueueItem, approved: boolean) {
        setBusy(true);
        setError("");
        try {
            await store.decideDemoDiscount(owner, row, approved, reason);
            changed();
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Keputusan gagal disimpan.",
            );
        } finally {
            setBusy(false);
        }
    }
    if (!rows.length) return null;
    return (
        <section class="paper-card">
            <h3>Simulator approval diskon</h3>
            <p>
                Kontrol pengujian, bukan kewenangan sales atau approval Odoo.
                Keputusan berlaku pada pengajuan pending yang dipilih, termasuk
                revisi SO tanpa diskon.
            </p>
            <label>
                Alasan keputusan diskon
                <textarea
                    value={reason}
                    maxLength={500}
                    onInput={(e) => setReason(e.currentTarget.value)}
                />
            </label>
            {rows.map((row) => (
                <div key={row.key}>
                    <p>
                        {row.label} · {row.command.client_uuid.slice(0, 8)}
                    </p>
                    <button
                        class="secondary"
                        disabled={busy}
                        onClick={() => void decide(row, true)}
                    >
                        Simulasikan setujui diskon
                    </button>
                    <button
                        class="secondary"
                        disabled={busy}
                        onClick={() => void decide(row, false)}
                    >
                        Simulasikan tolak diskon
                    </button>
                </div>
            ))}
            {error && <p role="alert">{error}</p>}
        </section>
    );
}
