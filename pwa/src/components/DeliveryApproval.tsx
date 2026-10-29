import { useState } from "preact/hooks";
import { approvalTiers } from "../domain/delivery-approval";
import type { FieldStore, QueueItem } from "../storage/store";
export function DeliveryApproval({
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
        (r) =>
            r.command?.type === "delivery.pod.submit" &&
            r.command.payload?.request,
    );
    async function decide(
        row: QueueItem,
        role: "spv" | "branch_manager",
        approved: boolean,
    ) {
        setBusy(true);
        setError("");
        try {
            await store.decideDemoDelivery(owner, row, role, approved, reason);
            changed();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal");
        } finally {
            setBusy(false);
        }
    }
    if (!rows.length) return null;
    return (
        <section class="paper-card">
            <h3>Simulator approval pending/cancel</h3>
            <p>
                Keputusan contoh SPV/BM; tidak mengubah picking, stok atau
                jadwal resmi.
            </p>
            <label>
                Alasan keputusan delivery
                <textarea
                    value={reason}
                    maxLength={500}
                    onInput={(e) => setReason(e.currentTarget.value)}
                />
            </label>
            {rows.map((row) =>
                row.command.type === "delivery.pod.submit" &&
                row.command.payload.request ? (
                    <article key={row.key}>
                        <p>
                            {row.label} ·{" "}
                            {row.command.payload.request.kind === "reschedule"
                                ? `Kirim ulang ${row.command.payload.request.requested_date}`
                                : `Cancel ${row.command.payload.request.sub_reason}`}{" "}
                            · tier{" "}
                            {approvalTiers(
                                row.command.payload.request,
                                row.command.payload.source.business_date,
                            ).join(" → ")}
                        </p>
                        <p>{row.receipt?.message ?? row.state}</p>
                        {row.state === "needs_approval" &&
                            ["spv", "branch_manager"].map((role) => (
                                <span key={role}>
                                    <button
                                        class="secondary"
                                        disabled={busy}
                                        onClick={() =>
                                            void decide(
                                                row,
                                                role as
                                                    | "spv"
                                                    | "branch_manager",
                                                true,
                                            )
                                        }
                                    >
                                        Simulasikan setujui {role}
                                    </button>
                                    <button
                                        class="secondary"
                                        disabled={busy}
                                        onClick={() =>
                                            void decide(
                                                row,
                                                role as
                                                    | "spv"
                                                    | "branch_manager",
                                                false,
                                            )
                                        }
                                    >
                                        Simulasikan tolak {role}
                                    </button>
                                </span>
                            ))}
                    </article>
                ) : null,
            )}
            {error && <p role="alert">{error}</p>}
        </section>
    );
}
