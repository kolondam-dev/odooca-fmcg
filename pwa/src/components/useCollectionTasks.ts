import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    CollectionTaskSchema,
    collectionKey,
    type CollectionTask,
} from "../domain/collection-contracts";
import {
    ownerKey,
    type FieldProvider,
    type Identity,
} from "../domain/contracts";
import type { FieldStore } from "../storage/store";

/**
 * Memuat penugasan tagihan hari ini (draft lokal dahulu, lalu penyedia saat online) dan
 * memvalidasi pemilik/hari/kunci unik. Mengembalikan undefined sampai siap; galat dilaporkan terpisah.
 */
export function useCollectionTasks(
    identity: Identity,
    provider: FieldProvider,
    store: FieldStore,
) {
    const owner = ownerKey(identity);
    const key = `collection-manifest-v1:${identity.businessDate}`;
    const [tasks, setTasks] = useState<CollectionTask[]>();
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            if (!identity.capabilities?.includes("collection.capture"))
                throw new Error(
                    "Kewenangan pencatatan tagihan belum tersedia.",
                );
            let data = await store.draft(owner, key);
            if (data === undefined) {
                if (!navigator.onLine || !provider.collectionTasks)
                    throw new Error(
                        "Hubungkan jaringan untuk memuat penugasan tagihan.",
                    );
                data = await store.createDraftIfAbsent(
                    owner,
                    key,
                    await provider.collectionTasks(),
                );
            }
            const parsed = z.array(CollectionTaskSchema).min(1).parse(data);
            if (
                parsed.some(
                    (s) =>
                        s.delivery.owner !== owner ||
                        s.delivery.business_date !== identity.businessDate,
                ) ||
                new Set(parsed.map(collectionKey)).size !== parsed.length
            )
                throw new Error("Penugasan tagihan tidak cocok.");
            if (active) setTasks(parsed);
        })().catch((e) => {
            if (active) setError(e instanceof Error ? e.message : String(e));
        });
        return () => {
            active = false;
        };
    }, [owner, key]);
    return { tasks, error };
}
