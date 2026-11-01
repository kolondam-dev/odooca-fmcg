import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    MORNING_KEY,
    morningReady,
    type MorningRecord,
} from "../domain/morning";
import {
    DeliveryTaskSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import type { Outbox } from "../domain/outbox";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    ownerKey,
    type Identity,
    type FieldProvider,
} from "../domain/contracts";
import { DeliveryTaskEditor } from "./DeliveryTaskEditor";
export function DeliveryWorkspace({
    store,
    identity,
    engine,
    changed,
    queue,
}: {
    store: FieldStore;
    identity: Identity;
    provider: FieldProvider;
    engine: Outbox;
    changed: () => void;
    queue: QueueItem[];
}) {
    const owner = ownerKey(identity),
        cache = `delivery-manifest-v1:${identity.businessDate}`;
    const [tasks, setTasks] = useState<DeliveryTask[]>(),
        [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            const morning = (await store.draft(owner, MORNING_KEY)) as
                | MorningRecord
                | undefined;
            if (!morningReady(morning, owner) || !morning?.deliveryManifest)
                throw new Error(
                    "Daily sync manifest wajib sebelum list Delivery.",
                );
            const manifest = z
                .array(DeliveryTaskSchema)
                .min(1)
                .parse(morning.deliveryManifest);
            if (
                manifest.some(
                    (s) =>
                        s.owner !== owner ||
                        s.business_date !== identity.businessDate,
                ) ||
                new Set(manifest.map(podKey)).size !== manifest.length
            )
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            let value = await store.draft(owner, cache);
            if (value === undefined) {
                // Daily sync already fetched this bundle. No network is needed to
                // materialize the validated local projection for the first visit.
                value = await store.createDraftIfAbsent(owner, cache, manifest);
            }
            const parsed = z.array(DeliveryTaskSchema).min(1).parse(value);
            if (JSON.stringify(parsed) !== JSON.stringify(manifest))
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            if (active) setTasks(parsed);
        })().catch((e) => {
            if (active) setError(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, cache]);
    return (
        <section>
            <h2>Serah terima pengiriman</h2>

            {error && <p role="alert">{error}</p>}
            {tasks?.map((task) => (
                <DeliveryTaskEditor
                    key={JSON.stringify(task)}
                    {...{ task, store, owner, engine, changed, queue }}
                />
            ))}
        </section>
    );
}
