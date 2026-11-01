import { useRememberedState, useRememberedScroll } from "../ui/viewMemory";
import { useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { OutletAvatar } from "./OutletAvatar";
import { FullDrawer } from "./FullDrawer";
import { Icon } from "./Icon";
export function OutletDirectory({
    outlets,
    open,
    status,
    extra,
}: {
    outlets: Snapshot["outlets"];
    open: (id: string) => void;
    status: (id: string) => string;
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
    const rows = (values: typeof outlets) =>
        values.map((outlet) => (
            <button
                class="outlet-row"
                key={outlet.id}
                onClick={() => {
                    setSearch(false);
                    open(outlet.id);
                }}
            >
                <OutletAvatar url={outlet.image_url} name={outlet.name} />
                <span>
                    <strong>{outlet.name}</strong>
                    <small>{outlet.address}</small>
                    <small>{status(outlet.id)}</small>
                </span>
                <Icon name="caret" size={18} />
            </button>
        ));
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
                <button class="text-button" onClick={extra}>
                    Extra call
                </button>
            </div>
            <div class="outlet-list" ref={listScroll}>
                {rows(outlets)}
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
                    <div class="search-results">
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
