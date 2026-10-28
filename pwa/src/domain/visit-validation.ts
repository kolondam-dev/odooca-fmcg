import { validateOrderQuote } from "./order-pricing";
import { bindVisitEvidence } from "./visit-evidence";
import { CommandSchema, validateOrder } from "./contracts";
import {
    fieldBusinessDate,
    morningReady,
    MorningRecordSchema,
} from "./morning";
import { distanceMeters, geofence } from "./format";
import {
    VisitContextSchema,
    VisitOrderSchema,
    VisitFixSchema,
    VisitSiteSchema,
    VisitLedgerSchema,
    type VisitContext,
    type VisitFix,
    type VisitLedger,
} from "./visit-contracts";
import type { QueueItem } from "../storage/store";
export const VISITS_KEY = "sales-visits-v1";
export function assessVisitFix(value: unknown, site: unknown, at = Date.now()) {
    const fix = VisitFixSchema.safeParse(value),
        anchor = VisitSiteSchema.safeParse(site);
    if (!fix.success || !anchor.success)
        return { status: "invalid" as const, distance: NaN };
    const age = at - Date.parse(fix.data.sampled_at);
    if (age < -1000) return { status: "future" as const, distance: NaN };
    if (age > 60000) return { status: "stale" as const, distance: NaN };
    const distance = distanceMeters(
        fix.data.latitude,
        fix.data.longitude,
        anchor.data.latitude,
        anchor.data.longitude,
    );
    return {
        status: geofence(distance, fix.data.accuracy, anchor.data.radius),
        distance,
    };
}
export function requireVisitFix(fix: VisitFix, site: unknown, at = Date.now()) {
    const result = assessVisitFix(fix, site, at);
    if (result.status !== "inside")
        throw new Error(
            result.status === "stale"
                ? "Lokasi kedaluwarsa. Ambil lokasi baru."
                : result.status === "outside"
                  ? "Lokasi berada di luar geofence outlet."
                  : result.status === "future"
                    ? "Waktu lokasi berada di masa depan. Ambil ulang."
                    : "Akurasi/lokasi belum cukup pasti untuk geofence outlet.",
        );
}
export function visitContextOf(value: unknown): VisitContext {
    const v = value as VisitContext;
    return VisitContextSchema.parse({
        visit_uuid: v.visit_uuid,
        work_session_id: v.work_session_id,
        business_date: v.business_date,
        snapshot_version: v.snapshot_version,
        outlet_id: v.outlet_id,
        site: v.site,
        fix: v.fix,
    });
}
const same = (a: unknown, b: unknown) =>
    JSON.stringify(a) === JSON.stringify(b);
