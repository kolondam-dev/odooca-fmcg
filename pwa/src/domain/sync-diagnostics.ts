import { CommandSchema, ReceiptSchema } from "./contracts";
import { createVisitSyncValidator, visitContextOf } from "./visit-validation";
import { visitDependenciesReady } from "./visit-dependencies";
import { VisitContextSchema } from "./visit-contracts";
import { queueLabels } from "./format";
import type { FieldStore, QueueState } from "../storage/store";
export type SyncSnapshot = Awaited<ReturnType<FieldStore["visitSyncState"]>>;
export type QueueFilter =
    | "all"
    | "pending"
    | "review"
    | "approval"
    | "accepted";
export interface SyncDiagnostic {
    key: string;
    label: string;
    uuid: string;
    type: string;
    occurredAt?: string;
    state: QueueState | "invalid";
    stateLabel: string;
    group: Exclude<QueueFilter, "all">;
    code: string;
    title: string;
    guidance: string;
    message: string;
    attempts: number;
    retryAt?: string;
    reference?: string;
    context?: {
        session: string;
        date: string;
        outlet: string;
        version: string;
    };
    dependencies: { uuid: string; state: string }[];
}
const copy: Record<string, [SyncDiagnostic["group"], string, string]> = {
    integrity: [
        "review",
        "Integritas perlu review",
        "Data tetap lokal. Hubungi supervisor dengan UUID transaksi; jangan hapus data atau membuat transaksi pengganti.",
    ],
    dependency: [
        "pending",
        "Menunggu transaksi sebelumnya",
        "Check-in harus diterima dan setiap order harus memiliki receipt bisnis sebelum check-out dikirim. Jika sumber ditahan, minta review supervisor.",
    ],
    offline: [
        "pending",
        "Tersimpan saat offline",
        "Buka aplikasi saat koneksi tersedia. UUID transaksi tetap sama saat sync.",
    ],
    ready: [
        "pending",
        "Menunggu proses sinkronisasi",
        "Sinkronkan saat online. Pemeriksaan sumber dan dependency akan diulang sebelum pengiriman.",
    ],
    backoff: [
        "pending",
        "Menunggu jadwal coba ulang",
        "Koneksi atau layanan sebelumnya gagal. Tunggu jadwal berikutnya atau gunakan Sinkronkan saat online; UUID tetap sama.",
    ],
    sending: [
        "pending",
        "Pengiriman belum terkonfirmasi",
        "Jangan membuat transaksi pengganti. Hasil belum pasti sampai receipt dengan UUID cocok diterima.",
    ],
    auth: [
        "review",
        "Sesi perlu dipulihkan",
        "Sinkronkan tidak memulihkan sesi yang habis. Pemulihan sesi resmi belum tersedia; hubungi supervisor. Data tetap tersimpan.",
    ],
    approval: [
        "approval",
        "Diterima untuk review",
        "Receipt ini hanya menyatakan perlu approval. Belum disetujui, dicairkan atau diposting ke Odoo.",
    ],
    business_rejected: [
        "review",
        "Ditolak oleh simulator",
        "Jangan replay UUID yang ditolak. Koreksi hanya melalui fitur bisnis yang mendukung revisi; lainnya menunggu review supervisor.",
    ],
    transport_rejected: [
        "review",
        "Penolakan tanpa receipt bisnis",
        "Error transport bukan hasil bisnis. Jangan membuat pengganti sampai status asal diperiksa; retry terminal tetap dikunci.",
    ],
    accepted: [
        "accepted",
        "Receipt simulator cocok",
        "Diterima simulator belum berarti posting Odoo, pencairan, atau approval resmi.",
    ],
};
const safeText = (value: unknown, fallback: string, length = 160) =>
    typeof value === "string" && value.trim()
        ? value.slice(0, length)
        : fallback;
