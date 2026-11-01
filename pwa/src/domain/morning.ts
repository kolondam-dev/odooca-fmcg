import { LocalExpenseEvidenceSchema } from "./settlement-contracts";
import type { EvidenceReference } from "./evidence-package";
import { assertLocalEvidence } from "./evidence-package";
import { DeliveryTaskSchema } from "./delivery-contracts";
import { z } from "zod";
import {
    SnapshotSchema,
    ownerKey,
    type FieldProvider,
    type Identity,
} from "./contracts";
import type { FieldStore } from "../storage/store";
export const MorningRecordSchema = z
    .object({
        mode: z.literal("simulation"),
        owner: z.string().min(1),
        businessDate: z.iso.date(),
        attendanceReference: z.string().min(1),
        attendanceAt: z.iso.datetime(),
        clockOutAt: z.iso.datetime().optional(),
        attendanceEvidence: LocalExpenseEvidenceSchema.optional(),
        clockOutEvidence: LocalExpenseEvidenceSchema.optional(),
        sessionId: z.string().uuid().nullable(),
        openedAt: z.iso.datetime().nullable(),
        snapshot: SnapshotSchema.nullable(),
        deliveryManifest: z.array(DeliveryTaskSchema).min(1).optional(),
    })
    .strict();
export type MorningRecord = z.infer<typeof MorningRecordSchema>;
export const MORNING_KEY = "morning-session-v1";
export function fieldBusinessDate(now = new Date()): string {
    return now.toLocaleDateString("en-CA", { timeZone: "Asia/Makassar" });
}
// Structural DTO checks alone are insufficient for persisted bundles. All entry
// points (sync, restore and readiness) share these semantic checks.
function validMorningSnapshot(value: unknown, date: string): boolean {
    const parsed = SnapshotSchema.safeParse(value);
    if (!parsed.success) return false;
    const snapshot = parsed.data;
    return (
        !!snapshot.version.trim() &&
        z.iso.datetime().safeParse(snapshot.updatedAt).success &&
        fieldBusinessDate(new Date(snapshot.updatedAt)) === date &&
        Date.parse(snapshot.updatedAt) <= Date.now() &&
        snapshot.outlets.length > 0 &&
        snapshot.products.length > 0
    );
}
function validMorningRecord(
    value: unknown,
    owner: string,
    date: string,
): MorningRecord | undefined {
    const parsed = MorningRecordSchema.safeParse(value);
    if (!parsed.success) return undefined;
    const record = parsed.data;
    if (
        record.owner !== owner ||
        record.businessDate !== date ||
        fieldBusinessDate(new Date(record.attendanceAt)) !== date ||
        Date.parse(record.attendanceAt) > Date.now()
    )
        return undefined;
    if (
        record.clockOutAt &&
        (Date.parse(record.clockOutAt) < Date.parse(record.attendanceAt) ||
            Date.parse(record.clockOutAt) > Date.now() ||
            fieldBusinessDate(new Date(record.clockOutAt)) !== date)
    )
        return undefined;
    // Attendance-only is a valid intermediate state, but never a ready session.
    if (
        record.sessionId === null &&
        record.openedAt === null &&
        record.snapshot === null
    )
        return record;
    if (
        !record.sessionId ||
        !record.openedAt ||
        !record.snapshot ||
        fieldBusinessDate(new Date(record.openedAt)) !== date ||
        Date.parse(record.openedAt) < Date.parse(record.attendanceAt) ||
        Date.parse(record.openedAt) > Date.now() ||
        !validMorningSnapshot(record.snapshot, date) ||
        (record.snapshot.catalog_version === 2 &&
            (!record.snapshot.scope ||
                `${record.snapshot.scope.company_id}:${record.snapshot.scope.user_id}` !==
                    owner ||
                record.snapshot.scope.business_date !== date)) ||
        Date.parse(record.snapshot.updatedAt) > Date.parse(record.openedAt)
    )
        return undefined;
    return record;
}
export function morningReady(
    record: unknown,
    owner: string,
    date = fieldBusinessDate(),
): boolean {
    const valid = validMorningRecord(record, owner, date);
    return !!valid?.sessionId && !valid.clockOutAt;
}
export class MorningSimulation {
    constructor(
        private store: FieldStore,
        private identity: Identity,
        private provider: FieldProvider,
    ) {}
    async restore(): Promise<MorningRecord | undefined> {
        return validMorningRecord(
            await this.store.draft(ownerKey(this.identity), MORNING_KEY),
            ownerKey(this.identity),
            fieldBusinessDate(),
        );
    }
    private async checkConnection() {
        if (this.provider.mode !== "demo")
            throw new Error("Sesi resmi belum tersedia.");
        if (!navigator.onLine)
            throw new Error(
                "Sesi pagi wajib dibuka online. Hubungkan perangkat lalu coba lagi.",
            );
        if (this.provider.scenario && this.provider.scenario !== "normal")
            throw new Error(
                "Sesi ditolak atau belum diterima. Pilih mode Normal untuk melanjutkan.",
            );
        const current = await this.provider.bootstrap();
        if (
            ownerKey(current) !== ownerKey(this.identity) ||
            current.businessDate !== fieldBusinessDate()
        )
            throw new Error(
                "Identitas atau tanggal bisnis berubah. Muat ulang aplikasi.",
            );
        if (!current.roles.some((r) => r === "sales" || r === "delivery"))
            throw new Error("Sesi kunjungan hanya untuk Sales/Canvasser.");
        return current.businessDate;
    }
    /**
     * One-tap day start: attendance is accepted when the day has no record yet,
     * then the daily bundle is opened. Attendance evidence captured elsewhere in
     * the app is already durable before this call.
     */
    async openDay(evidence?: EvidenceReference) {
        const current = await this.restore();
        if (!current || current.businessDate !== fieldBusinessDate())
            await this.acceptAttendance(evidence);
        return this.open();
    }
    async clockOut(evidence?: EvidenceReference) {
        await this.checkConnection();
        const record = await this.restore();
        if (!record?.sessionId || record.clockOutAt)
            throw new Error("Sesi aktif tidak tersedia.");
        await this.checkEvidence(evidence);
        const next = {
            ...record,
            clockOutAt: new Date().toISOString(),
            ...(evidence ? { clockOutEvidence: evidence } : {}),
        };
        await this.store.draft(next.owner, MORNING_KEY, next);
        return next;
    }
    private async checkEvidence(evidence?: EvidenceReference) {
        if (!evidence) return;
        const owner = ownerKey(this.identity);
        const row = (await this.store.listEvidence(owner)).find(
            (row) => row.key === `${owner}:${evidence.id}`,
        );
        await assertLocalEvidence(row, evidence, owner);
        if (
            fieldBusinessDate(new Date(evidence.capturedAt)) !==
            fieldBusinessDate()
        )
            throw new Error("Foto absensi harus diambil hari ini.");
    }
    async acceptAttendance(evidence?: EvidenceReference) {
        const businessDate = await this.checkConnection();
        await this.checkEvidence(evidence);
        const record: MorningRecord = {
            ...(evidence ? { attendanceEvidence: evidence } : {}),
            mode: "simulation",
            owner: ownerKey(this.identity),
            businessDate,
            attendanceReference: `SIM-ATT-${crypto.randomUUID()}`,
            attendanceAt: new Date().toISOString(),
            sessionId: null,
            openedAt: null,
            snapshot: null,
        };
        await this.store.draft(record.owner, MORNING_KEY, record);
        return record;
    }
    async open() {
        const date = await this.checkConnection();
        const attendance = await this.restore();
        if (!attendance || attendance.businessDate !== date)
            throw new Error("Absensi belum diterima. Buka sesi kerja dahulu.");
        const snapshot = SnapshotSchema.parse(await this.provider.snapshot());
        const deliveryManifest = this.identity.roles.includes("delivery")
            ? z
                  .array(DeliveryTaskSchema)
                  .min(1)
                  .parse(await this.provider.deliveryTasks?.())
            : undefined;
        if (
            deliveryManifest?.some(
                (t) =>
                    t.owner !== ownerKey(this.identity) ||
                    t.business_date !== date,
            )
        )
            throw new Error("Manifest daily sync tidak cocok.");
        if (!validMorningSnapshot(snapshot, date))
            throw new Error(
                "Paket PJP, stok dan harga belum lengkap atau tanggalnya tidak sesuai. Sesi belum dibuka.",
            );
        // Recheck after the request: midnight/offline must never unlock a stale session.
        await this.checkConnection();
        if (fieldBusinessDate() !== date)
            throw new Error("Tanggal bisnis berganti. Mulai sesi pagi baru.");
        const record: MorningRecord = {
            ...attendance,
            sessionId: crypto.randomUUID(),
            openedAt: new Date().toISOString(),
            snapshot,
            ...(deliveryManifest ? { deliveryManifest } : {}),
        };
        if (!morningReady(record, ownerKey(this.identity), date))
            throw new Error("Paket sesi tidak valid. Sesi belum dibuka.");
        // One IndexedDB record: never publish ready before the complete bundle is durable.
        await this.store.draft(record.owner, MORNING_KEY, record);
        return record;
    }
}
