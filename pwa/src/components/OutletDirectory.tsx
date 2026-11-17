import { useRememberedState, useRememberedScroll } from "../ui/viewMemory";
import { useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { outletMeta } from "../domain/outlet-card";
import { Button, OutletCard, Segmented } from "../ui";
import { FullDrawer } from "./FullDrawer";
import { Icon } from "./Icon";
export function OutletDirectory({
    outlets,
    open,
    closed,
    extra,
}: {
    outlets: Snapshot["outlets"];
    open: (id: string) => void;
    closed: (id: string) => boolean;
    extra: () => void;
}) {
    const suppressFocus = useRef(false);
    const dismiss = () => {
        suppressFocus.current = true;
        setSearch(false);
    };
    const [search, setSearch] = useState(false),
        [query, setQuery] = useRememberedState("outlet-query", "");
    const listScroll = useRememberedScroll<HTMLDivElement>("outlet-list");
    const filtered = outlets.filter((outlet) =>
        `${outlet.name} ${outlet.address}`
            .toLocaleLowerCase("id")
            .includes(query.trim().toLocaleLowerCase("id")),
    );
    const [filter, setFilter] = useState<"all" | "todo" | "done">("all");
    const doneCount = outlets.filter((o) => closed(o.id)).length;
    const nextId = outlets.find((o) => !closed(o.id))?.id;
    const rows = (values: typeof outlets) =>
        values.map((outlet) => {
            const done = closed(outlet.id);
            const meta = outletMeta(outlet);
            return (
                <OutletCard
                    key={outlet.id}
                    number={outlets.indexOf(outlet) + 1}
                    name={outlet.name}
                    address={outlet.address}
                    highlight={outlet.id === nextId}
                    meta={
                        meta.time || meta.distance ? (
                            <>
                                {meta.time ? (
                                    <span class="ui-ocard__m">
                                        <Icon name="clock" size={18} />
                                        {meta.time}
                                    </span>
                                ) : null}
                                {meta.distance ? (
                                    <span class="ui-ocard__m">
                                        <Icon name="pin" size={18} />
                                        {meta.distance}
                                    </span>
                                ) : null}
                            </>
                        ) : undefined
                    }
                    status={
                        done
                            ? { tone: "ok", label: "Selesai" }
                            : outlet.id === nextId
                              ? { tone: "info", label: "Berikutnya" }
                              : { tone: "neu", label: "Belum" }
                    }
                    onClick={() => {
                        setSearch(false);
                        open(outlet.id);
                    }}
                />
            );
        });
    const shown = outlets.filter(
        (o) => filter === "all" || (filter === "done") === closed(o.id),
    );
    return (
        <section class="sales-directory" aria-label="Daftar outlet">
            <div class="directory-toolbar">
                <label class="search compact-search">
                    <Icon name="store" size={18} />
                    <input
                        aria-label="Cari outlet"
                        placeholder="Cari outlet atau alamat…"
                        value={query}
                        readOnly
                        onFocus={() => {
                            if (suppressFocus.current) {
                                suppressFocus.current = false;
                                return;
                            }
                            setSearch(true);
                        }}
                        onClick={() => setSearch(true)}
                    />
                </label>
                <Button variant="sec" size="md" auto onClick={extra}>
                    Extra call
                </Button>
            </div>
            <div class="directory-filter">
                <Segmented
                    label="Filter outlet"
                    value={filter}
                    onChange={setFilter}
                    items={[
                        { value: "all", label: `Semua ${outlets.length}` },
                        {
                            value: "todo",
                            label: `Belum ${outlets.length - doneCount}`,
                        },
                        { value: "done", label: `Selesai ${doneCount}` },
                    ]}
                />
            </div>
            <div class="outlet-list ui-list" ref={listScroll}>
                {outlets.length ? (
                    <>
                        {rows(shown)}
                        {!shown.length && (
                            <p class="empty">
                                Tidak ada outlet pada filter ini.
                            </p>
                        )}
                    </>
                ) : (
                    <div class="ui-empty">
                        <span class="ui-empty__icon" aria-hidden="true">
                            <Icon name="store" size={36} />
                        </span>
                        <h2 class="ui-empty__title">
                            Belum ada outlet hari ini
                        </h2>
                        <p class="ui-empty__text">
                            PJP hari ini kosong atau belum disinkron. Tambahkan
                            kunjungan di luar rencana lewat Extra call.
                        </p>
                        <Button
                            variant="sec"
                            size="md"
                            auto
                            icon="plus"
                            onClick={extra}
                        >
                            Tambah Extra call
                        </Button>
                    </div>
                )}
            </div>
            {search && (
                <FullDrawer title="Pencarian outlet" close={dismiss}>
                    <label class="search compact-search">
                        <Icon name="store" size={18} />
                        <input
                            autoFocus
                            type="search"
                            aria-label="Cari outlet dalam pencarian"
                            placeholder="Nama toko atau alamat"
                            value={query}
                            onInput={(event) =>
                                setQuery(event.currentTarget.value)
                            }
                        />
                    </label>
                    <p class="result-count" role="status">
                        {filtered.length} outlet
                    </p>
                    <div class="search-results ui-list">
                        {rows(filtered)}
                        {!filtered.length && (
                            <p class="empty">Tidak ada outlet yang cocok.</p>
                        )}
                    </div>
                </FullDrawer>
            )}
        </section>
    );
}
