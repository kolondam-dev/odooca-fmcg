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
    return !!validMorningRecord(record, owner, date)?.sessionId;
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
                "Simulator menolak / belum menerima sesi. Pilih respons Normal untuk melanjutkan simulasi.",
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
    async acceptAttendance() {
        const businessDate = await this.checkConnection();
        const record: MorningRecord = {
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
            throw new Error("Simulasikan absensi diterima sebelum sync pagi.");
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