export function diagnoseSync(
    snapshot: SyncSnapshot,
    owner: string,
    online: boolean,
    now = Date.now(),
): SyncDiagnostic[] {
    const validateVisit = createVisitSyncValidator(
        owner,
        snapshot.ledger,
        snapshot.rows,
        snapshot.morning,
    );
    // Projection only: never mutate queue, draft, receipt or retry metadata.
    return snapshot.rows
        .filter((q) => q?.owner === owner)
        .map((row, index) => {
            const command = CommandSchema.safeParse(row.command);
            const state = Object.hasOwn(queueLabels, row.state)
                ? row.state
                : "invalid";
            const result: SyncDiagnostic = {
                key: safeText(row.key, `invalid-${index}`),
                label: safeText(row.label, "Transaksi lokal tidak terbaca"),
                uuid: command.success
                    ? command.data.client_uuid
                    : "UUID tidak valid",
                type: command.success
                    ? command.data.type
                    : "Command tidak valid",
                occurredAt: command.success
                    ? command.data.occurred_at
                    : undefined,
                state,
                stateLabel:
                    state === "invalid"
                        ? "Status tidak valid"
                        : queueLabels[state],
                group: "review",
                code: "integrity",
                title: "",
                guidance: "",
                message: safeText(
                    row.receipt?.message ?? row.error,
                    "Tersimpan lokal, belum diterima server.",
                    600,
                ),
                attempts:
                    Number.isSafeInteger(row.attempts) && row.attempts >= 0
                        ? row.attempts
                        : 0,
                dependencies: [],
            };
            let code = "integrity";
            try {
                if (
                    !command.success ||
                    state === "invalid" ||
                    row.key !== `${owner}:${command.data.client_uuid}` ||
                    !Number.isSafeInteger(row.attempts) ||
                    row.attempts < 0 ||
                    !Number.isFinite(row.nextAttempt) ||
                    row.nextAttempt < 0
                )
                    throw new Error("Invalid envelope");
                validateVisit(row);
                const c = command.data;
                const context =
                    c.type === "sales.visit.check_in" ||
                    c.type === "sales.visit.check_out"
                        ? visitContextOf(c.payload)
                        : c.type === "sales.order.submit"
                          ? VisitContextSchema.safeParse(
                                c.payload.visit_context,
                            ).data
                          : undefined;
                if (context)
                    result.context = {
                        session: context.work_session_id,
                        date: context.business_date,
                        outlet: safeText(
                            context.outlet_id,
                            "Outlet tidak terbaca",
                        ),
                        version: safeText(
                            context.snapshot_version,
                            "Versi tidak terbaca",
                        ),
                    };
                const parents: string[] = [];
                if (context && c.type !== "sales.visit.check_in")
                    parents.push(context.visit_uuid);
                if (c.type === "sales.visit.check_out")
                    parents.push(...c.payload.order_uuids);
                if (c.type === "field_expense.realization.submit") {
                    parents.push(c.payload.source_request_uuid);
                    if (c.payload.supersedes_uuid)
                        parents.push(c.payload.supersedes_uuid);
                }
                result.dependencies = [...new Set(parents)].map((uuid) => {
                    const parent = snapshot.rows.find(
                        (q) =>
                            q.owner === owner &&
                            q.key === `${owner}:${uuid}` &&
                            q.command?.client_uuid === uuid,
                    );
                    const receipt = ReceiptSchema.safeParse(parent?.receipt);
                    const matched =
                        receipt.success &&
                        receipt.data.client_uuid === uuid &&
                        receipt.data.status === parent?.state;
                    return {
                        uuid,
                        state: !parent
                            ? "Referensi hilang"
                            : matched
                              ? `Receipt cocok: ${queueLabels[receipt.data.status]}`
                              : "Belum ada receipt bisnis cocok",
                    };
                });
                const receipt = ReceiptSchema.safeParse(row.receipt);
                const matched =
                    receipt.success &&
                    receipt.data.client_uuid === c.client_uuid &&
                    receipt.data.status === state;
                if (
                    (["accepted", "needs_approval"].includes(state) &&
                        !matched) ||
                    (row.receipt !== undefined && !matched)
                )
                    throw new Error("Invalid receipt");
                if (matched)
                    result.reference = safeText(
                        receipt.data.reference,
                        "Tanpa referensi",
                    );
                if (state === "accepted") code = "accepted";
                else if (state === "needs_approval") code = "approval";
                else if (state === "rejected")
                    code = matched ? "business_rejected" : "transport_rejected";
                else if (state === "auth_required") code = "auth";
                else if (!visitDependenciesReady(c, owner, snapshot.rows))
                    code = "dependency";
                else if (state === "sending") code = "sending";
                else if (!online) code = "offline";
                else if (row.nextAttempt > now) {
                    code = "backoff";
                    if (Number.isFinite(new Date(row.nextAttempt).getTime()))
                        result.retryAt = new Date(
                            row.nextAttempt,
                        ).toISOString();
                } else code = "ready";
            } catch {
                code = "integrity";
            }
            if (code === "integrity")
                result.message = safeText(
                    row.error,
                    "Data atau referensi transaksi tidak valid. Perlu review; data dipertahankan.",
                    600,
                );
            const [group, title, guidance] = copy[code];
            return { ...result, code, group, title, guidance };
        })
        .sort((a, b) => (b.occurredAt ?? "").localeCompare(a.occurredAt ?? ""));
}
