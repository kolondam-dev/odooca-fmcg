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
    })
    .strict();
export type MorningRecord = z.infer<typeof MorningRecordSchema>;
export const MORNING_KEY = "morning-session-v1";
export function fieldBusinessDate(now = new Date()): string {
    return now.toLocaleDateString("en-CA", { timeZone: "Asia/Makassar" });
}
export function morningReady(
    record: MorningRecord | undefined,
    owner: string,
    date = fieldBusinessDate(),
): boolean {
    return (
        !!record &&
        record.mode === "simulation" &&
        record.owner === owner &&
        record.businessDate === date &&
        !!record.sessionId &&
        !!record.openedAt &&
        !!record.snapshot
    );
}
export class MorningSimulation {
    constructor(
        private store: FieldStore,
        private identity: Identity,
        private provider: FieldProvider,
    ) {}
    async restore(): Promise<MorningRecord | undefined> {
        const parsed = MorningRecordSchema.safeParse(
            await this.store.draft(ownerKey(this.identity), MORNING_KEY),
        );
        return parsed.success &&
            parsed.data.owner === ownerKey(this.identity) &&
            parsed.data.businessDate === fieldBusinessDate()
            ? parsed.data
            : undefined;
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
        if (!current.roles.includes("sales"))
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
        if (
            !snapshot.version.trim() ||
            !z.iso.datetime().safeParse(snapshot.updatedAt).success ||
            fieldBusinessDate(new Date(snapshot.updatedAt)) !== date ||
            !snapshot.outlets.length ||
            !snapshot.products.length
        )
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
        };
        // One IndexedDB record: never publish ready before the complete bundle is durable.
        await this.store.draft(record.owner, MORNING_KEY, record);
        return record;
    }
}
