import {
    ApiError,
    IdentitySchema,
    ReceiptSchema,
    SnapshotSchema,
    type Command,
    type FieldProvider,
    type Identity,
} from "../domain/contracts";
export class HttpProvider implements FieldProvider {
    readonly mode = "live" as const;
    private csrf?: string;
    private identity?: Identity;
    private bootstrapGeneration = 0;
    private async request(path: string, body?: unknown) {
        const response = await fetch(`/api/v1/${path}`, {
            credentials: "same-origin",
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
        if (!response.ok)
            throw new ApiError(
                response.status,
                response.status === 401
                    ? "Sesi resmi belum tersedia. Silakan login melalui layanan perusahaan."
                    : `Layanan belum siap (${response.status}).`,
            );
        return response.json();
    }
    async bootstrap() {
        const generation = ++this.bootstrapGeneration;
        this.identity = undefined;
        this.csrf = undefined;
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
            throw new ApiError(
                422,
                "Scope/satuan snapshot tidak cocok dengan sesi bootstrap.",
            );
        return snapshot;
    }
    async submit(command: Command) {
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
