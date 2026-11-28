import {
    ApiError,
    PayloadRejectedError,
    IdentitySchema,
    ReceiptSchema,
    SnapshotSchema,
    type Command,
    type FieldProvider,
    type Identity,
    type Snapshot,
} from "../domain/contracts";
import { assertLocalEvidence } from "../domain/evidence-package";
import { uploadOfficialEvidence } from "./official-evidence";
import type { FieldStore } from "../storage/store";
export class HttpProvider implements FieldProvider {
    readonly mode = "live" as const;
    constructor(private options: { readOnly?: boolean } = {}) {}
    invalidate() {
        ++this.bootstrapGeneration;
        this.identity = undefined;
        this.csrf = undefined;
        this.lastSnapshot = undefined;
    }
    private csrf?: string;
    private identity?: Identity;
    private lastSnapshot?: Snapshot;
    private bootstrapGeneration = 0;
    private async request(path: string, body?: unknown) {
        const response = await fetch(`/api/v1/${path}`, {
            credentials: "same-origin",
            redirect: "error",
            cache: "no-store",
            signal: AbortSignal.timeout(15000),
            headers: {
                Accept: "application/json",
                ...(body
                    ? {
                          "Content-Type": "application/json",
                          "X-CSRF-Token": this.csrf ?? "",
                      }
                    : {}),
            },
            method: body ? "POST" : "GET",
            ...(body ? { body: JSON.stringify(body) } : {}),
        });
        if (!response.ok) {
            let detail = "";
            try {
                const error = await response.clone().json();
                detail = typeof error?.error === "string" ? error.error : "";
            } catch {
                // Keep the status-based message for non-JSON gateway errors.
            }
            throw new ApiError(
                response.status,
                response.status === 401
                    ? "Sesi resmi belum tersedia. Silakan login melalui layanan perusahaan."
                    : detail || `Layanan belum siap (${response.status}).`,
            );
        }
        return response.json();
    }
    async bootstrap() {
        const generation = ++this.bootstrapGeneration;
        this.identity = undefined;
        this.csrf = undefined;
        this.lastSnapshot = undefined;
        try {
            const identity = IdentitySchema.parse(
                await this.request("me/bootstrap"),
            );
            if (generation !== this.bootstrapGeneration)
                throw new ApiError(
                    409,
                    "Bootstrap usang; sesi terbaru dipertahankan.",
                );
            this.csrf = identity.csrfToken;
            this.identity = identity;
            return identity;
        } catch (error) {
            // Both stale successes and stale errors cancel the older caller.
            // They must never restore or clear the latest session's state.
            if (generation !== this.bootstrapGeneration)
                throw new ApiError(
                    409,
                    "Bootstrap usang; sesi terbaru dipertahankan.",
                );
            throw error;
        }
    }
    async snapshot() {
        if (!this.identity)
            throw new ApiError(401, "Bootstrap wajib sebelum snapshot.");
        const identity = this.identity;
        // Kegagalan skema tetap ZodError (dipetakan "belum dapat dibaca" oleh
        // read-session); open() menandainya sebagai tahap validasi.
        const snapshot = SnapshotSchema.parse(
            await this.request("sync/snapshot"),
        );
        if (this.identity !== identity)
            throw new ApiError(409, "Sesi berubah saat snapshot dibaca.");

        if (
            snapshot.catalog_version !== 2 ||
            !snapshot.scope ||
            snapshot.scope.company_id !== identity.companyId ||
            snapshot.scope.user_id !== identity.id ||
            snapshot.scope.business_date !== identity.businessDate
        )
            throw new PayloadRejectedError(
                "Scope/satuan snapshot tidak cocok dengan sesi bootstrap.",
            );
        this.lastSnapshot = snapshot;
        return snapshot;
    }
    async deliveryTasks() {
        if (!this.lastSnapshot)
            throw new ApiError(
                409,
                "Snapshot wajib dibaca sebelum manifest delivery.",
            );
        return this.lastSnapshot.deliveries;
    }
    async submitWithEvidence(
        command: Command,
        store: FieldStore,
        owner: string,
    ) {
        if (command.type !== "delivery.pod.submit")
            throw new ApiError(422, "Hanya POD memakai unggah bukti resmi.");
        if (this.options.readOnly)
            throw new ApiError(405, "Build staging hanya membaca data.");
        const identity = this.identity,
            snapshot = this.lastSnapshot,
            p = command.payload;
        if (
            !identity ||
            !this.csrf ||
            !snapshot?.scope ||
            owner !== `${identity.companyId}:${identity.id}` ||
            p.source.owner !== owner ||
            p.source.business_date !== identity.businessDate ||
            snapshot.scope.business_date !== identity.businessDate ||
            !snapshot.deliveries.some(
                (task) =>
                    task.id === p.source.id &&
                    task.outlet_id === p.source.outlet_id &&
                    task.trip === p.source.trip &&
                    task.version === p.source.version,
            )
        )
            throw new ApiError(
                409,
                "Manifest/sesi berubah; sinkronkan kembali.",
            );

        let originalHash = "";
        for (const ref of [p.session?.opening, p.evidence]) {
            if (!ref) continue;
            const row = await store.getEvidence(owner, ref.id);
            await assertLocalEvidence(row, ref, owner);
            if (!row?.visual)
                throw new ApiError(422, "Paket foto POD tidak lengkap.");
            const { receipt } = await uploadOfficialEvidence(
                {
                    client_uuid: ref.id,
                    outlet_id: p.source.outlet_id,
                    business_date: identity.businessDate,
                    snapshot_version: snapshot.version,
                    photo_selected_at: row.visual.selectedAt,
                    device_recorded_at: row.capturedAt,
                    fix_sampled_at: row.visual.fixSampledAt,
                    latitude: ref.latitude,
                    longitude: ref.longitude,
                    accuracy: ref.accuracy,
                },
                new File([row.blob], "pod.jpg", { type: "image/jpeg" }),
                this.csrf,
                AbortSignal.timeout(30000),
                {
                    userId: identity.id,
                    companyId: identity.companyId,
                    warehouseId: snapshot.scope.warehouse_id,
                },
            );
            if (ref.id === p.evidence.id)
                originalHash = receipt.original_sha256;
        }
        if (!originalHash)
            throw new ApiError(422, "Receipt foto POD belum diterima.");
        // The local packageHash binds the local grid and photo; Odoo's
        // authoritative receipt uses the original photo hash instead. Keep
        // the immutable outbox command intact and translate only on the wire.
        return this.submit({
            ...command,
            payload: {
                ...p,
                evidence: { ...p.evidence, packageHash: originalHash },
            },
        });
    }
    async submit(command: Command) {
        if (this.options.readOnly)
            throw new ApiError(405, "Build staging hanya membaca data.");
        if (!this.csrf) throw new ApiError(401, "CSRF/session belum tersedia.");
        return ReceiptSchema.parse(
            await this.request("sync/commands", command),
        );
    }
}
export async function createProvider(actor: string): Promise<FieldProvider> {
    if (__DEMO__) {
        const { MockProvider } = await import("./mock");
        return new MockProvider(actor, true);
    }
    return new HttpProvider();
}