export function currentMorning(value: unknown, owner: string) {
    const parsed = MorningRecordSchema.safeParse(value);
    if (!parsed.success || !morningReady(parsed.data, owner))
        throw new Error(
            "Sesi pagi belum siap atau sudah berganti hari. Sync pagi kembali.",
        );
    return parsed.data;
}
export function bindVisitContext(
    context: VisitContext,
    morning: ReturnType<typeof currentMorning>,
    owner: string,
    date = fieldBusinessDate(),
) {
    if (
        !morningReady(morning, owner, date) ||
        morning.sessionId !== context.work_session_id ||
        morning.businessDate !== context.business_date ||
        morning.snapshot?.version !== context.snapshot_version
    )
        throw new Error("Konteks kunjungan tidak cocok dengan sesi pagi.");
    const outlet = morning.snapshot!.outlets.find(
        (o) => o.id === context.outlet_id,
    );
    if (
        !outlet ||
        !same(context.site, {
            latitude: outlet.latitude,
            longitude: outlet.longitude,
            radius: outlet.radius,
        })
    )
        throw new Error("Outlet/geofence tidak sesuai paket PJP pagi.");
}
export function visitOrders(rows: QueueItem[], visitId: string) {
    return rows.filter(
        (q) =>
            q.command.type === "sales.order.submit" &&
            q.command.payload.visit_context &&
            VisitContextSchema.parse(q.command.payload.visit_context)
                .visit_uuid === visitId,
    );
}
export function visitLedger(
    value: unknown,
    owner: string,
    rows: QueueItem[],
    fallbackMorning?: unknown,
): VisitLedger {
    if (value === undefined) value = { version: 1, visits: [] };
    const parsed = VisitLedgerSchema.safeParse(value);
    if (!parsed.success)
        throw new Error(
            "Riwayat kunjungan tidak valid. Data dipertahankan untuk review.",
        );
    const ids = new Set<string>();
    const photoIds = new Set<string>();
    const claimPhoto = (
        ref: unknown,
        c: VisitContext,
        at: string,
        notBefore: string,
    ) => {
        const photo = bindVisitEvidence(ref, c, at, notBefore);
        if (photoIds.has(photo.id))
            throw new Error(
                "Foto sudah digunakan oleh aksi kunjungan lain. Ambil foto baru.",
            );
        photoIds.add(photo.id);
    };
    for (const record of parsed.data.visits) {
        const c = record.context;
        const source = MorningRecordSchema.parse(
            record.morning_source ?? fallbackMorning,
        );
        bindVisitContext(c, source, owner, c.business_date);
        if (source.openedAt !== record.session_opened_at)
            throw new Error("Sumber sesi historis kunjungan tidak cocok.");
        if (
            record.owner !== owner ||
            ids.has(c.visit_uuid) ||
            Date.parse(record.check_in_at) > Date.now() ||
            Date.parse(record.session_opened_at) >
                Date.parse(record.check_in_at) ||
            fieldBusinessDate(new Date(record.session_opened_at)) !==
                c.business_date ||
            fieldBusinessDate(new Date(record.check_in_at)) !== c.business_date
        )
            throw new Error(
                "Owner/tanggal/urutan riwayat kunjungan tidak valid.",
            );
        ids.add(c.visit_uuid);
        requireVisitFix(c.fix, c.site, Date.parse(record.check_in_at));
        const start = rows.find((q) => q.command.client_uuid === c.visit_uuid);
        if (
            !start ||
            start.owner !== owner ||
            start.key !== `${owner}:${c.visit_uuid}` ||
            start.command.type !== "sales.visit.check_in" ||
            !CommandSchema.safeParse(start.command).success ||
            !same(start.command.payload, {
                ...c,
                ...(record.check_in_evidence
                    ? {
                          evidence_version: 1,
                          evidence: record.check_in_evidence,
                      }
                    : {}),
            }) ||
            start.command.occurred_at !== record.check_in_at
        )
            throw new Error(
                "Referensi check-in hilang atau berubah. Data dipertahankan.",
            );
        if (
            (record.photo_required && !record.check_in_evidence) ||
            (record.check_in_evidence && !record.photo_required)
        )
            throw new Error(
                "Sumber foto check-in hilang atau berubah; perlu review.",
            );
        if (record.check_in_evidence)
            claimPhoto(
                record.check_in_evidence,
                c,
                record.check_in_at,
                record.session_opened_at,
            );
        if (record.check_out) {
            const end = record.check_out,
                finish = rows.find(
                    (q) => q.command.client_uuid === end.command_uuid,
                );
            if (
                !finish ||
                finish.owner !== owner ||
                finish.key !== `${owner}:${end.command_uuid}` ||
                finish.command.type !== "sales.visit.check_out" ||
                !CommandSchema.safeParse(finish.command).success ||
                finish.command.occurred_at !== end.occurred_at ||
                !same(finish.command.payload, end.payload) ||
                !same({ ...visitContextOf(end.payload), fix: c.fix }, c) ||
                Date.parse(end.occurred_at) < Date.parse(record.check_in_at) ||
                Date.parse(end.occurred_at) > Date.now() ||
                fieldBusinessDate(new Date(end.occurred_at)) !== c.business_date
            )
                throw new Error("Penutupan/urutan kunjungan tidak valid.");
            requireVisitFix(
                end.payload.fix,
                c.site,
                Date.parse(end.occurred_at),
            );
            if (record.photo_required && !end.payload.evidence_version)
                throw new Error(
                    "Foto check-out wajib untuk kunjungan ini; perlu review.",
                );
            if (end.payload.evidence_version)
                claimPhoto(
                    end.payload.evidence,
                    c,
                    end.occurred_at,
                    record.check_in_at,
                );
            const orders = visitOrders(rows, c.visit_uuid)
                .map((q) => q.command.client_uuid)
                .sort();
            if (
                !same([...end.payload.order_uuids].sort(), orders) ||
                (end.payload.outcome === "order_requested") !==
                    !!orders.length ||
                (end.payload.outcome !== "order_requested" &&
                    end.payload.notes.trim().length < 5)
            )
                throw new Error(
                    "Hasil kunjungan tidak sesuai pengajuan order/alasan.",
                );
        }
    }
    for (const q of rows) {
        if (
            q.command.type === "sales.order.submit" &&
            !q.command.payload.visit_context &&
            parsed.data.visits.some(
                (v) =>
                    v.check_out?.payload.order_uuids.includes(
                        q.command.client_uuid,
                    ) ||
                    (q.command.type === "sales.order.submit" &&
                        v.context.work_session_id ===
                            q.command.payload.work_session_id &&
                        v.context.outlet_id === q.command.payload.outlet_id),
            )
        )
            throw new Error(
                "Order kunjungan kehilangan konteks sumber; perlu review.",
            );
        if (
            q.command.type !== "sales.order.submit" ||
            !q.command.payload.visit_context
        )
            continue;
        const c = VisitContextSchema.parse(q.command.payload.visit_context),
            r = parsed.data.visits.find(
                (v) => v.context.visit_uuid === c.visit_uuid,
            );
        if (
            !r ||
            q.owner !== owner ||
            q.key !== `${owner}:${q.command.client_uuid}` ||
            !CommandSchema.safeParse(q.command).success ||
            q.command.payload.outlet_id !== c.outlet_id ||
            q.command.payload.work_session_id !== c.work_session_id ||
            q.command.payload.snapshot_version !== c.snapshot_version ||
            !same({ ...c, fix: r.context.fix }, r.context) ||
            Date.parse(q.command.occurred_at) < Date.parse(r.check_in_at) ||
            Date.parse(q.command.occurred_at) > Date.now() ||
            fieldBusinessDate(new Date(q.command.occurred_at)) !==
                c.business_date ||
            (r.check_out &&
                Date.parse(q.command.occurred_at) >
                    Date.parse(r.check_out.occurred_at))
        )
            throw new Error("Konteks order/kunjungan tidak valid.");
        const body = VisitOrderSchema.parse(q.command.payload);
        validateOrderQuote(
            body,
            MorningRecordSchema.parse(r.morning_source ?? fallbackMorning)
                .snapshot!,
        );
        if (body.morning_business_date !== c.business_date)
            throw new Error("Tanggal order/kunjungan tidak cocok.");
        const source = MorningRecordSchema.parse(
            r.morning_source ?? fallbackMorning,
        );
        const invalid = validateOrder(
            body.lines.map((l) => ({
                productId: l.product_id,
                quantity: Number(l.qty),
            })),
            source.snapshot!,
        );
        if (invalid) throw new Error(invalid);
        requireVisitFix(c.fix, c.site, Date.parse(q.command.occurred_at));
    }
    for (const q of rows) {
        if (
            (q.command.type === "sales.visit.check_in" &&
                !ids.has(q.command.client_uuid)) ||
            (q.command.type === "sales.visit.check_out" &&
                !parsed.data.visits.some(
                    (r) => r.check_out?.command_uuid === q.command.client_uuid,
                ))
        )
            throw new Error(
                "Antrean kunjungan tidak memiliki riwayat yang sesuai.",
            );
    }
    return parsed.data;
}
export interface VisitCommitGuard {
    morning: unknown;
}
export function validateVisitCommit(
    item: QueueItem,
    old: unknown,
    value: unknown,
    morningRaw: unknown,
    rows: QueueItem[],
) {
    const morning = currentMorning(morningRaw, item.owner),
        before = visitLedger(old, item.owner, rows, morningRaw);
    const after = visitLedger(value, item.owner, [...rows, item], morningRaw);
    const c = visitContextOf(
        item.command.type === "sales.order.submit"
            ? item.command.payload.visit_context
            : item.command.payload,
    );
    bindVisitContext(c, morning, item.owner);
    requireVisitFix(c.fix, c.site);
    if (item.command.type === "sales.visit.check_in") {
        if (
            c.visit_uuid !== item.command.client_uuid ||
            before.visits.some(
                (v) =>
                    v.context.business_date === morning.businessDate &&
                    (!v.check_out || v.context.outlet_id === c.outlet_id),
            )
        )
            throw new Error(
                "Kunjungan masih aktif atau outlet sudah dikunjungi pada sesi hari ini.",
            );
        if (
            item.command.type !== "sales.visit.check_in" ||
            item.command.payload.evidence_version !== 1
        )
            throw new Error("Check-in baru wajib foto kunjungan.");
        const record = {
            mode: "simulation",
            owner: item.owner,
            context: c,
            session_opened_at: morning.openedAt!,
            morning_source: morning,
            check_in_at: item.command.occurred_at,
            photo_required: true,
            check_in_evidence: item.command.payload.evidence,
            check_out: null,
        };
        if (!same(after, { version: 1, visits: [...before.visits, record] }))
            throw new Error("Transisi check-in tidak valid.");
    } else {
        const active = before.visits.find(
            (v) => v.context.visit_uuid === c.visit_uuid,
        );
        if (
            !active ||
            active.check_out ||
            !same({ ...c, fix: active.context.fix }, active.context)
        )
            throw new Error("Kunjungan tidak aktif untuk outlet ini.");
        const checkin = rows.find(
            (q) => q.command.client_uuid === c.visit_uuid,
        )!;
        if (!["queued", "sending", "accepted"].includes(checkin.state))
            throw new Error(
                "Check-in ditahan/ditolak. Perlu review sebelum transaksi baru.",
            );
        if (item.command.type === "sales.order.submit") {
            const body = VisitOrderSchema.parse(item.command.payload);
            validateOrderQuote(body, morning.snapshot!);
            const invalid = validateOrder(
                body.lines.map((l) => ({
                    productId: l.product_id,
                    quantity: Number(l.qty),
                })),
                morning.snapshot!,
            );
            if (invalid) throw new Error(invalid);
            if (body.morning_business_date !== c.business_date)
                throw new Error("Tanggal order tidak sesuai kunjungan.");
            if (!same(before, after))
                throw new Error(
                    "Order tidak boleh mengubah riwayat kunjungan.",
                );
        } else if (item.command.type === "sales.visit.check_out") {
            if (item.command.payload.evidence_version !== 1)
                throw new Error("Check-out baru wajib foto kunjungan.");
            if (
                !same(after, {
                    version: 1,
                    visits: before.visits.map((v) =>
                        v === active
                            ? {
                                  ...v,
                                  check_out: {
                                      command_uuid: item.command.client_uuid,
                                      occurred_at: item.command.occurred_at,
                                      payload: item.command.payload,
                                  },
                              }
                            : v,
                    ),
                })
            )
                throw new Error("Transisi penutupan tidak valid.");
        } else throw new Error("Operasi kunjungan tidak diizinkan.");
    }
    return c;
}

