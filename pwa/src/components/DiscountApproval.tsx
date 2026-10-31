import { useState } from "preact/hooks";
import {
    approvalRoot,
    rootOrderDate,
    ORDER_DAY_CLOSED,
} from "../domain/order-revisions";
import { useBusinessDate } from "./useBusinessDate";
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
    const today = useBusinessDate();
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
                revisi SO tanpa diskon. Approval wajib pada hari root SO dalam
                WITA. Salesman wajib follow-up/push approval ke manager secara
                manual.
            </p>
            <label>
                Alasan keputusan diskon
                <textarea
                    value={reason}
                    maxLength={500}
                    onInput={(e) => setReason(e.currentTarget.value)}
                />
            </label>
            {rows.map((row) => {
                let blocked = "";
                try {
                    if (
                        rootOrderDate(
                            approvalRoot(queue, owner, row),
                            owner,
                        ) !== today
                    )
                        blocked = ORDER_DAY_CLOSED;
                } catch {
                    blocked = "Sumber SO perlu review; data tetap tersimpan.";
                }
                return (
                    <div key={row.key}>
                        <p>
                            {row.label} · {row.command.client_uuid.slice(0, 8)}
                        </p>
                        {blocked && <p role="status">{blocked}</p>}
                        <button
                            class="secondary"
                            disabled={busy || !!blocked}
                            onClick={() => void decide(row, true)}
                        >
                            Setujui diskon
                        </button>
                        <button
                            class="secondary"
                            disabled={busy || !!blocked}
                            onClick={() => void decide(row, false)}
                        >
                            Tolak diskon
                        </button>
                    </div>
                );
            })}
            {error && <p role="alert">{error}</p>}
        </section>
    );
}
