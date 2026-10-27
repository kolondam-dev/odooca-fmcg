import {
    bindVisitEvidence,
    assertVisitEvidence,
    validateVisitMedia,
} from "./visit-evidence";
import type { VisitEvidence } from "./visit-contracts";
import { ownerKey, type FieldProvider, type Identity } from "./contracts";
import { MORNING_KEY } from "./morning";
import {
    VISITS_KEY,
    bindVisitContext,
    currentMorning,
    requireVisitFix,
    visitLedger,
    visitOrders,
} from "./visit-validation";
import {
    VisitCheckoutSchema,
    type VisitFix,
    type VisitContext,
    type VisitCheckout,
} from "./visit-contracts";
import type { FieldStore } from "../storage/store";
import type { Outbox } from "./outbox";
export function captureVisitLocation(): Promise<VisitFix> {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject(new Error("Geolocation tidak tersedia pada perangkat ini."));
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (p) =>
                resolve({
                    latitude: p.coords.latitude,
                    longitude: p.coords.longitude,
                    accuracy: p.coords.accuracy,
                    sampled_at: new Date(p.timestamp).toISOString(),
                }),
            (e) =>
                reject(
                    new Error(
                        e.code === 1
                            ? "Izin lokasi ditolak. Aktifkan izin lokasi untuk kunjungan."
                            : e.code === 3
                              ? "Pengambilan lokasi timeout. Coba lagi di tempat aman."
                              : "Lokasi belum tersedia. Coba lagi.",
                    ),
                ),
            { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
        );
    });
}
export class SalesVisits {
    constructor(
        private store: FieldStore,
        private identity: Identity,
        private provider: FieldProvider,
        private outbox: Outbox,
    ) {}
    private async state() {
        if (
            this.provider.mode !== "demo" ||
            !this.identity.roles.includes("sales")
        )
            throw new Error(
                "Kunjungan resmi belum tersedia atau role tidak sesuai.",
            );
        const owner = ownerKey(this.identity),
            rawMorning = await this.store.draft(owner, MORNING_KEY),
            morning = currentMorning(rawMorning, owner),
            raw = await this.store.draft(owner, VISITS_KEY),
            rows = await this.store.list(owner),
            ledger = visitLedger(raw, owner, rows, rawMorning);
        await validateVisitMedia(rows, owner, this.store);
        return { owner, rawMorning, morning, raw, rows, ledger };
    }
    async restore(outletId: string) {
        const s = await this.state();
        const today = s.ledger.visits.filter(
            (v) => v.context.business_date === s.morning.businessDate,
        );
        const active = today.find((v) => !v.check_out);
        if (active) {
            bindVisitContext(active.context, s.morning, s.owner);
            const checkin = s.rows.find(
                (q) => q.command.client_uuid === active.context.visit_uuid,
            )!;
            if (!["queued", "sending", "accepted"].includes(checkin.state))
                throw new Error(
                    "Check-in ditahan/ditolak. Perlu review sebelum transaksi baru.",
                );
        }
        return {
            orders: today.find((v) => v.context.outlet_id === outletId)
                ? visitOrders(
                      s.rows,
                      today.find((v) => v.context.outlet_id === outletId)!
                          .context.visit_uuid,
                  ).length
                : 0,
            active,
            selected: today.find((v) => v.context.outlet_id === outletId),
            history: s.ledger.visits,
        };
    }
    async checkIn(outletId: string, fix: VisitFix, evidence?: VisitEvidence) {
        const s = await this.state(),
            outlet = s.morning.snapshot!.outlets.find((o) => o.id === outletId);
        if (!outlet)
            throw new Error(
                "Outlet tidak ada di PJP. Extra call memerlukan approval supervisor.",
            );
        const id = crypto.randomUUID(),
            context: VisitContext = {
                visit_uuid: id,
                work_session_id: s.morning.sessionId!,
                business_date: s.morning.businessDate,
                snapshot_version: s.morning.snapshot!.version,
                outlet_id: outletId,
                site: {
                    latitude: outlet.latitude,
                    longitude: outlet.longitude,
                    radius: outlet.radius,
                },
                fix,
            };
        requireVisitFix(fix, context.site);
        bindVisitContext(context, s.morning, s.owner);
        const at = new Date().toISOString();
        const photo = bindVisitEvidence(
            evidence,
            context,
            at,
            s.morning.openedAt!,
        );
        await assertVisitEvidence(photo, context, at, s.owner, this.store);
        return this.outbox.enqueue(
            "sales.visit.check_in",
            { ...context, evidence_version: 1, evidence: photo },
            `Check-in kunjungan • ${outlet.name}`,
            id,
            {
                key: VISITS_KEY,
                expected: s.raw,
                value: {
                    version: 1,
                    visits: [
                        ...s.ledger.visits,
                        {
                            photo_required: true,
                            check_in_evidence: photo,
                            mode: "simulation",
                            owner: s.owner,
                            context,
                            session_opened_at: s.morning.openedAt!,
                            morning_source: s.morning,
                            check_in_at: at,
                            check_out: null,
                        },
                    ],
                },
                visitGuard: { morning: s.rawMorning },
                occurredAt: at,
            },
        );
    }
    async submitOrder(payload: Record<string, unknown>, fix: VisitFix) {
        const s = await this.state(),
            active = s.ledger.visits.find(
                (v) =>
                    !v.check_out &&
                    v.context.business_date === s.morning.businessDate &&
                    v.context.outlet_id === payload.outlet_id,
            );
        if (!active)
            throw new Error("Mulai kunjungan outlet sebelum membuat order.");
        const context = { ...active.context, fix };
        bindVisitContext(context, s.morning, s.owner);
        requireVisitFix(fix, context.site);
        if (
            payload.work_session_id !== context.work_session_id ||
            payload.snapshot_version !== context.snapshot_version
        )
            throw new Error(
                "Draft order memakai sesi/paket berbeda. Muat ulang.",
            );
        return this.outbox.enqueue(
            "sales.order.submit",
            { ...payload, visit_context: context },
            `Order • ${s.morning.snapshot!.outlets.find((o) => o.id === context.outlet_id)!.name}`,
            crypto.randomUUID(),
            {
                key: VISITS_KEY,
                expected: s.raw,
                value: s.ledger,
                visitGuard: { morning: s.rawMorning },
            },
        );
    }
    async checkOut(
        outletId: string,
        fix: VisitFix,
        outcome: VisitCheckout["outcome"],
        notes: string,
        evidence?: VisitEvidence,
    ) {
        const s = await this.state(),
            active = s.ledger.visits.find(
                (v) =>
                    !v.check_out &&
                    v.context.business_date === s.morning.businessDate &&
                    v.context.outlet_id === outletId,
            );
        if (!active) throw new Error("Kunjungan outlet ini tidak aktif.");
        const at = new Date().toISOString();
        const photo = bindVisitEvidence(
            evidence,
            active.context,
            at,
            active.check_in_at,
        );
        await assertVisitEvidence(
            photo,
            active.context,
            at,
            s.owner,
            this.store,
        );
        const body = VisitCheckoutSchema.parse({
            evidence_version: 1,
            evidence: photo,
            ...active.context,
            fix,
            outcome,
            notes,
            order_uuids: visitOrders(s.rows, active.context.visit_uuid)
                .map((q) => q.command.client_uuid)
                .sort(),
        });
        bindVisitContext(body, s.morning, s.owner);
        requireVisitFix(fix, body.site);
        const id = crypto.randomUUID();
        return this.outbox.enqueue(
            "sales.visit.check_out",
            body,
            `Tutup kunjungan • ${outletId}`,
            id,
            {
                key: VISITS_KEY,
                expected: s.raw,
                value: {
                    version: 1,
                    visits: s.ledger.visits.map((v) =>
                        v === active
                            ? {
                                  ...v,
                                  check_out: {
                                      command_uuid: id,
                                      occurred_at: at,
                                      payload: body,
                                  },
                              }
                            : v,
                    ),
                },
                visitGuard: { morning: s.rawMorning },
                occurredAt: at,
            },
        );
    }
}