// Legacy orders without visit context remain supported unless the ledger links
// them to this visit. Never use today's readiness to authorize historical replay.
export function validateVisitSync(
    item: QueueItem,
    owner: string,
    ledger: unknown,
    rows: QueueItem[],
    morning: unknown,
) {
    // New validator at each send boundary: never reuse a cached graph after await.
    createVisitSyncValidator(owner, ledger, rows, morning)(item);
}
// Reuse only while projecting ONE immutable readonly snapshot, such as the
// diagnosis list. Validate the shared graph once instead of once per row.
export function createVisitSyncValidator(
    owner: string,
    ledger: unknown,
    rows: QueueItem[],
    morning: unknown,
) {
    const parsed = VisitLedgerSchema.safeParse(ledger);
    let checked = false;
    let graphError: unknown;
    return (item: QueueItem) => {
        const command = CommandSchema.parse(item.command);
        const linked =
            parsed.success &&
            parsed.data.visits.some(
                (v) =>
                    v.context.visit_uuid === command.client_uuid ||
                    v.check_out?.command_uuid === command.client_uuid ||
                    v.check_out?.payload.order_uuids.includes(
                        command.client_uuid,
                    ) ||
                    (command.type === "sales.order.submit" &&
                        v.context.work_session_id ===
                            command.payload.work_session_id &&
                        v.context.outlet_id === command.payload.outlet_id),
            );
        const related =
            command.type === "sales.visit.check_in" ||
            command.type === "sales.visit.check_out" ||
            (command.type === "sales.order.submit" &&
                Object.hasOwn(command.payload, "visit_context")) ||
            linked;
        if (!related) return;
        if (
            item.owner !== owner ||
            item.key !== `${owner}:${command.client_uuid}` ||
            !rows.some(
                (q) =>
                    q.key === item.key &&
                    q.owner === owner &&
                    same(q.command, item.command),
            )
        )
            throw new Error(
                "Antrean kunjungan berubah atau owner tidak cocok.",
            );
        if (!checked) {
            checked = true;
            try {
                visitLedger(ledger, owner, rows, morning);
            } catch (error) {
                graphError = error;
            }
        }
        if (graphError) throw graphError;
        if (command.type === "sales.order.submit")
            VisitContextSchema.parse(command.payload.visit_context);
    };
}
