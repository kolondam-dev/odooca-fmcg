import { assertLocalEvidence } from "./evidence-package";
import {
    CommandSchema,
    ownerKey,
    type FieldProvider,
    type Identity,
} from "./contracts";
import { ExpenseRequestSchema, type ExpenseRequest } from "./expense";
import { fieldBusinessDate } from "./morning";
import {
    ExpensePolicySchema,
    ExpenseRealizationSchema,
    SimulatedAdvanceSchema,
    receiptKey,
    type ExpenseRealization,
    type SimulatedAdvance,
} from "./settlement-contracts";
import { FieldStore, type QueueItem } from "../storage/store";
import { businessRejected } from "./outbox-state";
import type { Outbox } from "./outbox";
export const advanceKey = (uuid: string) => `expense-advance:${uuid}`;
export const realizationKey = (uuid: string) => `expense-realization:${uuid}`;
export function approvalRoles(
    category: ExpenseRequest["category"],
    amount: number,
    limit: string,
): ("supervisor" | "branch_manager")[] {
    if (
        !Number.isSafeInteger(amount) ||
        amount < 1 ||
        !ExpensePolicySchema.safeParse({
            version: "check",
            supervisor_limit: limit,
        }).success
    )
        throw new Error("Policy atau nominal tidak valid.");
    return category === "fuel_emergency" || amount > Number(limit)
        ? ["supervisor", "branch_manager"]
        : ["supervisor"];
}
export function settlementPreview(
    request: ExpenseRequest,
    advance: SimulatedAdvance,
    realization: ExpenseRealization,
) {
    const total = realization.lines.reduce(
        (sum, line) => sum + Number(line.amount),
        0,
    );
    if (!Number.isSafeInteger(total) || total < 1 || total > 100000000)
        throw new Error("Total realisasi harus Rp1–100.000.000.");
    const balance = Number(advance.amount) - total;
    return {
        total,
        refund: Math.max(0, balance),
        variance: Math.max(0, -balance),
        approvals: approvalRoles(
            request.category,
            Math.max(total, Number(advance.amount)),
            advance.policy.supervisor_limit,
        ),
    };
}
function requestFrom(item: QueueItem, owner: string) {
    if (
        item.owner !== owner ||
        item.command.type !== "field_expense.request" ||
        !CommandSchema.safeParse(item.command).success
    )
        throw new Error("Pengajuan biaya tidak sesuai akun.");
    const parsed = ExpenseRequestSchema.safeParse(item.command.payload);
    if (!parsed.success)
        throw new Error(
            "Data pengajuan biaya tidak valid. Review ulang diperlukan.",
        );
    const request = parsed.data;
    if (
        (request.expense_scope === "delivery") !== !!request.delivery_id ||
        (request.category.startsWith("fuel") && request.odometer === null)
    )
        throw new Error("Konteks pengajuan biaya tidak valid.");
    return request;
}
export function validateAdvance(
    value: unknown,
    item: QueueItem,
    owner: string,
): SimulatedAdvance {
    const parsed = SimulatedAdvanceSchema.safeParse(value);
    if (!parsed.success)
        throw new Error(
            "Data pencairan simulasi tidak valid. Review ulang diperlukan.",
        );
    const advance = parsed.data;
    const request = requestFrom(item, owner);
    const roles = approvalRoles(
        request.category,
        Number(request.amount),
        advance.policy.supervisor_limit,
    );
    if (
        advance.owner !== owner ||
        advance.source_request_uuid !== item.command.client_uuid ||
        advance.request_fingerprint !== JSON.stringify(request) ||
        advance.amount !== request.amount ||
        JSON.stringify(advance.approvals) !== JSON.stringify(roles) ||
        Date.parse(advance.approved_at) <
            Date.parse(item.command.occurred_at) ||
        Date.parse(advance.approved_at) > Date.parse(advance.disbursed_at) ||
        Date.parse(advance.disbursed_at) > Date.now() ||
        !["needs_approval"].includes(item.state) ||
        item.receipt?.status !== "needs_approval" ||
        item.receipt.client_uuid !== item.command.client_uuid
    )
        throw new Error(
            "Pencairan simulasi tidak cocok dengan pengajuan/persetujuan. Review ulang diperlukan.",
        );
    return advance;
}
export function validateRealization(
    value: unknown,
    item: QueueItem,
    advance: SimulatedAdvance,
    owner: string,
): ExpenseRealization {
    validateAdvance(advance, item, owner);
    const request = requestFrom(item, owner);
    const parsed = ExpenseRealizationSchema.safeParse(value);
    if (!parsed.success)
        throw new Error(
            "Lengkapi komponen biaya, nominal, tanggal, struk dan bukti odometer yang valid.",
        );
    const body = parsed.data;
    if (!!body.supersedes_uuid !== !!body.correction_reason)
        throw new Error(
            "Koreksi memerlukan referensi realisasi ditolak dan alasan.",
        );
    if (
        body.source_request_uuid !== item.command.client_uuid ||
        body.advance_reference !== advance.reference
    )
        throw new Error("Realisasi tidak terkait pencairan yang dipilih.");
    const ids: string[] = [];
    const receipts = new Set<string>();
    for (const line of body.lines) {
        if (
            line.expense_date <
                fieldBusinessDate(new Date(advance.disbursed_at)) ||
            line.expense_date > fieldBusinessDate()
        )
            throw new Error(
                "Tanggal struk harus antara pencairan dan hari ini.",
            );
        const key = receiptKey(line);
        if (receipts.has(key))
            throw new Error("Struk yang sama tidak boleh dihitung dua kali.");
        receipts.add(key);
        ids.push(line.evidence.id);
    }
    if (request.category.startsWith("fuel")) {
        const fuel = body.fuel;
        if (!fuel || body.lines.length !== 1)
            throw new Error(
                "BBM wajib satu struk serta bukti odometer sebelum dan sesudah.",
            );
        const [liters, decimal = ""] = fuel.liters.split(".");
        const ml = Number(liters) * 1000 + Number(decimal.padEnd(3, "0"));
        if (
            ml <= 0 ||
            Math.round((ml * Number(fuel.price_per_liter)) / 1000) !==
                Number(body.lines[0].amount)
        )
            throw new Error(
                "Total struk BBM harus sesuai liter × harga per liter (dibulatkan ke rupiah).",
            );
        if (
            fuel.odometer_before < request.odometer! ||
            fuel.odometer_after < fuel.odometer_before
        )
            throw new Error(
                "KM tidak boleh turun dari pengajuan/sebelum pengisian.",
            );
        ids.push(fuel.before.id, fuel.after.id);
    } else if (body.fuel)
        throw new Error("Data BBM tidak berlaku untuk kategori biaya ini.");
    if (new Set(ids).size !== ids.length)
        throw new Error(
            "Setiap struk dan odometer wajib memakai referensi foto terpisah.",
        );
    const evidence = [
        ...body.lines.map((l) => l.evidence),
        ...(body.fuel ? [body.fuel.before, body.fuel.after] : []),
    ];
    if (
        evidence.some(
            (e) =>
                Date.parse(e.capturedAt) > Date.now() ||
                Date.parse(e.capturedAt) < Date.parse(advance.disbursed_at),
        )
    )
        throw new Error("Waktu bukti tidak sesuai pencairan/hari ini.");
    settlementPreview(request, advance, body);
    return body;
}
export class ExpenseSimulation {
    constructor(
        private store: FieldStore,
        private identity: Identity,
        private provider: FieldProvider,
        private outbox: Outbox,
    ) {}
    private async source(uuid: string) {
        const item = (await this.store.list(ownerKey(this.identity))).find(
            (q) => q.command.client_uuid === uuid,
        );
        if (!item)
            throw new Error("Pengajuan biaya tidak ditemukan pada akun ini.");
        requestFrom(item, ownerKey(this.identity));
        return item;
    }
    async load(uuid: string) {
        const item = await this.source(uuid);
        const value = await this.store.draft(
            ownerKey(this.identity),
            advanceKey(uuid),
        );
        if (value === undefined) return undefined;
        const advance = validateAdvance(value, item, ownerKey(this.identity));
        if (advance.realization_uuid) {
            const rows = await this.store.list(ownerKey(this.identity));
            let uuid: string | undefined = advance.realization_uuid;
            const seen = new Set<string>();
            let childTime = Infinity;
            while (uuid) {
                if (seen.has(uuid))
                    throw new Error("Riwayat koreksi berulang/tidak valid.");
                seen.add(uuid);
                const linked = rows.find((q) => q.command.client_uuid === uuid);
                if (
                    !linked ||
                    linked.owner !== advance.owner ||
                    linked.key !== `${advance.owner}:${uuid}` ||
                    linked.command.type !==
                        "field_expense.realization.submit" ||
                    !CommandSchema.safeParse(linked.command).success ||
                    Date.parse(linked.command.occurred_at) > childTime ||
                    Date.parse(linked.command.occurred_at) > Date.now() ||
                    Date.parse(linked.command.occurred_at) <
                        Date.parse(advance.disbursed_at)
                )
                    throw new Error(
                        "Referensi/urutan realisasi tidak valid. Data tidak dihapus.",
                    );
                const body = validateRealization(
                    linked.command.payload,
                    item,
                    advance,
                    advance.owner,
                );
                if (seen.size > 1 && !businessRejected(linked))
                    throw new Error(
                        "Riwayat koreksi harus merujuk penolakan bisnis.",
                    );
                childTime = Date.parse(linked.command.occurred_at);
                uuid = body.supersedes_uuid;
            }
        }
        return advance;
    }
    async simulateDisbursement(uuid: string) {
        if (
            this.provider.mode !== "demo" ||
            !navigator.onLine ||
            (this.provider.scenario && this.provider.scenario !== "normal") ||
            !this.provider.expensePolicy
        )
            throw new Error(
                "Pencairan fiktif hanya tersedia online pada simulator Normal.",
            );
        if (
            ownerKey(await this.provider.bootstrap()) !==
            ownerKey(this.identity)
        )
            throw new Error("Identitas berubah. Muat ulang aplikasi.");
        const existing = await this.load(uuid);
        if (existing) return existing;
        const item = await this.source(uuid),
            request = requestFrom(item, ownerKey(this.identity));
        const policy = ExpensePolicySchema.parse(
            await this.provider.expensePolicy(),
        );
        const advance: SimulatedAdvance = {
            mode: "simulation",
            owner: ownerKey(this.identity),
            source_request_uuid: uuid,
            request_fingerprint: JSON.stringify(request),
            reference: `SIM-ADV-${uuid}`,
            amount: request.amount,
            policy,
            approvals: approvalRoles(
                request.category,
                Number(request.amount),
                policy.supervisor_limit,
            ),
            approved_at: new Date().toISOString(),
            disbursed_at: new Date().toISOString(),
            realization_uuid: null,
        };
        validateAdvance(advance, item, ownerKey(this.identity));
        if (
            !navigator.onLine ||
            (this.provider.scenario && this.provider.scenario !== "normal")
        )
            throw new Error(
                "Koneksi/respons berubah. Pencairan fiktif belum dicatat.",
            );
        return validateAdvance(
            await this.store.createDraftIfAbsent(
                advance.owner,
                advanceKey(uuid),
                advance,
            ),
            item,
            advance.owner,
        );
    }
    async submit(uuid: string, value: unknown) {
        if (this.provider.mode !== "demo")
            throw new Error("Realisasi resmi belum tersedia.");
        const item = await this.source(uuid),
            advance = await this.load(uuid);
        if (!advance) throw new Error("Simulasikan approval/pencairan dahulu.");
        const predecessor = advance.realization_uuid
            ? (await this.store.list(advance.owner)).find(
                  (q) => q.command.client_uuid === advance.realization_uuid,
              )
            : undefined;
        if (advance.realization_uuid && !businessRejected(predecessor))
            throw new Error(
                "Realisasi sudah diantrekan. Hanya receipt penolakan bisnis yang membuka koreksi.",
            );
        const body = validateRealization(
            value,
            item,
            advance,
            ownerKey(this.identity),
        );
        if (
            (predecessor &&
                body.supersedes_uuid !== predecessor.command.client_uuid) ||
            (!predecessor && body.supersedes_uuid)
        )
            throw new Error(
                "Referensi koreksi tidak cocok dengan realisasi ditolak.",
            );
        const blobs = await this.store.listEvidence(ownerKey(this.identity));
        const refs = [
            ...body.lines.map((l) => l.evidence),
            ...(body.fuel ? [body.fuel.before, body.fuel.after] : []),
        ];
        for (const ref of refs)
            await assertLocalEvidence(
                blobs.find(
                    (e) => e.key === `${ownerKey(this.identity)}:${ref.id}`,
                ),
                ref,
                ownerKey(this.identity),
            );
        const commandUuid = crypto.randomUUID();
        return this.outbox.enqueue(
            "field_expense.realization.submit",
            body,
            "Realisasi biaya • menunggu review",
            commandUuid,
            {
                key: advanceKey(uuid),
                value: { ...advance, realization_uuid: commandUuid },
                expected: advance,
                guards: { source: item, predecessor },
            },
        );
    }
}
