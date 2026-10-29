import { SalesVisits } from "../src/domain/visits";
import { ownerKey } from "../src/domain/contracts";
import { sha256, evidenceBinding } from "../src/domain/evidence-package";
import type { FieldStore, Evidence } from "../src/storage/store";
import type {
    VisitFix,
    VisitEvidence,
    VisitCheckout,
} from "../src/domain/visit-contracts";
// Existing geo/session regressions also exercise the new photo-mandatory path.
// Byte fixtures here are for integrity units; browser tests use actual PNG/JPEG.
export async function makeVisitPhoto(
    store: FieldStore,
    owner: string,
    fix: VisitFix,
): Promise<VisitEvidence> {
    const ref = {
        id: crypto.randomUUID(),
        latitude: fix.latitude,
        longitude: fix.longitude,
        accuracy: fix.accuracy,
        capturedAt: new Date().toISOString(),
    };
    const row: Evidence = {
        owner,
        key: `${owner}:${ref.id}`,
        blob: new Blob(["unit-photo"], { type: "image/jpeg" }),
        ...ref,
        mapStatus: "pending",
    };
    const map = new Blob(["unit-pinpoint"], { type: "image/png" });
    const visual = {
        version: 1 as const,
        kind: "simulation_grid" as const,
        selectedAt: ref.capturedAt,
        fixSampledAt: ref.capturedAt,
        photoSha256: await sha256(row.blob),
        mapSha256: await sha256(map),
    };
    const packageHash = await sha256(evidenceBinding(row, visual));
    row.visual = { ...visual, map, bindingSha256: packageHash };
    await store.saveEvidence(row);
    return { ...ref, packageHash };
}
export class PhotoSalesVisits extends SalesVisits {
    private fixtureStore: FieldStore;
    private fixtureOwner: string;
    constructor(...args: ConstructorParameters<typeof SalesVisits>) {
        super(...args);
        this.fixtureStore = args[0];
        this.fixtureOwner = ownerKey(args[1]);
    }
    override async checkIn(id: string, fix: VisitFix, photo?: VisitEvidence) {
        return super.checkIn(
            id,
            fix,
            photo ??
                (await makeVisitPhoto(
                    this.fixtureStore,
                    this.fixtureOwner,
                    fix,
                )),
        );
    }
    override async checkOut(
        id: string,
        fix: VisitFix,
        outcome: VisitCheckout["outcome"],
        notes: string,
        photo?: VisitEvidence,
    ) {
        return super.checkOut(
            id,
            fix,
            outcome,
            notes,
            photo ??
                (await makeVisitPhoto(
                    this.fixtureStore,
                    this.fixtureOwner,
                    fix,
                )),
        );
    }
}
